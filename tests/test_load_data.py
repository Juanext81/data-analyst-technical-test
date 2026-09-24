"""Unit tests for load_data.py (Data_Loader).

These cover the logic that does not require a live PostgreSQL:
- empty nullable CSV cell -> SQL NULL mapping (AC 9.3)
- LOAD_ORDER places parents before children (AC 9.2)
- missing source CSV is reported before any loading begins (AC 9.5)
- FK violation reports table + row id and rolls back (AC 9.4), via a fake conn
- post-load row-count mismatch is reported (AC 9.6), via a fake conn

Behaviors that require a real database (actual INSERT execution, the DB's own
FK enforcement, COUNT(*) over loaded data) are exercised against a live RDS in
the AWS integration tests (task 14.2); here we use fakes to drive load_all's
control flow deterministically.
"""

from __future__ import annotations

import sys
import types

import pytest

import load_data
from load_data import (
    LOAD_ORDER,
    LoadError,
    TABLE_COLUMNS,
    _map_cell,
    _read_csv_rows,
    load_all,
)


# ---------------------------------------------------------------------------
# A minimal fake psycopg2 so _load_one can import psycopg2.errors and match the
# ForeignKeyViolation type without a real driver / database.
# ---------------------------------------------------------------------------


class _FakeFKViolation(Exception):
    pass


@pytest.fixture(autouse=True)
def _fake_psycopg2(monkeypatch):
    fake_pkg = types.ModuleType("psycopg2")
    fake_errors = types.ModuleType("psycopg2.errors")
    fake_errors.ForeignKeyViolation = _FakeFKViolation
    fake_pkg.errors = fake_errors
    monkeypatch.setitem(sys.modules, "psycopg2", fake_pkg)
    monkeypatch.setitem(sys.modules, "psycopg2.errors", fake_errors)
    yield


# ---------------------------------------------------------------------------
# AC 9.3 -- empty nullable cell maps to NULL
# ---------------------------------------------------------------------------


def test_empty_nullable_cell_maps_to_none():
    # products.stock is nullable -> "" becomes None (SQL NULL).
    assert _map_cell("products", "stock", "") is None
    # orders.status / payment_method nullable.
    assert _map_cell("orders", "status", "") is None
    assert _map_cell("orders", "payment_method", "") is None
    # customers.city nullable.
    assert _map_cell("customers", "city", "") is None


def test_empty_non_nullable_cell_is_not_mapped_to_none():
    # category_name is NOT NULL -> an empty string is passed through so the DB
    # can reject it, rather than being silently turned into NULL.
    assert _map_cell("categories", "category_name", "") == ""
    assert _map_cell("orders", "customer_id", "") == ""


def test_non_empty_cell_passthrough():
    assert _map_cell("products", "stock", "405") == "405"
    assert _map_cell("orders", "status", "completed") == "completed"


def test_read_csv_maps_empty_nullable_to_none(tmp_path):
    csv_path = tmp_path / "products.csv"
    csv_path.write_text(
        "product_id,product_name,category_id,price,stock\n"
        "1,Laptop,1,2511646.94,405\n"
        "2,Table Lamp,2,2387654.08,\n",  # empty stock -> NULL
        encoding="utf-8",
    )
    rows = _read_csv_rows(str(csv_path), "products")
    stock_idx = TABLE_COLUMNS["products"].index("stock")
    assert rows[0][stock_idx] == "405"
    assert rows[1][stock_idx] is None


# ---------------------------------------------------------------------------
# AC 9.2 -- FK-safe load order
# ---------------------------------------------------------------------------


def test_load_order_places_parents_before_children():
    assert LOAD_ORDER == [
        "categories",
        "customers",
        "products",
        "orders",
        "order_details",
    ]
    order = {name: i for i, name in enumerate(LOAD_ORDER)}
    # Parents strictly precede children.
    assert order["categories"] < order["products"]
    assert order["customers"] < order["orders"]
    assert order["products"] < order["order_details"]
    assert order["orders"] < order["order_details"]


# ---------------------------------------------------------------------------
# AC 9.5 -- missing source CSV reported before loading begins
# ---------------------------------------------------------------------------


