import os
import re
import time
from datetime import datetime, timezone

import duckdb
import httpx
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import Counter, Gauge, Histogram, make_asgi_app

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

app = FastAPI(title="Analytics Service")

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
    active_connections.inc()
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
            method=request.method, endpoint=endpoint, status=str(status_code)
        ).inc()
        http_request_duration_seconds.labels(
            method=request.method, endpoint=endpoint
        ).observe(duration)
        active_connections.dec()

DATA_DIR = os.getenv("DATA_DIR", "/data")
CACHE_PATH = os.path.join(DATA_DIR, "analytics_cache.parquet")
PORT = int(os.getenv("PORT", "8080"))
PRODUCTS_SERVICE_URL = os.getenv(
    "PRODUCTS_SERVICE_URL", "http://products-service:8080"
)
ORDERS_SERVICE_URL = os.getenv(
    "ORDERS_SERVICE_URL", "http://orders-service:8080"
)

HTTP_TIMEOUT = 10.0

KEYCLOAK_URL = os.getenv("KEYCLOAK_URL", "")
KEYCLOAK_REALM = os.getenv("KEYCLOAK_REALM", "shopinsights")
KEYCLOAK_CLIENT_ID = os.getenv("KEYCLOAK_CLIENT_ID", "")
KEYCLOAK_CLIENT_SECRET = os.getenv("KEYCLOAK_CLIENT_SECRET", "")

_token_cache: dict | None = None


# ---------------------------------------------------------------------------
# Service-to-service token (client credentials grant)
# ---------------------------------------------------------------------------

def _get_service_token() -> str | None:
    """Acquire a token via client credentials grant, with caching."""
    global _token_cache
    if not (KEYCLOAK_URL and KEYCLOAK_CLIENT_ID and KEYCLOAK_CLIENT_SECRET):
        return None

    if _token_cache and _token_cache["expires_at"] > time.time():
        return _token_cache["access_token"]

    token_url = (
        f"{KEYCLOAK_URL}/realms/{KEYCLOAK_REALM}"
        "/protocol/openid-connect/token"
    )
    resp = httpx.post(
        token_url,
        data={
            "grant_type": "client_credentials",
            "client_id": KEYCLOAK_CLIENT_ID,
            "client_secret": KEYCLOAK_CLIENT_SECRET,
        },
        timeout=10.0,
    )
    resp.raise_for_status()
    data = resp.json()
    _token_cache = {
        "access_token": data["access_token"],
        "expires_at": time.time() + data.get("expires_in", 300) - 30,
    }
    return _token_cache["access_token"]


