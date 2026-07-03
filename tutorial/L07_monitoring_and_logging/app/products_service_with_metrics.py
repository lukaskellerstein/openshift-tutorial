"""Products Service with Prometheus metrics instrumentation.

This is the same Products Service from shared_app/products-service/app.py,
but instrumented with prometheus_client to expose custom metrics at /metrics.

Metrics exposed:
  - http_requests_total (Counter): Total HTTP requests by method, endpoint, status
  - http_request_duration_seconds (Histogram): Request latency by method, endpoint
  - duckdb_query_duration_seconds (Histogram): DuckDB query latency by query_type
  - active_connections (Gauge): Number of currently active HTTP connections

Requirements (add to pyproject.toml dependencies):
  "prometheus_client>=0.21.0"
"""

import os
import time

import duckdb
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from prometheus_client import (
    Counter,
    Gauge,
    Histogram,
    make_asgi_app,
)

# ---------------------------------------------------------------------------
# Prometheus metrics
# ---------------------------------------------------------------------------

http_requests_total = Counter(
    "http_requests_total",
    "Total number of HTTP requests",
    ["method", "endpoint", "status"],
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)

duckdb_query_duration_seconds = Histogram(
    "duckdb_query_duration_seconds",
    "DuckDB query duration in seconds",
    ["query_type"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0),
)

active_connections = Gauge(
    "active_connections",
    "Number of currently active HTTP connections",
)

# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------

app = FastAPI(title="Products Service")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount the Prometheus metrics endpoint at /metrics
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)

DATA_DIR = os.getenv("DATA_DIR", "/data")
DB_PATH = os.path.join(DATA_DIR, "products.parquet")


# ---------------------------------------------------------------------------
# Metrics middleware
# ---------------------------------------------------------------------------

@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    """Track request count, duration, and active connections for every endpoint."""
    # Skip the /metrics path itself to avoid self-instrumentation noise
    if request.url.path.startswith("/metrics"):
        return await call_next(request)

    active_connections.inc()
    start_time = time.perf_counter()

    try:
        response: Response = await call_next(request)
        status_code = response.status_code
    except Exception:
        status_code = 500
        raise
    finally:
        duration = time.perf_counter() - start_time

        # Normalise the path so /products/42 becomes /products/{id}
        endpoint = _normalise_path(request.url.path)

        http_requests_total.labels(
            method=request.method,
            endpoint=endpoint,
            status=str(status_code),
        ).inc()

        http_request_duration_seconds.labels(
            method=request.method,
            endpoint=endpoint,
        ).observe(duration)

        active_connections.dec()

    return response


def _normalise_path(path: str) -> str:
    """Collapse numeric path segments into placeholders to keep cardinality low."""
    parts = path.strip("/").split("/")
    normalised = []
    for part in parts:
        if part.isdigit():
            normalised.append("{id}")
        else:
            normalised.append(part)
    return "/" + "/".join(normalised) if normalised else "/"


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

class Product(BaseModel):
    name: str
    category: str
    price: float
    stock: int


# ---------------------------------------------------------------------------
# Database helpers (with query-duration instrumentation)
# ---------------------------------------------------------------------------

def get_connection():
    conn = duckdb.connect()
    if os.path.exists(DB_PATH):
        with duckdb_query_duration_seconds.labels(query_type="init_read_parquet").time():
            conn.execute(
                "CREATE TABLE IF NOT EXISTS products AS SELECT * FROM read_parquet(?)",
                [DB_PATH],
            )
    else:
        with duckdb_query_duration_seconds.labels(query_type="init_create_table").time():
            conn.execute("""
                CREATE TABLE IF NOT EXISTS products (
                    id INTEGER,
                    name VARCHAR,
                    category VARCHAR,
                    price DOUBLE,
                    stock INTEGER
                )
            """)
    return conn


def save(conn):
    with duckdb_query_duration_seconds.labels(query_type="save_parquet").time():
        conn.execute(f"COPY products TO '{DB_PATH}' (FORMAT PARQUET)")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/healthz")
def healthz():
    return {"status": "ok"}


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
    with duckdb_query_duration_seconds.labels(query_type="select_all").time():
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
    with duckdb_query_duration_seconds.labels(query_type="select_by_id").time():
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
def create_product(product: Product):
    conn = get_connection()
    with duckdb_query_duration_seconds.labels(query_type="insert").time():
        max_id = conn.execute("SELECT COALESCE(MAX(id), 0) FROM products").fetchone()[0]
        new_id = max_id + 1
        conn.execute(
            "INSERT INTO products VALUES (?, ?, ?, ?, ?)",
            [new_id, product.name, product.category, product.price, product.stock],
        )
    save(conn)
    conn.close()
    return {"id": new_id, **product.model_dump()}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8080")))
