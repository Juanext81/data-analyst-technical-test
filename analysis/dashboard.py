"""Dash dashboard: monthly revenue trend for the e-commerce dataset.

Shows the revenue-per-month trend (completed orders) as a line chart, plus a
small KPI header (AOV, total revenue, order count) and the top-5-products
table. Data comes from RDS with a CSV fallback.

Run:
    python -m analysis.dashboard
Then open http://127.0.0.1:8050 in a browser.
"""

from __future__ import annotations

import dash
from dash import dash_table, dcc, html
import plotly.graph_objects as go

from analysis.data_access import clean_tables, load_tables
from analysis.metrics import (
    average_order_value,
    revenue_per_month,
    top_products,
)


def _build_figure(monthly) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=monthly["month_label"],
            y=monthly["revenue"],
            mode="lines+markers",
            name="Revenue",
            line=dict(color="#2b6cb0", width=3),
            marker=dict(size=8),
            hovertemplate="%{x}<br>Revenue: %{y:,.0f}<extra></extra>",
        )
    )
    fig.update_layout(
        title="Revenue per Month (completed orders)",
        xaxis_title="Month",
        yaxis_title="Revenue (COP)",
        template="plotly_white",
        margin=dict(l=60, r=30, t=60, b=60),
        height=460,
    )
    return fig


def build_app() -> dash.Dash:
    raw, source = load_tables()
    tables = clean_tables(raw)

    monthly = revenue_per_month(tables)
    aov = average_order_value(tables)
    total_revenue = float(monthly["revenue"].sum()) if not monthly.empty else 0.0
    total_orders = int(monthly["orders"].sum()) if not monthly.empty else 0
    top5 = top_products(tables, n=5, by="revenue")

    def kpi(label: str, value: str) -> html.Div:
        return html.Div(
            [html.Div(label, style={"fontSize": "13px", "color": "#666"}),
             html.Div(value, style={"fontSize": "24px", "fontWeight": "700"})],
            style={"padding": "16px 24px", "background": "#f7fafc",
                   "borderRadius": "8px", "minWidth": "170px"},
        )

    app = dash.Dash(__name__)
    app.title = "E-commerce Revenue Dashboard"
    app.layout = html.Div(
        style={"fontFamily": "system-ui, sans-serif", "maxWidth": "1000px",
               "margin": "0 auto", "padding": "24px"},
        children=[
            html.H1("E-commerce Revenue Dashboard"),
            html.P(f"Data source: {source.upper()} · metrics on completed orders",
                   style={"color": "#666"}),
            html.Div(
                [kpi("Average Order Value", f"{aov:,.0f}"),
                 kpi("Total Revenue", f"{total_revenue:,.0f}"),
                 kpi("Completed Orders", f"{total_orders:,}")],
                style={"display": "flex", "gap": "16px", "marginBottom": "24px"},
            ),
            dcc.Graph(figure=_build_figure(monthly)),
            html.H2("Top 5 products by revenue"),
            dash_table.DataTable(
                data=top5.to_dict("records"),
                columns=[
                    {"name": "Product", "id": "product_name"},
                    {"name": "Units sold", "id": "units_sold"},
                    {"name": "Revenue", "id": "revenue",
                     "type": "numeric",
                     "format": {"specifier": ",.0f"}},
                ],
                style_cell={"padding": "8px", "textAlign": "left"},
                style_header={"fontWeight": "700", "background": "#edf2f7"},
            ),
        ],
    )
    return app


if __name__ == "__main__":
    app = build_app()
    app.run(debug=False)
