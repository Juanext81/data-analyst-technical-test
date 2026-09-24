"""Exploratory data analysis (EDA) for the e-commerce dataset.

Prints shapes, dtypes, null counts, and summary statistics for each table,
highlights the intentional data-quality defects, and reports the headline
business metrics (AOV, top customers, top 5 products, monthly revenue).

Run:
    python -m analysis.eda
"""

from __future__ import annotations

import pandas as pd

from analysis.data_access import clean_tables, load_tables
from analysis.metrics import (
    average_order_value,
    revenue_per_customer,
    revenue_per_month,
    top_products,
)

pd.set_option("display.width", 120)
pd.set_option("display.max_columns", 20)


def _section(title: str) -> None:
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


def run_eda(data_dir: str = "data") -> None:
    raw, source = load_tables(data_dir)
    print(f"Loaded data from: {source.upper()}")

    _section("1. Table shapes")
    for name, df in raw.items():
        print(f"  {name:<15} rows={len(df):>4}  cols={df.shape[1]}")

    _section("2. Dtypes and null counts (raw)")
    for name, df in raw.items():
        print(f"\n-- {name} --")
        info = pd.DataFrame({
            "dtype": df.dtypes.astype(str),
            "nulls": df.isna().sum(),
        })
        print(info)

    _section("3. Intentional data-quality defects (raw)")
    orders = raw["orders"]
    customers = raw["customers"]
    products = raw["products"]
    print("NULLs (intentional defect targets):")
    print(f"  customers.city         : {customers['city'].isna().sum()}")
    print(f"  orders.status          : {orders['status'].isna().sum()}")
    print(f"  orders.payment_method  : {orders['payment_method'].isna().sum()}")
    print(f"  products.stock         : {products['stock'].isna().sum()}")
    print("\nRaw distinct order statuses (note inconsistent casing/whitespace):")
    print(sorted(orders["status"].dropna().astype(str).unique().tolist()))

    tables = clean_tables(raw)

    _section("4. Distinct order statuses after cleaning")
    print(sorted(tables["orders"]["status"].dropna().astype(str).unique().tolist()))

    _section("5. Numeric summary (order_details)")
    print(tables["order_details"][["quantity", "unit_price"]].describe())

    _section("6. Headline business metrics (completed orders)")
    aov = average_order_value(tables)
    print(f"Average order value (AOV): {aov:,.2f}")

    print("\nTop 5 customers by revenue:")
    print(revenue_per_customer(tables).head(5).to_string(index=False))

    print("\nTop 5 products by revenue:")
    print(top_products(tables, n=5, by="revenue").to_string(index=False))

    print("\nRevenue per month:")
    print(revenue_per_month(tables)[["month_label", "revenue", "orders"]]
          .to_string(index=False))


if __name__ == "__main__":
    run_eda()
