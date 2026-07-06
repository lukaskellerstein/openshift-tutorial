import os
import re
import time

import duckdb
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

app = FastAPI(title="Products Service")

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
DB_PATH = os.path.join(DATA_DIR, "products.parquet")


class Product(BaseModel):
    name: str
    category: str
    price: float
    stock: int


SEED_DATA = [
    (1, "Wireless Mouse", "Electronics", 29.99, 150),
    (2, "Mechanical Keyboard", "Electronics", 89.99, 75),
    (3, "USB-C Hub", "Electronics", 49.99, 200),
    (4, "Standing Desk", "Furniture", 399.99, 30),
    (5, "Monitor Arm", "Furniture", 79.99, 90),
    (6, "Webcam HD", "Electronics", 59.99, 120),
    (7, "Desk Lamp", "Furniture", 34.99, 180),
    (8, "Noise-Cancelling Headphones", "Electronics", 199.99, 60),
    (9, "Ergonomic Chair", "Furniture", 549.99, 25),
    (10, "Laptop Stand", "Accessories", 44.99, 140),
    (11, "Cable Management Kit", "Accessories", 19.99, 300),
    (12, "Wireless Charger", "Electronics", 24.99, 220),
]


def seed(conn):
    for row in SEED_DATA:
        conn.execute("INSERT INTO products VALUES (?, ?, ?, ?, ?)", list(row))
    save(conn)


def get_connection():
    conn = duckdb.connect()
    if os.path.exists(DB_PATH):
        with duckdb_query_duration_seconds.labels(query_type="init_read_parquet", version=SERVICE_VERSION).time():
            conn.execute(
                "CREATE TABLE IF NOT EXISTS products AS SELECT * FROM read_parquet(?)",
                [DB_PATH],
            )
        if conn.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 0:
            seed(conn)
    else:
        with duckdb_query_duration_seconds.labels(query_type="init_create_table", version=SERVICE_VERSION).time():
            conn.execute("""
                CREATE TABLE IF NOT EXISTS products (
                    id INTEGER,
                    name VARCHAR,
                    category VARCHAR,
                    price DOUBLE,
                    stock INTEGER
                )
            """)
        seed(conn)
    return conn


def save(conn):
    with duckdb_query_duration_seconds.labels(query_type="save_parquet", version=SERVICE_VERSION).time():
        conn.execute(f"COPY products TO '{DB_PATH}' (FORMAT PARQUET)")


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


@app.get("/products")
def list_products():
    conn = get_connection()
    with duckdb_query_duration_seconds.labels(query_type="select_all", version=SERVICE_VERSION).time():
        rows = conn.execute(
            "SELECT id, name, category, price, stock FROM products ORDER BY id"
        ).fetchall()
    conn.close()
    return [
        {"id": r[0], "name": r[1], "category": r[2], "price": r[3], "stock": r[4]}
        for r in rows
    ]


@app.get("/products/{product_id}")
def get_product(product_id: int):
    conn = get_connection()
    with duckdb_query_duration_seconds.labels(query_type="select_by_id", version=SERVICE_VERSION).time():
        rows = conn.execute(
            "SELECT id, name, category, price, stock FROM products WHERE id = ?",
            [product_id],
        ).fetchall()
    conn.close()
    if not rows:
        raise HTTPException(status_code=404, detail="Product not found")
    r = rows[0]
    return {"id": r[0], "name": r[1], "category": r[2], "price": r[3], "stock": r[4]}


@app.post("/products")
def create_product(product: Product, user: dict | None = Depends(get_current_user)):
    conn = get_connection()
    max_id = conn.execute("SELECT COALESCE(MAX(id), 0) FROM products").fetchone()[0]
    new_id = max_id + 1
    with duckdb_query_duration_seconds.labels(query_type="insert", version=SERVICE_VERSION).time():
        conn.execute(
            "INSERT INTO products VALUES (?, ?, ?, ?, ?)",
            [new_id, product.name, product.category, product.price, product.stock],
        )
    save(conn)
    conn.close()
    return {"id": new_id, **product.model_dump()}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8080")))
