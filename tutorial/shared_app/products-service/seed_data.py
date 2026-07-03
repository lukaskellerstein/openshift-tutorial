"""Generate sample products.parquet for the tutorial."""
import duckdb

conn = duckdb.connect()
conn.execute("""
    CREATE TABLE products (
        id INTEGER,
        name VARCHAR,
        category VARCHAR,
        price DOUBLE,
        stock INTEGER
    )
""")
conn.execute("""
    INSERT INTO products VALUES
    (1, 'Wireless Mouse', 'Electronics', 29.99, 150),
    (2, 'Mechanical Keyboard', 'Electronics', 89.99, 75),
    (3, 'USB-C Hub', 'Electronics', 49.99, 200),
    (4, 'Standing Desk', 'Furniture', 399.99, 30),
    (5, 'Monitor Arm', 'Furniture', 79.99, 90),
    (6, 'Webcam HD', 'Electronics', 59.99, 120),
    (7, 'Desk Lamp', 'Furniture', 34.99, 180),
    (8, 'Noise-Cancelling Headphones', 'Electronics', 199.99, 60),
    (9, 'Ergonomic Chair', 'Furniture', 549.99, 25),
    (10, 'Laptop Stand', 'Accessories', 44.99, 140),
    (11, 'Cable Management Kit', 'Accessories', 19.99, 300),
    (12, 'Wireless Charger', 'Electronics', 24.99, 220)
""")
conn.execute("COPY products TO 'data/products.parquet' (FORMAT PARQUET)")
conn.close()
print("Created data/products.parquet with 12 sample products.")
