import os
from datetime import datetime, timezone

import duckdb
import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="Orders Service")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DATA_DIR = os.getenv("DATA_DIR", "/data")
DB_PATH = os.path.join(DATA_DIR, "orders.parquet")
PRODUCTS_SERVICE_URL = os.getenv(
    "PRODUCTS_SERVICE_URL", "http://products-service:8080"
)


class OrderCreate(BaseModel):
    product_id: int
    quantity: int
    customer_name: str


def get_connection():
    conn = duckdb.connect()
    if os.path.exists(DB_PATH):
        conn.execute(
            "CREATE TABLE IF NOT EXISTS orders AS SELECT * FROM read_parquet(?)",
            [DB_PATH],
        )
    else:
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
    return conn


def save(conn):
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
    return {"status": "ok"}


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
    total = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    revenue = conn.execute(
        "SELECT COALESCE(SUM(total_price), 0) FROM orders"
    ).fetchone()[0]
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
def create_order(order: OrderCreate):
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
