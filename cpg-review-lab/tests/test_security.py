"""Security and correctness tests, labelled with OWASP Top 10:2025 categories.

These PASS on procurement_fixed.py and FAIL on procurement_legacy.py. Every
payload is harmless: marker files are created inside pytest's tmp_path only.

    CPG_TARGET=procurement_legacy pytest -m security
"""
import base64
import hashlib
import pickle
import sqlite3
import time
from contextlib import closing

import pytest

pytestmark = pytest.mark.security


# ------------------------------- A05:2025 Injection: SQL ----
def test_sql_injection_in_supplier_name_returns_nothing(proc, supplier):
    proc.create_order(supplier, [{"sku": "A", "qty": 1, "unit_price": 1.0}], "2026-09-01", "2026-09-05")

    result = proc.get_supplier_orders("nobody' OR '1'='1")

    assert result == []


def test_orders_lookup_never_returns_error_dicts(proc):
    result = proc.get_supplier_orders("it's got a quote")
    assert result == []


# ----------------------- A05:2025 Injection: OS command ----
def test_shell_metacharacters_in_report_name_are_rejected(proc, supplier, tmp_path):
    marker = tmp_path / "pwned_marker"

    with pytest.raises(ValueError):
        proc.export_report("r; touch pwned_marker")

    assert not marker.exists()


# ------------------- A01:2025 Broken Access Control: path traversal ----
@pytest.mark.parametrize("bad_name", ["../escape", "sub/dir", "..", "/abs/path", ""])
def test_report_name_cannot_escape_export_dir(proc, bad_name):
    with pytest.raises(ValueError):
        proc.export_report(bad_name)


def test_absolute_path_report_name_writes_nothing_outside_exports(proc, tmp_path):
    outside = tmp_path / "abs_escape"
    with pytest.raises(ValueError):
        proc.export_report(str(outside))
    assert not outside.exists()


# ------------ A08:2025 Software or Data Integrity: unsafe deserialization ----
class _Exploit:
    def __reduce__(self):
        return (open, ("pickled_marker", "w"))  # harmless stand-in for "run code"


def test_cache_loader_does_not_execute_pickle_payloads(proc, tmp_path):
    blob = base64.b64encode(pickle.dumps(_Exploit())).decode()

    with pytest.raises(ValueError):
        proc.load_cached_report(blob)

    assert not (tmp_path / "pickled_marker").exists()


# --------------- A07:2025 Authentication Failures (+ A04 Crypto) ----
def test_no_hardcoded_admin_backdoor(proc):
    assert proc.login("admin", "admin123") is None


def test_passwords_are_not_stored_as_plain_md5(proc, tmp_path):
    proc.register_user("priya", "hunter2")
    with closing(sqlite3.connect(str(tmp_path / "test.db"))) as conn:
        stored = conn.execute("SELECT password_hash FROM users WHERE username = 'priya'").fetchone()[0]
    assert stored != hashlib.md5(b"hunter2").hexdigest()
    assert "hunter2" not in stored


def test_forged_token_is_rejected(proc):
    forged = base64.b64encode(b"admin:admin").decode()
    assert proc.verify_token(forged) is None


def test_tampered_token_is_rejected(proc):
    proc.register_user("sam", "pw", role="viewer")
    token = proc.login("sam", "pw")
    signature = token.rsplit(".", 1)[-1]
    upgraded = base64.urlsafe_b64encode(b'{"u": "sam", "r": "admin", "exp": 9999999999}').decode()
    assert proc.verify_token(f"{upgraded}.{signature}") is None


def test_tokens_expire(proc, monkeypatch):
    proc.register_user("sam", "pw", role="approver")
    token = proc.login("sam", "pw")
    real_time = time.time
    monkeypatch.setattr(time, "time", lambda: real_time() + 7200)  # two hours later
    assert proc.verify_token(token) is None


def test_garbage_tokens_are_rejected(proc):
    assert proc.verify_token(None) is None
    assert proc.verify_token("") is None
    assert proc.verify_token("a.b") is None
    assert proc.verify_token("no-dot-at-all") is None


# --------------------- A01:2025 Broken Access Control: roles ----
def test_viewer_cannot_approve_orders(proc, supplier):
    po = proc.create_order(supplier, [{"sku": "A", "qty": 1, "unit_price": 1.0}], "2026-09-01", "2026-09-05")
    proc.register_user("sam", "pw", role="viewer")
    token = proc.login("sam", "pw")

    with pytest.raises(PermissionError):
        proc.approve_order(token, po)

    assert proc.get_supplier_orders("Acme Packaging")[0]["status"] == "DRAFT"


def test_approve_with_forged_token_is_denied(proc, supplier):
    po = proc.create_order(supplier, [{"sku": "A", "qty": 1, "unit_price": 1.0}], "2026-09-01", "2026-09-05")
    forged = base64.b64encode(b"admin:admin").decode()

    with pytest.raises(PermissionError):
        proc.approve_order(forged, po)


def test_approving_unknown_order_fails_loudly(proc):
    proc.register_user("priya", "pw", role="approver")
    token = proc.login("priya", "pw")
    with pytest.raises(LookupError):
        proc.approve_order(token, 424242)


# ---- Correctness + A10:2025 Mishandling of Exceptional Conditions ----
@pytest.mark.parametrize(
    "bad_line",
    [
        {"sku": "A", "qty": "ten", "unit_price": 2.0},
        {"sku": "A", "qty": 1},
        {"sku": "A", "qty": -5, "unit_price": 2.0},
        {"sku": "A", "qty": 1, "unit_price": -2.0},
        {"sku": "A", "qty": 0, "unit_price": 2.0},
        {"sku": "A", "qty": None, "unit_price": 2.0},
    ],
)
def test_invalid_po_lines_raise_instead_of_being_ignored(proc, bad_line):
    with pytest.raises(ValueError):
        proc.calculate_po_total([bad_line])


def test_failed_order_creation_leaves_no_partial_order(proc, supplier):
    good = {"sku": "A", "qty": 1, "unit_price": 1.0}
    bad = {"sku": "B", "qty": -1, "unit_price": 1.0}
    with pytest.raises(ValueError):
        proc.create_order(supplier, [good, bad], "2026-09-01", "2026-09-05")
    assert proc.get_supplier_orders("Acme Packaging") == []


def test_missing_secret_key_fails_closed(proc, monkeypatch):
    proc.register_user("sam", "pw", role="viewer")
    monkeypatch.delenv("CPG_SECRET_KEY")
    with pytest.raises(RuntimeError):
        proc.login("sam", "pw")
