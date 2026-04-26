"""Create a SQLite demo database with realistic e-commerce data.

Usage:
    python scripts/seed_sqlite_demo.py [output_path]

Default output: data/demo.sqlite
"""

from __future__ import annotations

import random
import sqlite3
import sys
from datetime import date, datetime, timedelta
from pathlib import Path


SCHEMA_SQL = """
DROP TABLE IF EXISTS fact_sales;
DROP TABLE IF EXISTS dim_date;
DROP TABLE IF EXISTS dim_product;
DROP TABLE IF EXISTS dim_customer;

CREATE TABLE dim_customer (
    customer_id TEXT PRIMARY KEY,
    country TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE dim_product (
    product_id TEXT PRIMARY KEY,
    description TEXT NOT NULL,
    category TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE dim_date (
    date_id TEXT PRIMARY KEY,
    day INTEGER NOT NULL,
    month INTEGER NOT NULL,
    quarter INTEGER NOT NULL,
    year INTEGER NOT NULL,
    week_of_year INTEGER NOT NULL,
    month_name TEXT NOT NULL,
    day_name TEXT NOT NULL
);

CREATE TABLE fact_sales (
    sale_id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_no TEXT NOT NULL,
    invoice_line_no INTEGER NOT NULL,
    customer_id TEXT NOT NULL REFERENCES dim_customer(customer_id),
    product_id TEXT NOT NULL REFERENCES dim_product(product_id),
    date_id TEXT NOT NULL REFERENCES dim_date(date_id),
    invoice_timestamp TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price REAL NOT NULL,
    total_amount REAL NOT NULL,
    UNIQUE (invoice_no, invoice_line_no)
);

CREATE INDEX idx_fact_customer ON fact_sales(customer_id);
CREATE INDEX idx_fact_product ON fact_sales(product_id);
CREATE INDEX idx_fact_date ON fact_sales(date_id);
"""


COUNTRIES = [
    "United Kingdom", "Germany", "France", "Spain", "Netherlands",
    "Italy", "Belgium", "Switzerland", "Australia", "USA",
]

PRODUCTS = [
    ("P001", "Wireless Headphones", "Electronics", 89.99),
    ("P002", "USB-C Charger 65W", "Electronics", 29.99),
    ("P003", "Mechanical Keyboard", "Electronics", 149.99),
    ("P004", "4K Webcam", "Electronics", 119.99),
    ("P005", "Smart Watch Series X", "Electronics", 249.99),
    ("P006", "Coffee Mug Ceramic", "Home", 12.99),
    ("P007", "Ergonomic Office Chair", "Furniture", 399.99),
    ("P008", "LED Desk Lamp", "Home", 39.99),
    ("P009", "Standing Desk Adjustable", "Furniture", 549.99),
    ("P010", "Notebook A5 Hardcover", "Stationery", 9.99),
    ("P011", "Fountain Pen Premium", "Stationery", 79.99),
    ("P012", "Backpack Travel 30L", "Accessories", 89.99),
    ("P013", "Yoga Mat Pro", "Sports", 49.99),
    ("P014", "Water Bottle Insulated", "Sports", 24.99),
    ("P015", "Bluetooth Speaker", "Electronics", 69.99),
    ("P016", "Wireless Mouse", "Electronics", 39.99),
    ("P017", "Monitor Stand Wood", "Furniture", 59.99),
    ("P018", "Plant Pot Set", "Home", 34.99),
    ("P019", "Cable Organizer Kit", "Accessories", 14.99),
    ("P020", "Power Bank 20000mAh", "Electronics", 49.99),
]


def populate_dim_date(cur: sqlite3.Cursor, start: date, end: date) -> None:
    current = start
    rows = []
    month_names = ["January","February","March","April","May","June",
                   "July","August","September","October","November","December"]
    day_names = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
    while current <= end:
        rows.append((
            current.isoformat(),
            current.day,
            current.month,
            (current.month - 1) // 3 + 1,
            current.year,
            int(current.strftime("%V")),
            month_names[current.month - 1],
            day_names[current.weekday()],
        ))
        current += timedelta(days=1)
    cur.executemany(
        "INSERT INTO dim_date(date_id, day, month, quarter, year, week_of_year, month_name, day_name) "
        "VALUES (?,?,?,?,?,?,?,?)",
        rows,
    )


def populate_customers(cur: sqlite3.Cursor, n: int = 50) -> list[str]:
    ids = []
    rows = []
    for i in range(1, n + 1):
        cid = f"C{i:04d}"
        country = random.choice(COUNTRIES)
        rows.append((cid, country))
        ids.append(cid)
    cur.executemany("INSERT INTO dim_customer(customer_id, country) VALUES (?,?)", rows)
    return ids


def populate_products(cur: sqlite3.Cursor) -> list[tuple[str, float]]:
    cur.executemany(
        "INSERT INTO dim_product(product_id, description, category) VALUES (?,?,?)",
        [(p[0], p[1], p[2]) for p in PRODUCTS],
    )
    return [(p[0], p[3]) for p in PRODUCTS]


def populate_sales(
    cur: sqlite3.Cursor,
    customers: list[str],
    products: list[tuple[str, float]],
    start: date,
    end: date,
    n_invoices: int = 1500,
) -> None:
    rng = random.Random(42)
    span_days = (end - start).days
    rows = []
    for inv_idx in range(1, n_invoices + 1):
        invoice_no = f"INV{inv_idx:06d}"
        d = start + timedelta(days=rng.randint(0, span_days))
        ts = datetime.combine(d, datetime.min.time()) + timedelta(hours=rng.randint(8, 20))
        cust = rng.choice(customers)
        n_lines = rng.randint(1, 5)
        line_products = rng.sample(products, k=min(n_lines, len(products)))
        for line_no, (pid, base_price) in enumerate(line_products, start=1):
            qty = rng.randint(1, 10)
            price = round(base_price * rng.uniform(0.85, 1.15), 2)
            total = round(qty * price, 2)
            rows.append((
                invoice_no, line_no, cust, pid,
                d.isoformat(), ts.isoformat(sep=" "),
                qty, price, total,
            ))
    cur.executemany(
        "INSERT INTO fact_sales(invoice_no, invoice_line_no, customer_id, product_id, date_id, "
        "invoice_timestamp, quantity, unit_price, total_amount) VALUES (?,?,?,?,?,?,?,?,?)",
        rows,
    )


def main() -> None:
    out_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/demo.sqlite")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists():
        out_path.unlink()

    conn = sqlite3.connect(str(out_path))
    try:
        conn.executescript(SCHEMA_SQL)
        cur = conn.cursor()

        end = date.today()
        start = end - timedelta(days=365)

        populate_dim_date(cur, start, end)
        customers = populate_customers(cur)
        products = populate_products(cur)
        populate_sales(cur, customers, products, start, end, n_invoices=1500)

        conn.commit()

        cur.execute("SELECT COUNT(*) FROM dim_customer")
        cust_count = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM dim_product")
        prod_count = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM dim_date")
        date_count = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM fact_sales")
        sales_count = cur.fetchone()[0]

        print(f"Seed complete: {out_path}")
        print(f"  dim_customer: {cust_count} rows")
        print(f"  dim_product:  {prod_count} rows")
        print(f"  dim_date:     {date_count} rows")
        print(f"  fact_sales:   {sales_count} rows")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
