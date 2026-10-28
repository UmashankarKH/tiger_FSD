"""Supplier and purchase-order utilities for the CPG procurement analytics service.

Answer key for the lab: same public API as procurement_legacy.py, with the
security flaws fixed and the bloat removed.
"""
import base64
import csv
import gzip
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import time
from contextlib import closing
from datetime import date, datetime, timedelta
from decimal import Decimal

DB_PATH = os.environ.get("CPG_DB_PATH", "procurement.db")
EXPORT_DIR = os.environ.get("CPG_EXPORT_DIR", "exports")
RISK_WINDOW_DAYS = 90
LOW_RISK_MAX = 10.0
MEDIUM_RISK_MAX = 25.0
TOKEN_TTL_SECONDS = 3600
APPROVER_ROLES = {"approver", "admin"}
_SAFE_REPORT_NAME = re.compile(r"[A-Za-z0-9_-]{1,64}")

SCHEMA = """
CREATE TABLE IF NOT EXISTS suppliers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    country TEXT,
    active INTEGER DEFAULT 1
);
CREATE TABLE IF NOT EXISTS purchase_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    supplier_id INTEGER NOT NULL,
    status TEXT NOT NULL,
    order_date TEXT NOT NULL,
    promised_date TEXT NOT NULL,
    delivered_date TEXT,
    total REAL
);
CREATE TABLE IF NOT EXISTS po_lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    po_id INTEGER NOT NULL,
    sku TEXT NOT NULL,
    qty INTEGER NOT NULL,
    unit_price REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL
);
"""


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with closing(_connect()) as conn, conn:
        conn.executescript(SCHEMA)


# -------------------------------------------------------------- suppliers ----
def add_supplier(name, country):
    with closing(_connect()) as conn, conn:
        cur = conn.execute("INSERT INTO suppliers (name, country) VALUES (?, ?)", (name, country))
        return cur.lastrowid


def get_supplier(supplier_id):
    with closing(_connect()) as conn:
        row = conn.execute(
            "SELECT id, name, country, active FROM suppliers WHERE id = ?", (supplier_id,)
        ).fetchone()
    if row is None:
        return None
    return {**dict(row), "active": bool(row["active"])}


# -------------------------------------------------------- purchase orders ----
def calculate_po_total(lines):
    """Sum qty * unit_price. Raises ValueError on malformed or non-positive lines."""
    total = Decimal("0")
    for line in lines:
        try:
            qty = int(line["qty"])
            price = Decimal(str(line["unit_price"]))
        except (KeyError, ValueError, TypeError, ArithmeticError) as exc:
            raise ValueError(f"invalid PO line: {line!r}") from exc
        if qty <= 0 or price < 0:
            raise ValueError(f"qty must be > 0 and price >= 0: {line!r}")
        total += qty * price
    return float(round(total, 2))


def create_order(supplier_id, lines, order_date, promised_date):
    total = calculate_po_total(lines)
    with closing(_connect()) as conn, conn:
        cur = conn.execute(
            "INSERT INTO purchase_orders (supplier_id, status, order_date, promised_date, total) "
            "VALUES (?, 'DRAFT', ?, ?, ?)",
            (supplier_id, order_date, promised_date, total),
        )
        po_id = cur.lastrowid
        conn.executemany(
            "INSERT INTO po_lines (po_id, sku, qty, unit_price) VALUES (?, ?, ?, ?)",
            [(po_id, line["sku"], line["qty"], line["unit_price"]) for line in lines],
        )
    return po_id


def mark_delivered(po_id, delivered_date):
    with closing(_connect()) as conn, conn:
        conn.execute(
            "UPDATE purchase_orders SET delivered_date = ?, status = 'DELIVERED' WHERE id = ?",
            (delivered_date, po_id),
        )


def get_supplier_orders(supplier_name):
    with closing(_connect()) as conn:
        rows = conn.execute(
            "SELECT po.id, po.status, po.order_date, po.promised_date, po.delivered_date, po.total "
            "FROM purchase_orders po JOIN suppliers s ON s.id = po.supplier_id "
            "WHERE s.name = ? ORDER BY po.order_date, po.id",
            (supplier_name,),
        ).fetchall()
    return [dict(r) for r in rows]


