import os
import re
import time
from datetime import datetime, timezone

import duckdb
import httpx
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import Counter, Gauge, Histogram, make_asgi_app
SERVICE_VERSION = "1.0.0"
from pydantic import BaseModel

from auth import get_current_user

http_requests_total = Counter(
    "http_requests_total",
    "Total number of HTTP requests",
    ["method", "endpoint", "status", "version"],
)
http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint", "version"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)
duckdb_query_duration_seconds = Histogram(
    "duckdb_query_duration_seconds",
    "DuckDB query duration in seconds",
    ["query_type", "version"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0),
)
active_connections = Gauge(
    "active_connections",
    "Number of currently active HTTP connections",
    ["version"],
)

app = FastAPI(title="Orders Service")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)

_ID_RE = re.compile(r"/\d+")


def _normalise_path(path: str) -> str:
    return _ID_RE.sub("/{id}", path)


@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    if request.url.path.startswith("/metrics"):
        return await call_next(request)
    active_connections.labels(version=SERVICE_VERSION).inc()
    start_time = time.perf_counter()
    status_code = 500
    try:
        response: Response = await call_next(request)
        status_code = response.status_code
        return response
    except Exception:
        raise
    finally:
        duration = time.perf_counter() - start_time
        endpoint = _normalise_path(request.url.path)
        http_requests_total.labels(
            method=request.method, endpoint=endpoint, status=str(status_code), version=SERVICE_VERSION
        ).inc()
        http_request_duration_seconds.labels(
            method=request.method, endpoint=endpoint, version=SERVICE_VERSION
        ).observe(duration)
        active_connections.labels(version=SERVICE_VERSION).dec()

DATA_DIR = os.getenv("DATA_DIR", "/data")
DB_PATH = os.path.join(DATA_DIR, "orders.parquet")
PRODUCTS_SERVICE_URL = os.getenv(
    "PRODUCTS_SERVICE_URL", "http://products-service:8080"
)


class OrderCreate(BaseModel):
    product_id: int
    quantity: int
    customer_name: str


SEED_DATA = [
    (1, 1, "Wireless Mouse", 2, 29.99, 59.98, "Alice Johnson", "completed", "2024-01-15T10:30:00+00:00"),
    (2, 4, "Standing Desk", 1, 399.99, 399.99, "Bob Smith", "completed", "2024-01-16T14:20:00+00:00"),
    (3, 2, "Mechanical Keyboard", 1, 89.99, 89.99, "Carol Davis", "completed", "2024-01-18T09:15:00+00:00"),
    (4, 8, "Noise-Cancelling Headphones", 1, 199.99, 199.99, "Dave Wilson", "pending", "2024-01-20T11:45:00+00:00"),
    (5, 3, "USB-C Hub", 3, 49.99, 149.97, "Eve Martinez", "completed", "2024-01-22T16:00:00+00:00"),
    (6, 6, "Webcam HD", 2, 59.99, 119.98, "Frank Brown", "cancelled", "2024-01-25T08:30:00+00:00"),
    (7, 9, "Ergonomic Chair", 1, 549.99, 549.99, "Grace Lee", "completed", "2024-02-01T13:10:00+00:00"),
    (8, 5, "Monitor Arm", 2, 79.99, 159.98, "Hank Taylor", "pending", "2024-02-03T10:00:00+00:00"),
    (9, 12, "Wireless Charger", 4, 24.99, 99.96, "Ivy Chen", "completed", "2024-02-05T15:30:00+00:00"),
    (10, 7, "Desk Lamp", 1, 34.99, 34.99, "Jack Anderson", "completed", "2024-02-08T09:45:00+00:00"),
    (11, 10, "Laptop Stand", 1, 44.99, 44.99, "Karen White", "cancelled", "2024-02-10T12:20:00+00:00"),
    (12, 11, "Cable Management Kit", 5, 19.99, 99.95, "Leo Harris", "completed", "2024-02-12T14:00:00+00:00"),
    (13, 1, "Wireless Mouse", 1, 29.99, 29.99, "Mia Clark", "pending", "2024-02-15T11:30:00+00:00"),
    (14, 2, "Mechanical Keyboard", 2, 89.99, 179.98, "Noah Lewis", "completed", "2024-02-18T16:45:00+00:00"),
    (15, 3, "USB-C Hub", 1, 49.99, 49.99, "Olivia Robinson", "completed", "2024-02-20T10:15:00+00:00"),
]


def seed(conn):
    for row in SEED_DATA:
        conn.execute("INSERT INTO orders VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", list(row))
    save(conn)


