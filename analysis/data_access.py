"""Data access + cleaning for the analysis layer.

Loads the five e-commerce tables into pandas DataFrames, preferring the live
RDS database (via ``db.connection``) and falling back to the generated
``data/*.csv`` files when the database is unreachable.

It also normalizes the intentional data-quality defects (mixed-case /
whitespace ``status`` and ``payment_method`` values, and NULLs) so downstream
metrics group cleanly.
"""

from __future__ import annotations

import os
from typing import Dict, Tuple

import pandas as pd

TABLES = ["categories", "customers", "products", "orders", "order_details"]

# Columns parsed as dates when reading from CSV.
_DATE_COLUMNS = {
    "customers": ["registration_date"],
    "orders": ["order_date"],
}


def load_tables(data_dir: str = "data") -> Tuple[Dict[str, pd.DataFrame], str]:
    """Load all five tables as DataFrames.

    Tries the RDS database first; on any failure, falls back to the CSVs in
    ``data_dir``.

    Returns:
        (tables, source) where ``source`` is "rds" or "csv".
    """
    try:
        tables = _load_from_rds()
        return tables, "rds"
    except Exception as exc:  # noqa: BLE001 - fall back on any DB issue
        print(f"[data_access] RDS unavailable ({type(exc).__name__}); "
              f"falling back to CSVs in {data_dir!r}.")
        return _load_from_csv(data_dir), "csv"


def _load_from_rds() -> Dict[str, pd.DataFrame]:
    """Load every table from the RDS database.

    Uses a SQLAlchemy engine (pandas' preferred connectable) built from the
    same validated parameters as ``db.connection``, with ``sslmode=require``
    to match the RDS connection policy.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.engine import URL

    from db.connection import load_config

    cfg = load_config()
    url = URL.create(
        "postgresql+psycopg2",
        username=cfg.user,
        password=cfg.password,
        host=cfg.host,
        port=cfg.port,
        database=cfg.dbname,
    )
    engine = create_engine(url, connect_args={"sslmode": "require",
                                              "connect_timeout": 10})
    try:
        return {t: pd.read_sql(f"SELECT * FROM {t}", engine) for t in TABLES}
    finally:
        engine.dispose()


def _load_from_csv(data_dir: str) -> Dict[str, pd.DataFrame]:
    """Load every table from the generated CSV files."""
    tables: Dict[str, pd.DataFrame] = {}
    for t in TABLES:
        path = os.path.join(data_dir, f"{t}.csv")
        parse_dates = _DATE_COLUMNS.get(t)
        tables[t] = pd.read_csv(path, parse_dates=parse_dates)
    return tables


def clean_tables(tables: Dict[str, pd.DataFrame]) -> Dict[str, pd.DataFrame]:
    """Normalize the intentional data-quality defects in place-safe copies.

    - Trims whitespace and lowercases ``orders.status`` and
      ``orders.payment_method`` so inconsistent casing/whitespace (e.g.
      ``"  ReTuRnEd "``) collapses to a single canonical value.
    - Leaves NULLs as NaN so callers can decide how to handle them.
    - Ensures date columns are datetime and numeric columns are numeric.
    """
    cleaned = {name: df.copy() for name, df in tables.items()}

    orders = cleaned["orders"]
    for col in ("status", "payment_method"):
        if col in orders.columns:
            orders[col] = (
                orders[col].astype("string").str.strip().str.lower()
            )
    if "order_date" in orders.columns:
        orders["order_date"] = pd.to_datetime(orders["order_date"])

    customers = cleaned["customers"]
    if "city" in customers.columns:
        # Trim/normalize but keep genuine NULLs as <NA>.
        customers["city"] = customers["city"].astype("string").str.strip()

    details = cleaned["order_details"]
    for col in ("quantity", "unit_price"):
        if col in details.columns:
            details[col] = pd.to_numeric(details[col], errors="coerce")

    products = cleaned["products"]
    for col in ("price", "stock"):
        if col in products.columns:
            products[col] = pd.to_numeric(products[col], errors="coerce")

    return cleaned


def order_line_revenue(tables: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Return order_details joined with order/customer info plus a ``revenue``
    column (quantity * unit_price)."""
    details = tables["order_details"].copy()
    orders = tables["orders"][["order_id", "customer_id", "order_date", "status"]]
    details["revenue"] = details["quantity"] * details["unit_price"]
    return details.merge(orders, on="order_id", how="left")
