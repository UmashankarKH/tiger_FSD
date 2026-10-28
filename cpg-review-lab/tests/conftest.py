"""Shared fixtures.

The same tests run against either module so learners can watch the security
tests FAIL on the legacy code and PASS on the fixed code:

    pytest                                  # fixed module (default)
    CPG_TARGET=procurement_legacy pytest    # legacy module
"""
import importlib
import os

import pytest

TARGET = os.environ.get("CPG_TARGET", "procurement_fixed")


@pytest.fixture
def proc(tmp_path, monkeypatch):
    """The module under test, wired to a throwaway database and export folder."""
    monkeypatch.setenv("CPG_SECRET_KEY", "test-secret-not-for-production")
    monkeypatch.chdir(tmp_path)  # anything a bad test writes lands in tmp_path
    module = importlib.import_module(TARGET)
    monkeypatch.setattr(module, "DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr(module, "EXPORT_DIR", str(tmp_path / "exports"))
    module.init_db()
    return module


@pytest.fixture
def supplier(proc):
    """A supplier id with no orders yet."""
    return proc.add_supplier("Acme Packaging", "IN")


@pytest.fixture
def make_delivered_order(proc):
    """Factory: create a PO and mark it delivered, with a given lateness in days."""

    def _make(supplier_id, promised, delivered):
        po = proc.create_order(
            supplier_id,
            [{"sku": "SKU-1", "qty": 1, "unit_price": 10.0}],
            order_date="2026-07-01",
            promised_date=promised,
        )
        proc.mark_delivered(po, delivered)
        return po

    return _make