def get_connection():
    conn = duckdb.connect()
    if os.path.exists(DB_PATH):
        with duckdb_query_duration_seconds.labels(query_type="init_read_parquet", version=SERVICE_VERSION).time():
            conn.execute(
                "CREATE TABLE IF NOT EXISTS orders AS SELECT * FROM read_parquet(?)",
                [DB_PATH],
            )
        if conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 0:
            seed(conn)
    else:
        with duckdb_query_duration_seconds.labels(query_type="init_create_table", version=SERVICE_VERSION).time():
            conn.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    id INTEGER,
                    product_id INTEGER,
                    product_name VARCHAR,
                    quantity INTEGER,
                    unit_price DOUBLE,
                    total_price DOUBLE,
                    customer_name VARCHAR,
                    status VARCHAR,
                    created_at VARCHAR
                )
            """)
        seed(conn)
    return conn


def save(conn):
    with duckdb_query_duration_seconds.labels(query_type="save_parquet", version=SERVICE_VERSION).time():
        conn.execute(f"COPY orders TO '{DB_PATH}' (FORMAT PARQUET)")


def row_to_dict(r):
    return {
        "id": r[0],
        "product_id": r[1],
        "product_name": r[2],
        "quantity": r[3],
        "unit_price": r[4],
        "total_price": r[5],
        "customer_name": r[6],
        "status": r[7],
        "created_at": r[8],
    }


@app.get("/healthz")
def healthz():
    return {"status": "ok", "version": SERVICE_VERSION}


@app.get("/ready")
def ready():
    try:
        conn = get_connection()
        conn.close()
        return {"status": "ready"}
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@app.get("/orders/stats")
def order_stats():
    conn = get_connection()
    with duckdb_query_duration_seconds.labels(query_type="stats_count", version=SERVICE_VERSION).time():
        total = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
        revenue = conn.execute(
            "SELECT COALESCE(SUM(total_price), 0) FROM orders"
        ).fetchone()[0]
    with duckdb_query_duration_seconds.labels(query_type="stats_by_status", version=SERVICE_VERSION).time():
        by_status = conn.execute(
            "SELECT status, COUNT(*) as count FROM orders GROUP BY status ORDER BY status"
        ).fetchall()
    conn.close()
    return {
        "total_orders": total,
        "total_revenue": round(revenue, 2),
        "orders_by_status": {row[0]: row[1] for row in by_status},
    }


@app.get("/orders")
def list_orders():
    conn = get_connection()
    with duckdb_query_duration_seconds.labels(query_type="select_all", version=SERVICE_VERSION).time():
        rows = conn.execute(
            "SELECT id, product_id, product_name, quantity, unit_price, "
            "total_price, customer_name, status, created_at "
            "FROM orders ORDER BY id"
        ).fetchall()
    conn.close()
    return [row_to_dict(r) for r in rows]


@app.get("/orders/{order_id}")
def get_order(order_id: int):
    conn = get_connection()
    with duckdb_query_duration_seconds.labels(query_type="select_by_id", version=SERVICE_VERSION).time():
        rows = conn.execute(
            "SELECT id, product_id, product_name, quantity, unit_price, "
            "total_price, customer_name, status, created_at "
            "FROM orders WHERE id = ?",
            [order_id],
        ).fetchall()
    conn.close()
    if not rows:
        raise HTTPException(status_code=404, detail="Order not found")
    return row_to_dict(rows[0])


@app.post("/orders")
def create_order(order: OrderCreate, user: dict | None = Depends(get_current_user)):
    # Validate product and get price from Products Service
    try:
        resp = httpx.get(
            f"{PRODUCTS_SERVICE_URL}/products/{order.product_id}", timeout=5.0
        )
        resp.raise_for_status()
        product = resp.json()
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            raise HTTPException(
                status_code=400,
                detail=f"Product with id {order.product_id} not found",
            )
        raise HTTPException(
            status_code=502, detail="Products service returned an error"
        )
    except httpx.RequestError:
        raise HTTPException(
            status_code=502, detail="Unable to reach products service"
        )

    product_name = product["name"]
    unit_price = product["price"]
    total_price = round(unit_price * order.quantity, 2)
    created_at = datetime.now(timezone.utc).isoformat()

    conn = get_connection()
    max_id = conn.execute("SELECT COALESCE(MAX(id), 0) FROM orders").fetchone()[0]
    new_id = max_id + 1
    with duckdb_query_duration_seconds.labels(query_type="insert", version=SERVICE_VERSION).time():
        conn.execute(
            "INSERT INTO orders VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                new_id,
                order.product_id,
                product_name,
                order.quantity,
                unit_price,
                total_price,
                order.customer_name,
                "pending",
                created_at,
            ],
        )
    save(conn)
    conn.close()
    return {
        "id": new_id,
        "product_id": order.product_id,
        "product_name": product_name,
        "quantity": order.quantity,
        "unit_price": unit_price,
        "total_price": total_price,
        "customer_name": order.customer_name,
        "status": "pending",
        "created_at": created_at,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8080")))