def supplier_risk_score(supplier_id, today=None):
    """% of POs delivered late in the last RISK_WINDOW_DAYS, bucketed Low/Medium/High."""
    if today is None:
        today = date.today()
    elif isinstance(today, str):
        today = datetime.strptime(today, "%Y-%m-%d").date()
    cutoff = (today - timedelta(days=RISK_WINDOW_DAYS)).isoformat()

    with closing(_connect()) as conn:
        rows = conn.execute(
            "SELECT promised_date, delivered_date FROM purchase_orders "
            "WHERE supplier_id = ? AND delivered_date IS NOT NULL AND delivered_date >= ?",
            (supplier_id, cutoff),
        ).fetchall()

    if not rows:
        return {"supplier_id": supplier_id, "late_pct": None, "bucket": "Unknown", "sample_size": 0}

    late = sum(1 for r in rows if r["delivered_date"] > r["promised_date"])
    pct = round(late / len(rows) * 100, 1)
    if pct < LOW_RISK_MAX:
        bucket = "Low"
    elif pct < MEDIUM_RISK_MAX:
        bucket = "Medium"
    else:
        bucket = "High"
    return {"supplier_id": supplier_id, "late_pct": pct, "bucket": bucket, "sample_size": len(rows)}


# ------------------------------------------------------------ users / auth ----
def _secret():
    key = os.environ.get("CPG_SECRET_KEY")
    if not key:
        raise RuntimeError("CPG_SECRET_KEY is not set")
    return key.encode()


def _hash_password(password, salt=None):
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return f"{salt.hex()}${digest.hex()}"


def _password_matches(password, stored):
    salt_hex, _, _ = stored.partition("$")
    candidate = _hash_password(password, bytes.fromhex(salt_hex))
    return hmac.compare_digest(candidate, stored)


def register_user(username, password, role="viewer"):
    with closing(_connect()) as conn, conn:
        conn.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            (username, _hash_password(password), role),
        )


def _sign(payload):
    return hmac.new(_secret(), payload.encode(), hashlib.sha256).hexdigest()


def _make_token(username, role):
    body = {"u": username, "r": role, "exp": int(time.time()) + TOKEN_TTL_SECONDS}
    payload = base64.urlsafe_b64encode(json.dumps(body).encode()).decode()
    return f"{payload}.{_sign(payload)}"


def verify_token(token):
    """Return (username, role) for a valid, unexpired token, else None."""
    try:
        payload, signature = token.split(".", 1)
    except (AttributeError, ValueError):
        return None
    if not hmac.compare_digest(signature, _sign(payload)):
        return None
    body = json.loads(base64.urlsafe_b64decode(payload))  # signed by us, so always well-formed
    if body["exp"] < time.time():
        return None
    return body["u"], body["r"]


def login(username, password):
    with closing(_connect()) as conn:
        row = conn.execute(
            "SELECT username, role, password_hash FROM users WHERE username = ?", (username,)
        ).fetchone()
    if row is None or not _password_matches(password, row["password_hash"]):
        return None
    return _make_token(row["username"], row["role"])


def approve_order(token, po_id):
    user = verify_token(token)
    if user is None:
        raise PermissionError("invalid or expired token")
    if user[1] not in APPROVER_ROLES:
        raise PermissionError("role not allowed to approve orders")
    with closing(_connect()) as conn, conn:
        cur = conn.execute("UPDATE purchase_orders SET status = 'APPROVED' WHERE id = ?", (po_id,))
        if cur.rowcount == 0:
            raise LookupError(f"purchase order {po_id} not found")
    return True


# ---------------------------------------------------------- reports / cache ----
def export_report(filename, supplier_id=None):
    """Write a gzipped CSV of purchase orders into EXPORT_DIR and return its path."""
    if not _SAFE_REPORT_NAME.fullmatch(filename):
        raise ValueError("report name must be 1-64 letters, digits, '_' or '-'")
    os.makedirs(EXPORT_DIR, exist_ok=True)
    path = os.path.join(EXPORT_DIR, f"{filename}.csv.gz")

    query = (
        "SELECT id, supplier_id, status, order_date, promised_date, delivered_date, total "
        "FROM purchase_orders"
    )
    params = ()
    if supplier_id is not None:
        query += " WHERE supplier_id = ?"
        params = (supplier_id,)
    with closing(_connect()) as conn:
        rows = conn.execute(query + " ORDER BY id", params).fetchall()

    with gzip.open(path, "wt", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["po_id", "supplier_id", "status", "order_date", "promised_date", "delivered_date", "total"])
        writer.writerows(tuple(r) for r in rows)
    return path


def cache_report(data):
    return base64.b64encode(json.dumps(data).encode()).decode()


def load_cached_report(blob):
    try:
        return json.loads(base64.b64decode(blob, validate=True))
    except ValueError as exc:
        raise ValueError("invalid cache payload") from exc
