import os
import duckdb
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="Products Service")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

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


def get_connection():
    conn = duckdb.connect()
    if os.path.exists(DB_PATH):
        conn.execute(
            "CREATE TABLE IF NOT EXISTS products AS SELECT * FROM read_parquet(?)",
            [DB_PATH],
        )
    else:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER,
                name VARCHAR,
                category VARCHAR,
                price DOUBLE,
                stock INTEGER
            )
        """)
        for row in SEED_DATA:
            conn.execute("INSERT INTO products VALUES (?, ?, ?, ?, ?)", list(row))
        save(conn)
    return conn


def save(conn):
    conn.execute(f"COPY products TO '{DB_PATH}' (FORMAT PARQUET)")


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
    max_id = conn.execute("SELECT COALESCE(MAX(id), 0) FROM products").fetchone()[0]
    new_id = max_id + 1
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
