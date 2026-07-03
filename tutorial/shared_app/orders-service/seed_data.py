"""Generate sample orders.parquet for the tutorial."""
import duckdb

conn = duckdb.connect()
conn.execute("""
    CREATE TABLE orders (
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
conn.execute("""
    INSERT INTO orders VALUES
    (1, 1, 'Wireless Mouse', 2, 29.99, 59.98, 'Alice Johnson', 'completed', '2024-01-15T10:30:00+00:00'),
    (2, 4, 'Standing Desk', 1, 399.99, 399.99, 'Bob Smith', 'completed', '2024-01-16T14:20:00+00:00'),
    (3, 2, 'Mechanical Keyboard', 1, 89.99, 89.99, 'Carol Davis', 'completed', '2024-01-18T09:15:00+00:00'),
    (4, 8, 'Noise-Cancelling Headphones', 1, 199.99, 199.99, 'Dave Wilson', 'pending', '2024-01-20T11:45:00+00:00'),
    (5, 3, 'USB-C Hub', 3, 49.99, 149.97, 'Eve Martinez', 'completed', '2024-01-22T16:00:00+00:00'),
    (6, 6, 'Webcam HD', 2, 59.99, 119.98, 'Frank Brown', 'cancelled', '2024-01-25T08:30:00+00:00'),
    (7, 9, 'Ergonomic Chair', 1, 549.99, 549.99, 'Grace Lee', 'completed', '2024-02-01T13:10:00+00:00'),
    (8, 5, 'Monitor Arm', 2, 79.99, 159.98, 'Hank Taylor', 'pending', '2024-02-03T10:00:00+00:00'),
    (9, 12, 'Wireless Charger', 4, 24.99, 99.96, 'Ivy Chen', 'completed', '2024-02-05T15:30:00+00:00'),
    (10, 7, 'Desk Lamp', 1, 34.99, 34.99, 'Jack Anderson', 'completed', '2024-02-08T09:45:00+00:00'),
    (11, 10, 'Laptop Stand', 1, 44.99, 44.99, 'Karen White', 'cancelled', '2024-02-10T12:20:00+00:00'),
    (12, 11, 'Cable Management Kit', 5, 19.99, 99.95, 'Leo Harris', 'completed', '2024-02-12T14:00:00+00:00'),
    (13, 1, 'Wireless Mouse', 1, 29.99, 29.99, 'Mia Clark', 'pending', '2024-02-15T11:30:00+00:00'),
    (14, 2, 'Mechanical Keyboard', 2, 89.99, 179.98, 'Noah Lewis', 'completed', '2024-02-18T16:45:00+00:00'),
    (15, 3, 'USB-C Hub', 1, 49.99, 49.99, 'Olivia Robinson', 'completed', '2024-02-20T10:15:00+00:00')
""")
conn.execute("COPY orders TO 'data/orders.parquet' (FORMAT PARQUET)")
conn.close()
print("Created data/orders.parquet with 15 sample orders.")
