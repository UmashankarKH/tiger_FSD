import base64
import sqlite3
from contextlib import closing

import pytest


# ---- unit: purchase-order totals --------------------------------------------
def test_po_total_uses_exact_decimal_arithmetic(proc):
    lines = [{"sku": "A", "qty": 3, "unit_price": 0.1}]
    assert proc.calculate_po_total(lines) == 0.3


@pytest.mark.parametrize(
    "lines, expected",
    [
        ([{"sku": "A", "qty": 1, "unit_price": 0.0}], 0.0),
        ([{"sku": "A", "qty": 1000000, "unit_price": 0.01}], 10000.0),
        ([{"sku": "A", "qty": "4", "unit_price": "2.50"}], 10.0),
    ],
)
def test_po_total_edge_values(proc, lines, expected):
    assert proc.calculate_po_total(lines) == expected


# ---- unit: suppliers --------------------------------------------------------
def test_duplicate_supplier_name_is_rejected(proc):
    proc.add_supplier("Acme", "IN")
    with pytest.raises(sqlite3.IntegrityError):
        proc.add_supplier("Acme", "US")


def test_init_db_is_idempotent(proc, supplier):
    proc.init_db()
    assert proc.get_supplier(supplier)["name"] == "Acme Packaging"


# ---- edge: risk window boundary --------------------------------------------
def test_delivery_exactly_90_days_ago_is_counted(proc, supplier, make_delivered_order):
    make_delivered_order(supplier, promised="2026-06-30", delivered="2026-07-03")  # 90 days before 2026-10-01
    result = proc.supplier_risk_score(supplier, today="2026-10-01")
    assert result["sample_size"] == 1
    assert result["bucket"] == "High"


def test_delivery_91_days_ago_is_not_counted(proc, supplier, make_delivered_order):
    make_delivered_order(supplier, promised="2026-06-30", delivered="2026-07-02")
    result = proc.supplier_risk_score(supplier, today="2026-10-01")
    assert result["sample_size"] == 0
    assert result["bucket"] == "Unknown"


def test_risk_score_rejects_malformed_today_string(proc, supplier):
    with pytest.raises(ValueError):
        proc.supplier_risk_score(supplier, today="01/10/2026")


# ---- edge: report names -----------------------------------------------------
def test_report_name_length_limit(proc):
    assert proc.export_report("a" * 64).endswith(".csv.gz")
    with pytest.raises(ValueError):
        proc.export_report("a" * 65)


# ---- security: cache and tokens ---------------------------------------------
def test_cache_loader_rejects_non_base64_input(proc):
    with pytest.raises(ValueError):
        proc.load_cached_report("this is not base64!!")


def test_cache_loader_rejects_valid_base64_that_is_not_json(proc):
    blob = base64.b64encode(b"\x80\x04not json").decode()
    with pytest.raises(ValueError):
        proc.load_cached_report(blob)


def test_same_password_gets_different_hashes(proc, tmp_path):
    proc.register_user("a", "same-password")
    proc.register_user("b", "same-password")
    with closing(sqlite3.connect(str(tmp_path / "test.db"))) as conn:
        hashes = [row[0] for row in conn.execute("SELECT password_hash FROM users ORDER BY username")]
    assert hashes[0] != hashes[1]


def test_duplicate_username_is_rejected(proc):
    proc.register_user("a", "pw")
    with pytest.raises(sqlite3.IntegrityError):
        proc.register_user("a", "other")


# ---- integration: create, deliver, score, export ----------------------------
def test_full_flow_create_deliver_score_export(proc, supplier):
    import gzip

    for promised, delivered in [("2026-09-10", "2026-09-10"), ("2026-09-10", "2026-09-14")]:
        po = proc.create_order(
            supplier, [{"sku": "S", "qty": 2, "unit_price": 4.0}], "2026-09-01", promised
        )
        proc.mark_delivered(po, delivered)

    score = proc.supplier_risk_score(supplier, today="2026-10-01")
    assert (score["late_pct"], score["bucket"], score["sample_size"]) == (50.0, "High", 2)

    path = proc.export_report("flow", supplier_id=supplier)
    with gzip.open(path, "rt") as f:
        rows = f.read().splitlines()
    assert len(rows) == 3
    assert all(r.split(",")[2] == "DELIVERED" for r in rows[1:])


def test_approval_flow_end_to_end(proc, supplier):
    po = proc.create_order(supplier, [{"sku": "S", "qty": 1, "unit_price": 9.99}], "2026-09-01", "2026-09-09")
    proc.register_user("boss", "pw", role="admin")
    assert proc.approve_order(proc.login("boss", "pw"), po) is True
    assert proc.get_supplier_orders("Acme Packaging")[0]["status"] == "APPROVED"
