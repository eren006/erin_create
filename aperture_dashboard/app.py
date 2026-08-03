import os
import random
import sqlite3
from datetime import date, timedelta

from flask import Flask, render_template, request, jsonify

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "aperture.db")
DAYS_OF_HISTORY = 365
SEED = 20260802

app = Flask(__name__)

PRODUCTS = [
    ("Classic Tee", "Apparel", 24),
    ("Denim Jacket", "Apparel", 89),
    ("Wool Scarf", "Apparel", 34),
    ("Wireless Earbuds", "Electronics", 79),
    ("Smart Watch", "Electronics", 149),
    ("Portable Speaker", "Electronics", 59),
    ("Ceramic Mug Set", "Home", 28),
    ("Linen Throw", "Home", 45),
    ("Table Lamp", "Home", 62),
    ("Vitamin C Serum", "Beauty", 32),
    ("Clay Mask", "Beauty", 22),
    ("Hair Oil", "Beauty", 26),
    ("Yoga Mat", "Sports", 38),
    ("Resistance Bands", "Sports", 19),
    ("Water Bottle", "Sports", 24),
]

CATEGORY_WEIGHTS = {"Apparel": 0.28, "Electronics": 0.24, "Home": 0.20, "Beauty": 0.16, "Sports": 0.12}
REGIONS = ["North America", "Europe", "Asia", "Latin America"]
REGION_WEIGHTS = [0.42, 0.30, 0.20, 0.08]

PRODUCTS_BY_CATEGORY = {}
for name, cat, price in PRODUCTS:
    PRODUCTS_BY_CATEGORY.setdefault(cat, []).append((name, price))


# ---------------------------------------------------------------------------
# Seed data generation (deterministic, runs once on first startup)
# ---------------------------------------------------------------------------