def _auth_headers() -> dict:
    """Return Authorization header if service token is available."""
    token = _get_service_token()
    if token:
        return {"Authorization": f"Bearer {token}"}
    return {}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def fetch_products() -> list[dict]:
    """Fetch all products from the Products Service."""
    resp = httpx.get(
        f"{PRODUCTS_SERVICE_URL}/products",
        headers=_auth_headers(),
        timeout=HTTP_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


def fetch_orders() -> list[dict]:
    """Fetch all orders from the Orders Service."""
    resp = httpx.get(
        f"{ORDERS_SERVICE_URL}/orders",
        headers=_auth_headers(),
        timeout=HTTP_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


def fetch_order_stats() -> dict:
    """Fetch aggregated order stats from the Orders Service."""
    resp = httpx.get(
        f"{ORDERS_SERVICE_URL}/orders/stats",
        headers=_auth_headers(),
        timeout=HTTP_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


def build_orders_table(conn, orders: list[dict]):
    """Load orders into an in-memory DuckDB table."""
    with duckdb_query_duration_seconds.labels(query_type="build_orders_table").time():
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
        for o in orders:
            conn.execute(
                "INSERT INTO orders VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    o["id"],
                    o["product_id"],
                    o.get("product_name", ""),
                    o["quantity"],
                    o.get("unit_price", 0),
                    o["total_price"],
                    o.get("customer_name", ""),
                    o.get("status", ""),
                    o.get("created_at", ""),
                ],
            )


def build_products_table(conn, products: list[dict]):
    """Load products into an in-memory DuckDB table."""
    with duckdb_query_duration_seconds.labels(query_type="build_products_table").time():
        conn.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER,
                name VARCHAR,
                category VARCHAR,
                price DOUBLE,
                stock INTEGER
            )
        """)
        for p in products:
            conn.execute(
                "INSERT INTO products VALUES (?, ?, ?, ?, ?)",
                [p["id"], p["name"], p["category"], p["price"], p["stock"]],
            )


def cache_revenue(conn):
    """Write the current revenue-by-month aggregation to a Parquet cache."""
    try:
        with duckdb_query_duration_seconds.labels(query_type="cache_revenue").time():
            conn.execute(f"""
                COPY (
                    SELECT
                        strftime(TRY_CAST(created_at AS TIMESTAMP), '%Y-%m') AS month,
                        SUM(total_price) AS revenue
                    FROM orders
                    WHERE TRY_CAST(created_at AS TIMESTAMP) IS NOT NULL
                    GROUP BY month
                    ORDER BY month
                ) TO '{CACHE_PATH}' (FORMAT PARQUET)
            """)
    except Exception:
        pass  # caching is best-effort


# ---------------------------------------------------------------------------
# Health endpoints
# ---------------------------------------------------------------------------

@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/ready")
def ready():
    """Readiness probe -- verify upstream services are reachable."""
    errors = []
    try:
        r = httpx.get(f"{PRODUCTS_SERVICE_URL}/healthz", timeout=5.0)
        r.raise_for_status()
    except Exception as e:
        errors.append(f"products-service: {e}")

    try:
        r = httpx.get(f"{ORDERS_SERVICE_URL}/healthz", timeout=5.0)
        r.raise_for_status()
    except Exception as e:
        errors.append(f"orders-service: {e}")

    if errors:
        raise HTTPException(status_code=503, detail="; ".join(errors))

    return {"status": "ready"}


# ---------------------------------------------------------------------------
# Analytics endpoints
# ---------------------------------------------------------------------------

@app.get("/analytics/revenue")
def revenue():
    """Total revenue, revenue by category, and revenue by month."""
    try:
        orders = fetch_orders()
        products = fetch_products()
    except httpx.RequestError as e:
        raise HTTPException(
            status_code=502, detail=f"Unable to reach upstream service: {e}"
        )
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=502,
            detail=f"Upstream service error: {e.response.status_code}",
        )

    conn = duckdb.connect()
    build_orders_table(conn, orders)
    build_products_table(conn, products)

    with duckdb_query_duration_seconds.labels(query_type="revenue_total").time():
        total = conn.execute(
            "SELECT COALESCE(SUM(total_price), 0) FROM orders"
        ).fetchone()[0]

    with duckdb_query_duration_seconds.labels(query_type="revenue_by_category").time():
        by_category_rows = conn.execute("""
            SELECT p.category, ROUND(SUM(o.total_price), 2) AS revenue
            FROM orders o
            JOIN products p ON o.product_id = p.id
            GROUP BY p.category
            ORDER BY revenue DESC
        """).fetchall()

    with duckdb_query_duration_seconds.labels(query_type="revenue_by_month").time():
        by_month_rows = conn.execute("""
            SELECT
                strftime(TRY_CAST(created_at AS TIMESTAMP), '%Y-%m') AS month,
                ROUND(SUM(total_price), 2) AS revenue
            FROM orders
            WHERE TRY_CAST(created_at AS TIMESTAMP) IS NOT NULL
            GROUP BY month
            ORDER BY month
        """).fetchall()

    cache_revenue(conn)
    conn.close()

    return {
        "total_revenue": round(total, 2),
        "revenue_by_category": [
            {"category": r[0], "revenue": r[1]} for r in by_category_rows
        ],
        "revenue_by_month": [
            {"month": r[0], "revenue": r[1]} for r in by_month_rows
        ],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/analytics/top-products")
def top_products():
    """Top 10 products by total revenue and by order count."""
    try:
        orders = fetch_orders()
        products = fetch_products()
    except httpx.RequestError as e:
        raise HTTPException(
            status_code=502, detail=f"Unable to reach upstream service: {e}"
        )
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=502,
            detail=f"Upstream service error: {e.response.status_code}",
        )

    conn = duckdb.connect()
    build_orders_table(conn, orders)
    build_products_table(conn, products)

    with duckdb_query_duration_seconds.labels(query_type="top_by_revenue").time():
        by_revenue = conn.execute("""
            SELECT
                p.id,
                p.name,
                p.category,
                COUNT(o.id) AS order_count,
                CAST(SUM(o.quantity) AS INTEGER) AS total_quantity,
                ROUND(SUM(o.total_price), 2) AS total_revenue
            FROM orders o
            JOIN products p ON o.product_id = p.id
            GROUP BY p.id, p.name, p.category
            ORDER BY total_revenue DESC
            LIMIT 10
        """).fetchall()

    with duckdb_query_duration_seconds.labels(query_type="top_by_orders").time():
        by_order_count = conn.execute("""
            SELECT
                p.id,
                p.name,
                p.category,
                COUNT(o.id) AS order_count,
                CAST(SUM(o.quantity) AS INTEGER) AS total_quantity,
                ROUND(SUM(o.total_price), 2) AS total_revenue
            FROM orders o
            JOIN products p ON o.product_id = p.id
            GROUP BY p.id, p.name, p.category
            ORDER BY order_count DESC
            LIMIT 10
        """).fetchall()

    conn.close()

    def format_row(r):
        return {
            "product_id": r[0],
            "name": r[1],
            "category": r[2],
            "order_count": r[3],
            "total_quantity": r[4],
            "total_revenue": r[5],
        }

    return {
        "by_revenue": [format_row(r) for r in by_revenue],
        "by_order_count": [format_row(r) for r in by_order_count],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/analytics/summary")
def summary():
    """Dashboard summary: total products, total orders, total revenue, avg order value."""
    errors = {}

    # Fetch product count
    total_products = 0
    try:
        products = fetch_products()
        total_products = len(products)
    except Exception as e:
        errors["products"] = str(e)

    # Fetch order stats
    total_orders = 0
    total_revenue = 0.0
    avg_order_value = 0.0
    try:
        stats = fetch_order_stats()
        total_orders = stats.get("total_orders", 0)
        total_revenue = stats.get("total_revenue", 0.0)
        avg_order_value = (
            round(total_revenue / total_orders, 2) if total_orders > 0 else 0.0
        )
    except Exception as e:
        errors["orders"] = str(e)

    if errors:
        # Return partial data with warnings rather than failing entirely
        return {
            "total_products": total_products,
            "total_orders": total_orders,
            "total_revenue": total_revenue,
            "average_order_value": avg_order_value,
            "warnings": errors,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    return {
        "total_products": total_products,
        "total_orders": total_orders,
        "total_revenue": total_revenue,
        "average_order_value": avg_order_value,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=PORT)
