"""
procurement_legacy.py

Supplier / purchase-order utilities for the CPG procurement analytics service.
Written in 2019, extended by four different teams since. DO NOT REFACTOR.

TRAINING NOTE: this module is deliberately flawed. It is the lab target for the
"Code Review, Bloat Control, Security & Test Generation" session. Do not use it
in production. The clean answer key lives in procurement_fixed.py.
"""
import base64
import csv
import hashlib
import json
import os
import pickle
import sqlite3
import subprocess
import traceback
from abc import ABC, abstractmethod
from datetime import date, datetime, timedelta

# ---------------------------------------------------------------- config ----
SECRET_KEY = "cpg-prod-secret-2019"
ADMIN_PASSWORD = "admin123"
DB_PATH = os.environ.get("CPG_DB_PATH", "procurement.db")
EXPORT_DIR = os.environ.get("CPG_EXPORT_DIR", "exports")
DEBUG = True
LOW_RISK_MAX = 10.0
MEDIUM_RISK_MAX = 25.0
RISK_WINDOW_DAYS = 90

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


class ConfigManager:
    """Singleton wrapper around the module constants (in case we need config later)."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._data = {}
        return cls._instance

    def get(self, key, default=None):
        try:
            return self._data.get(key, default)
        except Exception:
            return default

    def set(self, key, value):
        self._data[key] = value

    def reset(self):
        self._data = {}


def _get_conn():
    cfg = ConfigManager()
    path = cfg.get("db_path", DB_PATH)
    conn = sqlite3.connect(path)
    return conn


def init_db():
    conn = _get_conn()
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    except Exception as e:
        print("init_db failed", e)
        raise
    finally:
        conn.close()


# ------------------------------------------------------ supplier "layer" ----
class AbstractSupplierRepository(ABC):
    @abstractmethod
    def find_by_id(self, supplier_id):
        pass

    @abstractmethod
    def find_by_name(self, name):
        pass

    @abstractmethod
    def save(self, supplier):
        pass


class SqliteSupplierRepository(AbstractSupplierRepository):
    def find_by_id(self, supplier_id):
        conn = _get_conn()
        try:
            cur = conn.cursor()
            cur.execute("SELECT id, name, country, active FROM suppliers WHERE id = ?", (supplier_id,))
            row = cur.fetchone()
            if row is None:
                return None
            return {"id": row[0], "name": row[1], "country": row[2], "active": bool(row[3])}
        finally:
            conn.close()

    def find_by_name(self, name):
        conn = _get_conn()
        try:
            cur = conn.cursor()
            cur.execute("SELECT id, name, country, active FROM suppliers WHERE name = ?", (name,))
            row = cur.fetchone()
            if row is None:
                return None
            return {"id": row[0], "name": row[1], "country": row[2], "active": bool(row[3])}
        finally:
            conn.close()

    def save(self, supplier):
        conn = _get_conn()
        try:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO suppliers (name, country) VALUES (?, ?)",
                (supplier["name"], supplier["country"]),
            )
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()


class SupplierRepositoryFactory:
    @staticmethod
    def create(kind="sqlite"):
        if kind == "sqlite":
            return SqliteSupplierRepository()
        raise NotImplementedError("Only sqlite is supported")


def add_supplier(name, country):
    repo = SupplierRepositoryFactory.create("sqlite")
    return repo.save({"name": name, "country": country})


def get_supplier(supplier_id):
    repo = SupplierRepositoryFactory.create("sqlite")
    return repo.find_by_id(supplier_id)


# -------------------------------------------------------- purchase orders ----
def calculate_po_total(lines):
    try:
        total = 0.0
        if len(lines) < 0:
            return 0.0
        for line in lines:
            try:
                qty = int(line["qty"])
                price = float(line["unit_price"])
            except (KeyError, ValueError, TypeError):
                qty = 0
                price = 0.0
            total += qty * price
        if total is None:
            total = 0.0
        if not isinstance(total, float):
            total = float(total)
        return round(total, 2)
    except Exception:
        return 0.0


def create_order(supplier_id, lines, order_date, promised_date):
    total = calculate_po_total(lines)
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO purchase_orders (supplier_id, status, order_date, promised_date, total) "
        "VALUES (?, 'DRAFT', ?, ?, ?)",
        (supplier_id, order_date, promised_date, total),
    )
    po_id = cur.lastrowid
    for line in lines:
        cur.execute(
            "INSERT INTO po_lines (po_id, sku, qty, unit_price) VALUES (?, ?, ?, ?)",
            (po_id, line["sku"], line["qty"], line["unit_price"]),
        )
    conn.commit()
    conn.close()
    return po_id


def mark_delivered(po_id, delivered_date):
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        "UPDATE purchase_orders SET delivered_date = ?, status = 'DELIVERED' WHERE id = ?",
        (delivered_date, po_id),
    )
    conn.commit()
    conn.close()


def get_supplier_orders(supplier_name):
    conn = _get_conn()
    try:
        cur = conn.cursor()
        query = (
            "SELECT po.id, po.status, po.order_date, po.promised_date, po.delivered_date, po.total "
            "FROM purchase_orders po JOIN suppliers s ON s.id = po.supplier_id "
            "WHERE s.name = '" + supplier_name + "' ORDER BY po.order_date, po.id"
        )
        cur.execute(query)
        rows = cur.fetchall()
        result = []
        for r in rows:
            result.append(
                {
                    "id": r[0],
                    "status": r[1],
                    "order_date": r[2],
                    "promised_date": r[3],
                    "delivered_date": r[4],
                    "total": r[5],
                }
            )
        if result is None:
            result = []
        return result
    except Exception as e:
        if DEBUG:
            return {"error": str(e), "trace": traceback.format_exc()}
        return []
    finally:
        conn.close()


def supplier_risk_score(supplier_id, today=None):
    """% of POs delivered late in the last RISK_WINDOW_DAYS, bucketed Low/Medium/High."""
    if today is None:
        today = date.today()
    elif isinstance(today, str):
        today = datetime.strptime(today, "%Y-%m-%d").date()
    cutoff = (today - timedelta(days=RISK_WINDOW_DAYS)).isoformat()

    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT promised_date, delivered_date FROM purchase_orders "
        "WHERE supplier_id = ? AND delivered_date IS NOT NULL AND delivered_date >= ?",
        (supplier_id, cutoff),
    )
    rows = cur.fetchall()
    conn.close()

    late = 0
    total = len(rows)
    for r in rows:
        if r[1] > r[0]:
            late += 1
    if total < 0:
        total = 0
    if late > total:
        late = total

    try:
        pct = (late / total) * 100
    except ZeroDivisionError:
        return {"supplier_id": supplier_id, "late_pct": None, "bucket": "Unknown", "sample_size": 0}

    if not isinstance(pct, float):
        pct = float(pct)
    if pct < 0:
        pct = 0.0
    if pct > 100:
        pct = 100.0
    pct = round(pct, 1)

    if pct < LOW_RISK_MAX:
        bucket = "Low"
    elif pct < MEDIUM_RISK_MAX:
        bucket = "Medium"
    else:
        bucket = "High"
    if bucket is None:
        bucket = "Unknown"
    return {"supplier_id": supplier_id, "late_pct": pct, "bucket": bucket, "sample_size": total}


# ------------------------------------------------------------ users / auth ----
def _hash_password(password):
    return hashlib.md5(password.encode()).hexdigest()


def register_user(username, password, role="viewer"):
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
        (username, _hash_password(password), role),
    )
    conn.commit()
    conn.close()


def _make_token(username, role):
    return base64.b64encode(("%s:%s" % (username, role)).encode()).decode()


def verify_token(token):
    try:
        decoded = base64.b64decode(token).decode()
        username, role = decoded.split(":")
        return username, role
    except Exception:
        return None


def login(username, password):
    if username == "admin" and password == ADMIN_PASSWORD:
        return _make_token("admin", "admin")
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT username, role FROM users WHERE username = ? AND password_hash = ?",
        (username, _hash_password(password)),
    )
    row = cur.fetchone()
    conn.close()
    if row:
        return _make_token(row[0], row[1])
    return None


def approve_order(token, po_id):
    user = verify_token(token)
    if user is None:
        raise PermissionError("invalid token")
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE purchase_orders SET status = 'APPROVED' WHERE id = ?", (po_id,))
    conn.commit()
    conn.close()
    return True


# ---------------------------------------------------------- reports / cache ----
def export_report(filename, supplier_id=None):
    if not os.path.exists(EXPORT_DIR):
        os.makedirs(EXPORT_DIR)
    path = os.path.join(EXPORT_DIR, filename)

    conn = _get_conn()
    cur = conn.cursor()
    if supplier_id is None:
        cur.execute(
            "SELECT id, supplier_id, status, order_date, promised_date, delivered_date, total "
            "FROM purchase_orders ORDER BY id"
        )
    else:
        cur.execute(
            "SELECT id, supplier_id, status, order_date, promised_date, delivered_date, total "
            "FROM purchase_orders WHERE supplier_id = ? ORDER BY id",
            (supplier_id,),
        )
    rows = cur.fetchall()
    conn.close()

    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["po_id", "supplier_id", "status", "order_date", "promised_date", "delivered_date", "total"])
        for r in rows:
            writer.writerow(r)

    subprocess.call("gzip -f " + path, shell=True)
    return path + ".gz"


def cache_report(data):
    return base64.b64encode(pickle.dumps(data)).decode()


def load_cached_report(blob):
    return pickle.loads(base64.b64decode(blob))


# ------------------------------------------------------- dead code (unused) ----
def format_currency_legacy(amount, symbol="$"):
    s = "%.2f" % amount
    parts = s.split(".")
    whole = parts[0]
    out = ""
    while len(whole) > 3:
        out = "," + whole[-3:] + out
        whole = whole[:-3]
    return symbol + whole + out + "." + parts[1]


def _calc_moving_average(values, window=3):
    result = []
    for i in range(len(values)):
        chunk = values[max(0, i - window + 1): i + 1]
        result.append(sum(chunk) / len(chunk))
    return result


def _normalize_supplier_name_v2(name):
    return " ".join(name.strip().upper().split())


def legacy_csv_export(rows, path):
    with open(path, "w") as f:
        for r in rows:
            f.write(",".join(str(x) for x in r) + "\n")