def _write_all_csvs(dir_path):
    (dir_path / "categories.csv").write_text(
        "category_id,category_name\n1,Electronics\n", encoding="utf-8"
    )
    (dir_path / "customers.csv").write_text(
        "customer_id,first_name,last_name,email,city,registration_date\n"
        "1,A,B,a@b.com,,2025-01-01\n",
        encoding="utf-8",
    )
    (dir_path / "products.csv").write_text(
        "product_id,product_name,category_id,price,stock\n1,Laptop,1,10.00,\n",
        encoding="utf-8",
    )
    (dir_path / "orders.csv").write_text(
        "order_id,customer_id,order_date,status,payment_method\n1,1,2025-02-01,,\n",
        encoding="utf-8",
    )
    (dir_path / "order_details.csv").write_text(
        "order_detail_id,order_id,product_id,quantity,unit_price\n1,1,1,2,10.00\n",
        encoding="utf-8",
    )


def test_missing_csv_reported_and_no_loading(tmp_path):
    _write_all_csvs(tmp_path)
    (tmp_path / "orders.csv").unlink()  # remove one file

    conn = _RecordingConn()
    with pytest.raises(LoadError) as exc:
        load_all(conn, data_dir=str(tmp_path))
    assert "orders" in str(exc.value)
    # No loading began: no cursor/execute activity.
    assert conn.executed == []
    assert conn.commits == 0


# ---------------------------------------------------------------------------
# Fake connection used to drive load_all control flow
# ---------------------------------------------------------------------------


class _FakeCursor:
    def __init__(self, conn):
        self._conn = conn

    def execute(self, sql, params=None):
        if sql.startswith("SELECT COUNT(*)"):
            # Return the configured count for the table named in the SQL.
            table = sql.rsplit(" ", 1)[-1]
            self._conn._last_count = self._conn.counts.get(table, 0)
            return
        # INSERT: record it, or raise a configured FK violation.
        self._conn.executed.append((sql, params))
        if self._conn.fk_violation_on is not None:
            table = sql.split()[2]  # INSERT INTO <table> ...
            if table == self._conn.fk_violation_on:
                raise _FakeFKViolation("fk")

    def fetchone(self):
        return (self._conn._last_count,)

    def close(self):
        pass


class _RecordingConn:
    """Fake connection: records executes/commits/rollbacks and returns counts."""

    def __init__(self, counts=None, fk_violation_on=None):
        self.executed = []
        self.commits = 0
        self.rollbacks = 0
        self.counts = counts or {}
        self.fk_violation_on = fk_violation_on
        self._last_count = 0

    def cursor(self):
        return _FakeCursor(self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


# ---------------------------------------------------------------------------
# AC 9.1 / 9.6 -- successful load returns a report with matching counts
# ---------------------------------------------------------------------------


def test_successful_load_returns_report(tmp_path):
    _write_all_csvs(tmp_path)
    # Each CSV above has exactly 1 data row.
    counts = {t: 1 for t in LOAD_ORDER}
    conn = _RecordingConn(counts=counts)

    report = load_all(conn, data_dir=str(tmp_path))

    assert conn.commits == len(LOAD_ORDER)
    assert conn.rollbacks == 0
    assert report.total_loaded == len(LOAD_ORDER)
    for r in report.results:
        assert r.csv_row_count == 1
        assert r.loaded_row_count == 1


# ---------------------------------------------------------------------------
# AC 9.4 -- FK violation reports table + row id and rolls back that file
# ---------------------------------------------------------------------------


def test_fk_violation_reports_table_and_row_id_and_rolls_back(tmp_path):
    _write_all_csvs(tmp_path)
    # categories + customers load fine (1 row each) before products fails.
    counts = {t: 1 for t in LOAD_ORDER}
    conn = _RecordingConn(counts=counts, fk_violation_on="products")

    with pytest.raises(LoadError) as exc:
        load_all(conn, data_dir=str(tmp_path))

    msg = str(exc.value)
    assert "products" in msg
    assert "1" in msg  # the row id (product_id) from the CSV row
    # The failing file's transaction was rolled back (no partial load).
    assert conn.rollbacks == 1
    # categories + customers committed before products failed.
    assert conn.commits == 2


# ---------------------------------------------------------------------------
# AC 9.6 -- row-count mismatch after load is reported
# ---------------------------------------------------------------------------


def test_row_count_mismatch_reported(tmp_path):
    _write_all_csvs(tmp_path)
    # categories CSV has 1 data row but the table reports 0 loaded.
    counts = {t: 1 for t in LOAD_ORDER}
    counts["categories"] = 0
    conn = _RecordingConn(counts=counts)

    with pytest.raises(LoadError) as exc:
        load_all(conn, data_dir=str(tmp_path))
    assert "categories" in str(exc.value)
    assert "mismatch" in str(exc.value).lower()
