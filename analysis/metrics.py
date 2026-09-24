"""Business metrics for the e-commerce dataset.

Revenue is defined as SUM(quantity * unit_price). Average order value (AOV)
and revenue metrics are restricted to COMPLETED orders unless otherwise noted.
All functions take the cleaned tables dict from ``analysis.data_access``.
"""

from __future__ import annotations

from typing import Dict

import pandas as pd

from analysis.data_access import order_line_revenue

COMPLETED = "completed"


def _completed_lines(tables: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Order-detail lines (with revenue) belonging to completed orders."""
    lines = order_line_revenue(tables)
    return lines[lines["status"] == COMPLETED].copy()


def average_order_value(tables: Dict[str, pd.DataFrame]) -> float:
    """Average revenue per completed order.

    AOV = total completed revenue / number of distinct completed orders.
    Returns 0.0 when there are no completed orders.
    """
    lines = _completed_lines(tables)
    if lines.empty:
        return 0.0
    per_order = lines.groupby("order_id")["revenue"].sum()
    return float(per_order.mean())


def revenue_per_customer(tables: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Total completed revenue and order count per customer, with names.

    Returns a DataFrame sorted by total_revenue descending with columns:
    customer_id, customer_name, orders, total_revenue.
    """
    lines = _completed_lines(tables)
    customers = tables["customers"]

    grouped = (
        lines.groupby("customer_id")
        .agg(orders=("order_id", "nunique"),
             total_revenue=("revenue", "sum"))
        .reset_index()
    )

    name = (customers["first_name"].astype("string") + " "
            + customers["last_name"].astype("string"))
    names = customers.assign(customer_name=name)[["customer_id", "customer_name"]]

    out = grouped.merge(names, on="customer_id", how="left")
    out = out[["customer_id", "customer_name", "orders", "total_revenue"]]
    return out.sort_values("total_revenue", ascending=False).reset_index(drop=True)


def top_products(tables: Dict[str, pd.DataFrame], n: int = 5,
                 by: str = "revenue") -> pd.DataFrame:
    """Top ``n`` products for completed orders.

    Args:
        by: "revenue" (default) ranks by total revenue; "quantity" ranks by
            units sold.

    Returns a DataFrame with product_id, product_name, units_sold, revenue.
    """
    lines = _completed_lines(tables)
    products = tables["products"][["product_id", "product_name"]]

    grouped = (
        lines.groupby("product_id")
        .agg(units_sold=("quantity", "sum"),
             revenue=("revenue", "sum"))
        .reset_index()
        .merge(products, on="product_id", how="left")
    )
    sort_col = "revenue" if by == "revenue" else "units_sold"
    grouped = grouped.sort_values(sort_col, ascending=False)
    cols = ["product_id", "product_name", "units_sold", "revenue"]
    return grouped[cols].head(n).reset_index(drop=True)


def revenue_per_month(tables: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Completed revenue by calendar month, chronologically ordered.

    Returns a DataFrame with columns: month (Period->Timestamp at month start),
    month_label (YYYY-MM), revenue, orders.
    """
    lines = _completed_lines(tables)
    if lines.empty:
        return pd.DataFrame(columns=["month", "month_label", "revenue", "orders"])

    lines["month"] = lines["order_date"].dt.to_period("M").dt.to_timestamp()
    grouped = (
        lines.groupby("month")
        .agg(revenue=("revenue", "sum"), orders=("order_id", "nunique"))
        .reset_index()
        .sort_values("month")
    )
    grouped["month_label"] = grouped["month"].dt.strftime("%Y-%m")
    return grouped[["month", "month_label", "revenue", "orders"]].reset_index(drop=True)