def generate_orders(rng, end_date):
    orders = []
    start_date = end_date - timedelta(days=DAYS_OF_HISTORY - 1)
    total_days = DAYS_OF_HISTORY

    promo_days = set(rng.sample(range(total_days), 7))
    categories = list(CATEGORY_WEIGHTS.keys())
    category_w = list(CATEGORY_WEIGHTS.values())

    order_id = 1
    for day_index in range(total_days):
        day = start_date + timedelta(days=day_index)
        progress = day_index / max(1, total_days - 1)
        baseline = 8 + progress * 14  # grows from ~8/day to ~22/day over the year

        weekday_mult = 1.4 if day.weekday() >= 5 else 1.0
        promo = day_index in promo_days
        promo_mult = 2.4 if promo else 1.0
        noise = rng.uniform(0.75, 1.25)

        expected = baseline * weekday_mult * promo_mult * noise
        count = max(0, round(rng.gauss(expected, expected * 0.15)))

        new_customer_prob = 0.5 if promo else 0.35

        for _ in range(count):
            category = rng.choices(categories, weights=category_w, k=1)[0]
            name, base_price = rng.choice(PRODUCTS_BY_CATEGORY[category])
            region = rng.choices(REGIONS, weights=REGION_WEIGHTS, k=1)[0]
            quantity = rng.choices([1, 2, 3], weights=[0.65, 0.25, 0.10], k=1)[0]
            unit_price = round(base_price * rng.uniform(0.92, 1.08), 2)
            customer_type = "new" if rng.random() < new_customer_prob else "returning"
            revenue = round(unit_price * quantity, 2)

            orders.append((
                order_id, day.isoformat(), name, category, region,
                customer_type, quantity, unit_price, revenue,
            ))
            order_id += 1

    return orders


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY,
            order_date TEXT NOT NULL,
            product_name TEXT NOT NULL,
            category TEXT NOT NULL,
            region TEXT NOT NULL,
            customer_type TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            unit_price REAL NOT NULL,
            revenue REAL NOT NULL
        )"""
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_date ON orders(order_date)")
    count = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    if count == 0:
        rng = random.Random(SEED)
        orders = generate_orders(rng, date.today())
        conn.executemany(
            "INSERT INTO orders VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", orders
        )
        conn.commit()
    conn.close()


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ---------------------------------------------------------------------------
# Aggregation helpers
# ---------------------------------------------------------------------------

RANGE_DAYS = {"7d": 7, "30d": 30, "90d": 90, "12m": 365}


def period_bounds(range_key, anchor):
    days = RANGE_DAYS.get(range_key, 30)
    end = anchor
    start = end - timedelta(days=days - 1)
    prev_end = start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=days - 1)
    return start, end, prev_start, prev_end, days


def totals_for(conn, start, end):
    row = conn.execute(
        """SELECT COALESCE(SUM(revenue), 0) AS revenue,
                  COUNT(*) AS orders,
                  COALESCE(SUM(CASE WHEN customer_type = 'new' THEN 1 ELSE 0 END), 0) AS new_customers
           FROM orders WHERE order_date BETWEEN ? AND ?""",
        (start.isoformat(), end.isoformat()),
    ).fetchone()
    revenue = row["revenue"]
    orders = row["orders"]
    aov = (revenue / orders) if orders else 0
    new_share = (row["new_customers"] / orders * 100) if orders else 0
    return {"revenue": revenue, "orders": orders, "aov": aov, "new_share": new_share}


def pct_delta(current, previous):
    if previous == 0:
        return None
    return round((current - previous) / previous * 100, 1)


def daily_series(conn, start, end, days):
    rows = conn.execute(
        """SELECT order_date, SUM(revenue) AS revenue, COUNT(*) AS orders
           FROM orders WHERE order_date BETWEEN ? AND ?
           GROUP BY order_date ORDER BY order_date""",
        (start.isoformat(), end.isoformat()),
    ).fetchall()
    by_date = {r["order_date"]: {"revenue": r["revenue"], "orders": r["orders"]} for r in rows}

    points = []
    d = start
    while d <= end:
        v = by_date.get(d.isoformat(), {"revenue": 0, "orders": 0})
        points.append({"date": d.isoformat(), "revenue": round(v["revenue"], 2), "orders": v["orders"]})
        d += timedelta(days=1)

    if days > 120:
        bucketed = []
        for i in range(0, len(points), 7):
            chunk = points[i:i + 7]
            bucketed.append({
                "date": chunk[0]["date"],
                "revenue": round(sum(p["revenue"] for p in chunk), 2),
                "orders": sum(p["orders"] for p in chunk),
            })
        return bucketed
    return points


def sparkline(conn, end, n=14):
    start = end - timedelta(days=n - 1)
    rows = conn.execute(
        """SELECT order_date, SUM(revenue) AS revenue
           FROM orders WHERE order_date BETWEEN ? AND ?
           GROUP BY order_date ORDER BY order_date""",
        (start.isoformat(), end.isoformat()),
    ).fetchall()
    by_date = {r["order_date"]: r["revenue"] for r in rows}
    values = []
    d = start
    while d <= end:
        values.append(round(by_date.get(d.isoformat(), 0), 2))
        d += timedelta(days=1)
    return values


def category_breakdown(conn, start, end):
    rows = conn.execute(
        """SELECT category, SUM(revenue) AS revenue
           FROM orders WHERE order_date BETWEEN ? AND ?
           GROUP BY category ORDER BY revenue DESC""",
        (start.isoformat(), end.isoformat()),
    ).fetchall()
    return [{"label": r["category"], "value": round(r["revenue"], 2)} for r in rows]


def region_breakdown(conn, start, end):
    rows = conn.execute(
        """SELECT region, COUNT(*) AS orders
           FROM orders WHERE order_date BETWEEN ? AND ?
           GROUP BY region ORDER BY orders DESC""",
        (start.isoformat(), end.isoformat()),
    ).fetchall()
    return [{"label": r["region"], "value": r["orders"]} for r in rows]


def customer_mix(conn, start, end):
    rows = conn.execute(
        """SELECT customer_type, COUNT(*) AS n
           FROM orders WHERE order_date BETWEEN ? AND ?
           GROUP BY customer_type""",
        (start.isoformat(), end.isoformat()),
    ).fetchall()
    total = sum(r["n"] for r in rows) or 1
    mix = {"new": 0, "returning": 0}
    for r in rows:
        mix[r["customer_type"]] = r["n"]
    return {
        "new_pct": round(mix["new"] / total * 100, 1),
        "returning_pct": round(mix["returning"] / total * 100, 1),
    }


def top_products(conn, start, end, limit=8):
    rows = conn.execute(
        """SELECT product_name, category, SUM(quantity) AS units, SUM(revenue) AS revenue
           FROM orders WHERE order_date BETWEEN ? AND ?
           GROUP BY product_name, category ORDER BY revenue DESC LIMIT ?""",
        (start.isoformat(), end.isoformat(), limit),
    ).fetchall()
    return [
        {"name": r["product_name"], "category": r["category"], "units": r["units"], "revenue": round(r["revenue"], 2)}
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/summary")
def api_summary():
    range_key = request.args.get("range", "30d")
    if range_key not in RANGE_DAYS:
        range_key = "30d"

    conn = get_db()
    latest_row = conn.execute("SELECT MAX(order_date) AS d FROM orders").fetchone()
    anchor = date.fromisoformat(latest_row["d"]) if latest_row and latest_row["d"] else date.today()

    start, end, prev_start, prev_end, days = period_bounds(range_key, anchor)

    current = totals_for(conn, start, end)
    previous = totals_for(conn, prev_start, prev_end)

    payload = {
        "range": range_key,
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        "compare_period": {"start": prev_start.isoformat(), "end": prev_end.isoformat()},
        "kpis": {
            "revenue": {
                "value": round(current["revenue"], 2),
                "delta_pct": pct_delta(current["revenue"], previous["revenue"]),
                "sparkline": sparkline(conn, anchor),
            },
            "orders": {
                "value": current["orders"],
                "delta_pct": pct_delta(current["orders"], previous["orders"]),
                "sparkline": None,
            },
            "aov": {
                "value": round(current["aov"], 2),
                "delta_pct": pct_delta(current["aov"], previous["aov"]),
                "sparkline": None,
            },
            "new_share": {
                "value": round(current["new_share"], 1),
                "delta_pct": pct_delta(current["new_share"], previous["new_share"]),
                "sparkline": None,
            },
        },
        "revenue_trend": daily_series(conn, start, end, days),
        "category_breakdown": category_breakdown(conn, start, end),
        "region_breakdown": region_breakdown(conn, start, end),
        "customer_mix": customer_mix(conn, start, end),
        "top_products": top_products(conn, start, end),
    }
    conn.close()
    return jsonify(payload)


init_db()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5063))
    debug = os.environ.get("FLASK_DEBUG", "1") == "1"
    app.run(debug=debug, host="0.0.0.0", port=port)
