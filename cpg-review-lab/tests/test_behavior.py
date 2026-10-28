"""Characterization tests: the business behaviour both versions must share."""
import gzip
from datetime import date

import pytest


# ----------------------------------------------------------- suppliers ----
def test_add_and_get_supplier(proc):
    supplier_id = proc.add_supplier("Globex Foods", "DE")
    assert proc.get_supplier(supplier_id) == {
        "id": supplier_id,
        "name": "Globex Foods",
        "country": "DE",
        "active": True,
    }


def test_get_missing_supplier_returns_none(proc):
    assert proc.get_supplier(9999) is None


# ------------------------------------------------------- PO totals ----
def test_po_total_sums_lines_and_rounds(proc):
    lines = [
        {"sku": "A", "qty": 10, "unit_price": 2.5},
        {"sku": "B", "qty": 3, "unit_price": 19.99},
    ]
    assert proc.calculate_po_total(lines) == 84.97


def test_po_total_of_no_lines_is_zero(proc):
    assert proc.calculate_po_total([]) == 0.0


def test_create_order_stores_total_and_lines(proc, supplier):
    po = proc.create_order(
        supplier,
        [{"sku": "A", "qty": 2, "unit_price": 5.0}],
        order_date="2026-07-01",
        promised_date="2026-07-10",
    )
    orders = proc.get_supplier_orders("Acme Packaging")
    assert [o["id"] for o in orders] == [po]
    assert orders[0]["total"] == 10.0
    assert orders[0]["status"] == "DRAFT"


def test_supplier_orders_unknown_supplier_is_empty(proc):
    assert proc.get_supplier_orders("Nobody Ltd") == []


# ------------------------------------------------------ risk score ----
TODAY = "2026-10-01"


@pytest.mark.parametrize(
    "late_count, on_time_count, expected_pct, expected_bucket",
    [
        (0, 10, 0.0, "Low"),
        (1, 11, 8.3, "Low"),       # just under 10%
        (1, 9, 10.0, "Medium"),    # boundary: 10% is Medium
        (2, 8, 20.0, "Medium"),
        (1, 3, 25.0, "High"),      # boundary: 25% is High
        (5, 0, 100.0, "High"),
    ],
)
def test_risk_buckets(proc, supplier, make_delivered_order, late_count, on_time_count, expected_pct, expected_bucket):
    for _ in range(late_count):
        make_delivered_order(supplier, promised="2026-09-10", delivered="2026-09-15")
    for _ in range(on_time_count):
        make_delivered_order(supplier, promised="2026-09-10", delivered="2026-09-10")

    result = proc.supplier_risk_score(supplier, today=TODAY)

    assert result["late_pct"] == expected_pct
    assert result["bucket"] == expected_bucket
    assert result["sample_size"] == late_count + on_time_count


def test_risk_unknown_when_no_deliveries(proc, supplier):
    result = proc.supplier_risk_score(supplier, today=TODAY)
    assert result == {"supplier_id": supplier, "late_pct": None, "bucket": "Unknown", "sample_size": 0}


def test_risk_ignores_deliveries_older_than_90_days(proc, supplier, make_delivered_order):
    make_delivered_order(supplier, promised="2026-05-01", delivered="2026-05-20")  # 134 days ago, late
    make_delivered_order(supplier, promised="2026-09-10", delivered="2026-09-10")  # recent, on time

    result = proc.supplier_risk_score(supplier, today=TODAY)

    assert result["sample_size"] == 1
    assert result["bucket"] == "Low"


def test_risk_defaults_to_the_current_date(proc, supplier, make_delivered_order):
    today = date.today().isoformat()
    make_delivered_order(supplier, promised=today, delivered=today)

    result = proc.supplier_risk_score(supplier)

    assert (result["sample_size"], result["bucket"]) == (1, "Low")


def test_risk_ignores_undelivered_orders(proc, supplier):
    proc.create_order(supplier, [{"sku": "A", "qty": 1, "unit_price": 1.0}], "2026-09-01", "2026-09-05")
    assert proc.supplier_risk_score(supplier, today=TODAY)["bucket"] == "Unknown"


# ------------------------------------------------- login and approval ----
def test_registered_user_can_log_in(proc):
    proc.register_user("priya", "correct horse", role="approver")
    token = proc.login("priya", "correct horse")
    assert proc.verify_token(token) == ("priya", "approver")


def test_wrong_password_is_rejected(proc):
    proc.register_user("priya", "correct horse", role="approver")
    assert proc.login("priya", "wrong") is None


def test_unknown_user_is_rejected(proc):
    assert proc.login("ghost", "whatever") is None


def test_approver_can_approve_order(proc, supplier):
    po = proc.create_order(supplier, [{"sku": "A", "qty": 1, "unit_price": 1.0}], "2026-09-01", "2026-09-05")
    proc.register_user("priya", "pw", role="approver")
    token = proc.login("priya", "pw")

    assert proc.approve_order(token, po) is True
    assert proc.get_supplier_orders("Acme Packaging")[0]["status"] == "APPROVED"


# ---------------------------------------------------- export and cache ----
def test_export_report_writes_gzipped_csv(proc, supplier):
    proc.create_order(supplier, [{"sku": "A", "qty": 2, "unit_price": 5.0}], "2026-09-01", "2026-09-05")

    path = proc.export_report("weekly_report")

    with gzip.open(path, "rt") as f:
        lines = f.read().splitlines()
    assert lines[0] == "po_id,supplier_id,status,order_date,promised_date,delivered_date,total"
    assert len(lines) == 2
    assert lines[1].startswith("1,")


def test_export_report_can_filter_by_supplier(proc, supplier):
    other = proc.add_supplier("Other Co", "US")
    proc.create_order(supplier, [{"sku": "A", "qty": 1, "unit_price": 1.0}], "2026-09-01", "2026-09-05")
    proc.create_order(other, [{"sku": "B", "qty": 1, "unit_price": 1.0}], "2026-09-01", "2026-09-05")

    path = proc.export_report("only_other", supplier_id=other)

    with gzip.open(path, "rt") as f:
        assert len(f.read().splitlines()) == 2  # header + one row


def test_report_cache_round_trip(proc):
    data = {"supplier": "Acme", "late_pct": 12.5, "history": [1, 2, 3]}
    assert proc.load_cached_report(proc.cache_report(data)) == data
