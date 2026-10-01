"""Interactive Dash dashboard — dark + orange design system.

Applies the dark-orange-dashboard skill:
  • Deep navy background with warm/cool atmospheric gradients.
  • Single orange accent (#F28C38) for the primary chart series and actions.
  • KPI strip (one panel, five columns split by thin dividers).
  • Combo chart: light-blue bars + orange line, dual axis.
  • Two-column body: chart left, alerts/top-products right.
  • Dynamic filters (date range, category, status, payment) drive every KPI,
    chart, and table.

Run:
    python -m analysis.dashboard
Then open http://127.0.0.1:8050.
"""

from __future__ import annotations

import dash
from dash import Input, Output, dash_table, dcc, html
import pandas as pd
import plotly.graph_objects as go

from analysis.data_access import clean_tables, enriched_lines, load_tables

COMPLETED = "completed"

# ---------------------------------------------------------------------------
# Design tokens (from dark-orange-dashboard skill)
# ---------------------------------------------------------------------------

BG           = "#0A111D"
PANEL        = "rgba(255,255,255,0.035)"
PANEL_SOLID  = "#101927"
LINE         = "rgba(255,255,255,0.07)"
TEXT         = "#F3F5F9"
MUTED        = "#8B95A7"
ACCENT       = "#F28C38"
ACCENT_INK   = "#1A0E04"
ACCENT_SOFT  = "rgba(242,140,56,0.14)"
SERIES_2     = "#7DB3D9"
POSITIVE     = "#4FD1A5"
NEGATIVE     = "#F87171"
NEGATIVE_SOFT= "rgba(248,113,113,0.14)"
WARNING      = "#E5B94A"
WARNING_SOFT = "rgba(229,185,74,0.14)"
RADIUS       = "16px"

# Plotly chart template matching the dark theme
_CHART_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Manrope, Sora, system-ui, sans-serif", color=TEXT, size=12),
    xaxis=dict(gridcolor=LINE, linecolor=LINE, tickfont=dict(color=MUTED, size=11)),
    yaxis=dict(gridcolor=LINE, linecolor=LINE, tickfont=dict(color=MUTED, size=11)),
    margin=dict(l=52, r=52, t=56, b=44),
    legend=dict(orientation="h", y=1.08, x=0,
                font=dict(color=MUTED, size=11),
                bgcolor="rgba(0,0,0,0)"),
    hoverlabel=dict(bgcolor=PANEL_SOLID, bordercolor=LINE,
                    font=dict(color=TEXT, size=12)),
)

# ---------------------------------------------------------------------------
# Shared styles
# ---------------------------------------------------------------------------

PAGE_STYLE = {
    "fontFamily": "Manrope, Sora, system-ui, sans-serif",
    "background": (
        f"radial-gradient(900px 500px at 0% 0%, rgba(242,140,56,.16), transparent 60%),"
        f"radial-gradient(900px 600px at 100% 10%, rgba(90,110,220,.14), transparent 60%),"
        f"{BG}"
    ),
    "minHeight": "100vh",
    "color": TEXT,
    "padding": "0 0 48px",
}

def _panel(**extra):
    base = {
        "background": PANEL,
        "border": f"1px solid {LINE}",
        "borderRadius": RADIUS,
        "backdropFilter": "blur(8px)",
    }
    base.update(extra)
    return base

def _label(text: str) -> html.Div:
    return html.Div(text, style={
        "fontSize": "11px", "textTransform": "uppercase",
        "letterSpacing": ".14em", "color": MUTED, "marginBottom": "4px",
    })


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def _load_lines():
    raw, source = load_tables()
    tables = clean_tables(raw)
    lines = enriched_lines(tables)
    return lines, source


# Exact display labels for payment methods in the donut chart and dropdowns.
PAYMENT_LABELS: dict = {
    "pse":           "PSE",
    "credit_card":   "Credit Card",
    "bank_transfer": "Bank Transfer",
    "debit_card":    "Debit Card",
    "cash":          "Cash",
}


def _payment_label(raw: str) -> str:
    """Return the exact display label for a raw payment_method value."""
    return PAYMENT_LABELS.get(str(raw).lower(), str(raw).replace("_", " ").title())


def _sorted_options(series: pd.Series):
    values = sorted(v for v in series.dropna().unique())
    return [{"label": _payment_label(str(v)), "value": v} for v in values]


# ---------------------------------------------------------------------------
# KPI strip helpers
# ---------------------------------------------------------------------------

def _delta_style(good: bool) -> dict:
    color = POSITIVE if good else NEGATIVE
    return {"color": color, "fontSize": "12px", "marginTop": "2px"}


def _kpi_col(label: str, value: str, context: str = "",
             delta: str = "", delta_good: bool = True) -> html.Div:
    return html.Div(
        [
            _label(label),
            html.Div(value, style={
                "fontSize": "32px", "fontWeight": "600",
                "fontVariantNumeric": "tabular-nums", "lineHeight": "1.1",
            }),
            html.Div(context, style={"fontSize": "12px", "color": MUTED, "marginTop": "2px"}),
            html.Div(delta, style=_delta_style(delta_good)) if delta else None,
        ],
        style={"flex": "1", "padding": "20px 24px",
               "borderRight": f"1px solid {LINE}"},
    )


# ---------------------------------------------------------------------------
# Chart builders
# ---------------------------------------------------------------------------

def _fig_combo(df: pd.DataFrame) -> go.Figure:
    """Monthly revenue (orange line) + order count (light-blue bars), dual axis."""
    if df.empty:
        fig = go.Figure()
        fig.update_layout(**_CHART_LAYOUT, height=320)
        return fig

    monthly = (
        df.groupby("month_label")
        .agg(revenue=("revenue", "sum"), orders=("order_id", "nunique"))
        .reset_index().sort_values("month_label")
    )

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=monthly["month_label"], y=monthly["orders"],
        name="Orders", yaxis="y2",
        marker=dict(color=SERIES_2, opacity=0.75,
                    line=dict(width=0),
                    cornerradius=4),
        hovertemplate="%{x}<br>Orders: %{y}<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=monthly["month_label"], y=monthly["revenue"],
        name="Revenue", mode="lines+markers",
        line=dict(color=ACCENT, width=2.5, shape="spline"),
        marker=dict(color=ACCENT, size=6,
                    line=dict(color=BG, width=2)),
        hovertemplate="%{x}<br>Revenue: $%{y:,.0f}<extra></extra>",
    ))

    layout = dict(**_CHART_LAYOUT)
    layout["yaxis"] = dict(
        title="Revenue (COP)", gridcolor=LINE, linecolor=LINE,
        tickfont=dict(color=MUTED, size=11),
        tickformat="$,.0f",
    )
    layout["yaxis2"] = dict(
        title="Orders", overlaying="y", side="right",
        showgrid=False, tickfont=dict(color=MUTED, size=11),
    )
    layout["height"] = 320
    fig.update_layout(**layout)
    return fig


def _fig_by_category(df: pd.DataFrame) -> go.Figure:
    if df.empty:
        fig = go.Figure()
        fig.update_layout(**_CHART_LAYOUT, height=260)
        return fig
    grp = (df.groupby("category_name")["revenue"].sum()
           .sort_values(ascending=True).reset_index())
    fig = go.Figure(go.Bar(
        x=grp["revenue"], y=grp["category_name"],
        orientation="h",
        marker=dict(color=ACCENT, opacity=0.85,
                    line=dict(width=0), cornerradius=4),
        hovertemplate="%{y}<br>$%{x:,.0f}<extra></extra>",
    ))
    layout = dict(**_CHART_LAYOUT)
    layout["height"] = 260
    layout["xaxis"] = dict(gridcolor=LINE, linecolor=LINE,
                           tickfont=dict(color=MUTED, size=11),
                           tickformat="$,.0f")
    layout["yaxis"] = dict(gridcolor=LINE, linecolor=LINE,
                           tickfont=dict(color=TEXT, size=12))
    fig.update_layout(**layout)
    return fig


def _fig_payment(df: pd.DataFrame) -> go.Figure:
    if df.empty:
        fig = go.Figure()
        fig.update_layout(**_CHART_LAYOUT, height=260)
        return fig
    grp = df.groupby("payment_method")["revenue"].sum().reset_index()
    # Apply exact display labels: PSE, Credit Card, Bank Transfer, Debit Card, Cash.
    grp["label"] = grp["payment_method"].apply(_payment_label)
    colors = [ACCENT, SERIES_2, POSITIVE, WARNING, NEGATIVE]
    fig = go.Figure(go.Pie(
        labels=grp["label"], values=grp["revenue"],
        hole=0.55,
        marker=dict(colors=colors[:len(grp)],
                    line=dict(color=BG, width=2)),
        textfont=dict(color=TEXT, size=11),
        hovertemplate="%{label}<br>$%{value:,.0f}<extra></extra>",
    ))
    layout = dict(**_CHART_LAYOUT)
    layout["height"] = 260
    layout["showlegend"] = True
    layout["legend"] = dict(
        orientation="v", x=1.02, y=0.5,
        font=dict(color=MUTED, size=11),
        bgcolor="rgba(0,0,0,0)",
    )
    fig.update_layout(**layout)
    return fig


def _fig_top_products(df: pd.DataFrame) -> go.Figure:
    if df.empty:
        fig = go.Figure()
        fig.update_layout(**_CHART_LAYOUT, height=300)
        return fig
    grp = (df.groupby("product_name")["revenue"].sum()
           .sort_values(ascending=True).tail(8).reset_index())
    fig = go.Figure(go.Bar(
        x=grp["revenue"], y=grp["product_name"],
        orientation="h",
        marker=dict(color=SERIES_2, opacity=0.85,
                    line=dict(width=0), cornerradius=4),
        hovertemplate="%{y}<br>$%{x:,.0f}<extra></extra>",
    ))
    layout = dict(**_CHART_LAYOUT)
    layout["height"] = 300
    layout["xaxis"] = dict(gridcolor=LINE, linecolor=LINE,
                           tickfont=dict(color=MUTED, size=11),
                           tickformat="$,.0f")
    layout["yaxis"] = dict(gridcolor=LINE, linecolor=LINE,
                           tickfont=dict(color=TEXT, size=12))
    fig.update_layout(**layout)
    return fig


# ---------------------------------------------------------------------------
# Alert rows (low revenue products in current filter)
# ---------------------------------------------------------------------------

def _alert_rows(df: pd.DataFrame) -> list:
    """Bottom-3 products by revenue in the current filter — stock risk signal."""
    if df.empty:
        return [html.Div("No data", style={"color": MUTED, "padding": "12px"})]

    grp = (df.groupby(["product_name", "product_id"])
           .agg(revenue=("revenue", "sum"), units=("quantity", "sum"))
           .reset_index()
           .sort_values("revenue").head(3))

    rows = []
    for _, r in grp.iterrows():
        rows.append(html.Div([
            html.Div([
                html.Span(r["product_name"],
                          style={"color": TEXT, "fontWeight": "600",
                                 "fontSize": "13px"}),
                html.Span(f"  {int(r['units'])} units sold",
                          style={"color": MUTED, "fontSize": "11px",
                                 "marginLeft": "8px"}),
            ]),
            html.Div([
                html.Span(f"${r['revenue']:,.0f}",
                          style={"color": NEGATIVE, "fontSize": "12px",
                                 "background": NEGATIVE_SOFT,
                                 "padding": "2px 8px", "borderRadius": "6px",
                                 "letterSpacing": ".06em"}),
            ]),
        ], style={
            "display": "flex", "justifyContent": "space-between",
            "alignItems": "center",
            "padding": "10px 0",
            "borderBottom": f"1px solid {LINE}",
        }))
    return rows


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

def build_app() -> dash.Dash:
    lines, source = _load_lines()
    min_date = lines["order_date"].min()
    max_date = lines["order_date"].max()

    app = dash.Dash(__name__)
    app.title = "Commerce Ops"

    # Google Fonts (Manrope)
    app.index_string = '''
<!DOCTYPE html>
<html>
<head>
  {%metas%}
  <title>{%title%}</title>
  {%favicon%}
  {%css%}
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body { background: ''' + BG + '''; }
    ::-webkit-scrollbar { width: 6px; background: ''' + BG + '''; }
    ::-webkit-scrollbar-thumb { background: rgba(255,255,255,.12); border-radius: 3px; }

    /* ── Fix 1: filter bar stacking context above Plotly canvas ──────────
       Plotly embeds an SVG + an invisible glass <div> that intercepts
       pointer events. Setting isolation:isolate + z-index on the filter
       bar (and its parent body column) creates a stacking context that
       sits above the chart layer, restoring click / focus on dropdowns. */
    #filter-bar {
      position: relative;
      z-index: 200;
      isolation: isolate;
    }
    /* Dash Select (react-select) dropdown menu */
    .Select-menu-outer   { z-index: 9999 !important; position: absolute !important; }
    .VirtualizedSelectOption { pointer-events: auto !important; }
    /* react-dates calendar portal */
    .DateRangePicker_picker { z-index: 9999 !important; position: absolute !important; }
    .DateInput_input        { background: transparent; color: ''' + TEXT + '''; font-size: 13px; }
    .CalendarDay__default   { background: ''' + PANEL_SOLID + '''; color: ''' + TEXT + '''; }
    /* Plotly's invisible drag layer must NOT sit above the filter row */
    .js-plotly-plot .plotly .svg-container { z-index: 0 !important; }
    .js-plotly-plot .plotly .main-svg      { position: relative; z-index: 0; }

    /* ── Fix: black text for filter controls only ────────────────────────
       Scope every selector to #filter-bar so nothing outside it is affected. */
    #filter-bar .Select-value-label,
    #filter-bar .Select-placeholder,
    #filter-bar .Select-input input,
    #filter-bar .Select-option,
    #filter-bar .Select-control,
    #filter-bar .VirtualizedSelectOption  { color: #000000 !important; }
    #filter-bar .Select-menu-outer        { background: #ffffff !important; }
    #filter-bar .Select-option:hover      { background: #f0f0f0 !important; }
    /* DatePickerRange inputs */
    #filter-bar .DateInput_input          { color: #000000 !important; }
  </style>
</head>
<body>
  {%app_entry%}
  <footer>{%config%}{%scripts%}{%renderer%}</footer>
</body>
</html>
'''

    # ---- Filter bar -------------------------------------------------------
    filter_bar = html.Div(
        id="filter-bar",
        style=_panel(padding="16px 24px",
                     display="flex", gap="20px", flexWrap="wrap",
                     alignItems="flex-end", marginBottom="20px",
                     position="relative", zIndex=200, isolation="isolate"),
        children=[
            html.Div([
                _label("Date range"),
                dcc.DatePickerRange(
                    id="date-range",
                    min_date_allowed=min_date, max_date_allowed=max_date,
                    start_date=min_date, end_date=max_date,
                    display_format="YYYY-MM-DD",
                    style={"color": TEXT},
                ),
            ], style={"display": "flex", "flexDirection": "column", "gap": "4px"}),
            html.Div([
                _label("Category"),
                dcc.Dropdown(id="f-category",
                             options=_sorted_options(lines["category_name"]),
                             multi=True, placeholder="All",
                             style={"minWidth": "180px", "color": "#000000",
                                    "background": PANEL_SOLID,
                                    "border": f"1px solid {LINE}"}),
            ], style={"flex": "1", "minWidth": "160px",
                      "display": "flex", "flexDirection": "column", "gap": "4px"}),
            html.Div([
                _label("Status"),
                dcc.Dropdown(id="f-status",
                             options=_sorted_options(lines["status"]),
                             multi=True, placeholder="All",
                             style={"minWidth": "160px", "color": "#000000",
                                    "background": PANEL_SOLID,
                                    "border": f"1px solid {LINE}"}),
            ], style={"flex": "1", "minWidth": "150px",
                      "display": "flex", "flexDirection": "column", "gap": "4px"}),
            html.Div([
                _label("Payment"),
                dcc.Dropdown(id="f-payment",
                             options=_sorted_options(lines["payment_method"]),
                             multi=True, placeholder="All",
                             style={"minWidth": "160px", "color": "#000000",
                                    "background": PANEL_SOLID,
                                    "border": f"1px solid {LINE}"}),
            ], style={"flex": "1", "minWidth": "150px",
                      "display": "flex", "flexDirection": "column", "gap": "4px"}),
        ],
    )

    # ---- Layout -----------------------------------------------------------
    app.layout = html.Div(style=PAGE_STYLE, children=[

        # Header
        html.Div(style={"padding": "32px 32px 0"}, children=[
            html.Div("COMMERCE OPS", style={
                "fontSize": "11px", "letterSpacing": ".14em",
                "textTransform": "uppercase", "color": MUTED, "marginBottom": "6px",
            }),
            html.Div(style={"display": "flex", "alignItems": "center",
                            "justifyContent": "space-between", "flexWrap": "wrap",
                            "gap": "12px", "marginBottom": "6px"}, children=[
                html.H1("E-commerce Analytics", style={
                    "fontSize": "36px", "fontWeight": "600",
                    "color": TEXT, "margin": "0",
                    "display": "flex", "alignItems": "center", "gap": "12px",
                }),
                html.Div(style={"display": "flex", "gap": "10px"}, children=[
                    html.Div(
                        f"Source: {source.upper()}",
                        style={
                            "padding": "8px 18px",
                            "background": PANEL,
                            "border": f"1px solid {LINE}",
                            "borderRadius": "10px",
                            "color": TEXT, "fontSize": "13px",
                            "cursor": "default",
                        }
                    ),
                ]),
            ]),
            html.P("Monitor daily sales, fulfillment pace, and revenue risk from one compact workspace.",
                   style={"color": MUTED, "fontSize": "14px", "marginBottom": "24px"}),
        ]),

        # Body
        html.Div(style={"padding": "0 32px"}, children=[

            filter_bar,

            # KPI strip — one panel, five columns
            html.Div(id="kpi-strip", style=_panel(
                display="flex", marginBottom="20px", overflow="hidden",
            )),

            # Two-column: combo chart left + alerts/donut right
            html.Div(style={"display": "flex", "gap": "16px",
                            "marginBottom": "16px", "flexWrap": "wrap"}, children=[
                # Left: combo chart
                html.Div(style={**_panel(padding="20px 24px"), "flex": "2",
                                "minWidth": "340px"}, children=[
                    html.Div(style={"display": "flex", "alignItems": "flex-start",
                                    "justifyContent": "space-between",
                                    "marginBottom": "4px"}, children=[
                        html.Div([
                            html.Div("Revenue & orders per month",
                                     style={"fontSize": "18px", "fontWeight": "600",
                                            "color": TEXT}),
                            html.Div("Completed + all statuses · monthly aggregates",
                                     style={"fontSize": "13px", "color": MUTED,
                                            "marginTop": "2px"}),
                        ]),
                        html.Div(style={"display": "flex", "gap": "14px",
                                        "alignItems": "center"}, children=[
                            html.Span(style={"display": "flex", "alignItems": "center",
                                             "gap": "6px", "fontSize": "12px",
                                             "color": MUTED}, children=[
                                html.Span(style={"width": "10px", "height": "10px",
                                                 "borderRadius": "50%",
                                                 "background": ACCENT,
                                                 "display": "inline-block"}),
                                "Revenue",
                            ]),
                            html.Span(style={"display": "flex", "alignItems": "center",
                                             "gap": "6px", "fontSize": "12px",
                                             "color": MUTED}, children=[
                                html.Span(style={"width": "10px", "height": "10px",
                                                 "borderRadius": "50%",
                                                 "background": SERIES_2,
                                                 "display": "inline-block"}),
                                "Orders",
                            ]),
                        ]),
                    ]),
                    dcc.Graph(id="fig-combo", config={"displayModeBar": False}),
                ]),
                # Right: alerts + payment donut
                html.Div(style={"flex": "1", "minWidth": "280px",
                                "display": "flex", "flexDirection": "column",
                                "gap": "16px"}, children=[
                    # Low-revenue alert panel
                    html.Div(style=_panel(padding="20px 24px"), children=[
                        html.Div(style={"display": "flex", "alignItems": "center",
                                        "gap": "10px", "marginBottom": "12px"}, children=[
                            html.Span("⚠", style={"color": WARNING, "fontSize": "16px"}),
                            html.Span("Lowest revenue products",
                                      style={"fontWeight": "600", "fontSize": "15px"}),
                            html.Span(id="alert-badge",
                                      style={"background": WARNING_SOFT,
                                             "color": WARNING,
                                             "fontSize": "11px",
                                             "padding": "2px 8px",
                                             "borderRadius": "6px",
                                             "letterSpacing": ".08em"}),
                        ]),
                        html.Div(id="alert-rows"),
                    ]),
                    # Payment donut
                    html.Div(style=_panel(padding="20px 24px"), children=[
                        html.Div("Revenue by payment method",
                                 style={"fontSize": "15px", "fontWeight": "600",
                                        "marginBottom": "4px"}),
                        dcc.Graph(id="fig-payment",
                                  config={"displayModeBar": False}),
                    ]),
                ]),
            ]),

            # Second row: category bars + top products
            html.Div(style={"display": "flex", "gap": "16px",
                            "marginBottom": "16px", "flexWrap": "wrap"}, children=[
                html.Div(style={**_panel(padding="20px 24px"), "flex": "1",
                                "minWidth": "280px"}, children=[
                    html.Div("Revenue by category",
                             style={"fontSize": "15px", "fontWeight": "600",
                                    "marginBottom": "12px"}),
                    dcc.Graph(id="fig-category", config={"displayModeBar": False}),
                ]),
                html.Div(style={**_panel(padding="20px 24px"), "flex": "1",
                                "minWidth": "280px"}, children=[
                    html.Div("Top products · revenue",
                             style={"fontSize": "15px", "fontWeight": "600",
                                    "marginBottom": "12px"}),
                    dcc.Graph(id="fig-products", config={"displayModeBar": False}),
                ]),
            ]),

            # Data exploration table
            html.Div(style=_panel(padding="20px 24px"), children=[
                html.Div("Explore order-detail lines",
                         style={"fontSize": "18px", "fontWeight": "600",
                                "marginBottom": "4px"}),
                html.P("Sort or filter any column · paginated · matches current filters above",
                       style={"fontSize": "13px", "color": MUTED,
                              "marginBottom": "14px"}),
                dash_table.DataTable(
                    id="data-table",
                    columns=[
                        {"name": "Order",    "id": "order_id"},
                        {"name": "Date",     "id": "order_date"},
                        {"name": "Customer", "id": "customer_name"},
                        {"name": "City",     "id": "city"},
                        {"name": "Category", "id": "category_name"},
                        {"name": "Product",  "id": "product_name"},
                        {"name": "Status",   "id": "status"},
                        {"name": "Payment",  "id": "payment_method"},
                        {"name": "Qty",      "id": "quantity",    "type": "numeric"},
                        {"name": "Unit price","id": "unit_price", "type": "numeric",
                         "format": {"specifier": ",.0f"}},
                        {"name": "Revenue",  "id": "revenue",     "type": "numeric",
                         "format": {"specifier": ",.0f"}},
                    ],
                    page_size=12,
                    sort_action="native",
                    filter_action="native",
                    style_table={"overflowX": "auto"},
                    style_cell={
                        "padding": "9px 12px",
                        "textAlign": "left",
                        "fontSize": "12px",
                        "fontFamily": "Manrope, system-ui, sans-serif",
                        "background": "transparent",
                        "color": TEXT,
                        "border": f"1px solid {LINE}",
                    },
                    style_header={
                        "fontWeight": "700",
                        "background": PANEL_SOLID,
                        "color": MUTED,
                        "textTransform": "uppercase",
                        "fontSize": "11px",
                        "letterSpacing": ".10em",
                        "border": f"1px solid {LINE}",
                    },
                    style_data={
                        "background": "transparent",
                        "border": f"1px solid {LINE}",
                    },
                    style_data_conditional=[
                        {"if": {"row_index": "odd"},
                         "background": "rgba(255,255,255,.02)"},
                        {"if": {"filter_query": "{status} = completed",
                                "column_id": "status"},
                         "color": POSITIVE, "fontWeight": "600"},
                        {"if": {"filter_query": "{status} = cancelled",
                                "column_id": "status"},
                         "color": NEGATIVE},
                        {"if": {"filter_query": "{status} = returned",
                                "column_id": "status"},
                         "color": WARNING},
                    ],
                    style_filter={
                        "background": PANEL_SOLID,
                        "color": TEXT,
                        "border": f"1px solid {LINE}",
                    },
                ),
            ]),
        ]),
    ])

    # -----------------------------------------------------------------------
    # Single callback: filters → everything
    # -----------------------------------------------------------------------

    @app.callback(
        Output("kpi-strip",    "children"),
        Output("fig-combo",    "figure"),
        Output("fig-category", "figure"),
        Output("fig-payment",  "figure"),
        Output("fig-products", "figure"),
        Output("alert-rows",   "children"),
        Output("alert-badge",  "children"),
        Output("data-table",   "data"),
        Input("date-range",    "start_date"),
        Input("date-range",    "end_date"),
        Input("f-category",    "value"),
        Input("f-status",      "value"),
        Input("f-payment",     "value"),
    )
    def _update(start_date, end_date, categories, statuses, payments):
        df = lines.copy()
        if start_date:
            df = df[df["order_date"] >= pd.to_datetime(start_date)]
        if end_date:
            df = df[df["order_date"] <= pd.to_datetime(end_date)]
        if categories:
            df = df[df["category_name"].isin(categories)]
        if statuses:
            df = df[df["status"].isin(statuses)]
        if payments:
            df = df[df["payment_method"].isin(payments)]

        completed = df[df["status"] == COMPLETED]

        total_rev   = float(df["revenue"].sum())
        comp_rev    = float(completed["revenue"].sum())
        n_orders    = int(df["order_id"].nunique())
        n_comp_ord  = int(completed["order_id"].nunique())
        n_units     = int(df["quantity"].sum()) if not df.empty else 0
        n_customers = int(df["customer_id"].nunique())
        aov_val     = completed.groupby("order_id")["revenue"].sum().mean()
        aov         = float(aov_val) if pd.notna(aov_val) else 0.0

        kpi_strip = [
            _kpi_col("Total revenue", f"${total_rev:,.0f}",
                     f"{n_orders:,} orders"),
            _kpi_col("Completed revenue", f"${comp_rev:,.0f}",
                     f"{n_comp_ord:,} completed"),
            _kpi_col("Avg order value", f"${aov:,.0f}",
                     "completed orders only"),
            _kpi_col("Units sold", f"{n_units:,}",
                     f"{len(df):,} line items"),
            _kpi_col("Unique customers", f"{n_customers:,}",
                     "in selection",
                     delta="", delta_good=True),
        ]
        # Remove right border from last column
        kpi_strip[-1].style["borderRight"] = "none"

        alert_rows  = _alert_rows(df)
        alert_badge = f"{len(alert_rows)} LOW"

        table_df = df.sort_values("order_date").copy()
        table_df["order_date"] = table_df["order_date"].dt.strftime("%Y-%m-%d")
        table_cols = ["order_id", "order_date", "customer_name", "city",
                      "category_name", "product_name", "status",
                      "payment_method", "quantity", "unit_price", "revenue"]
        table_data = table_df[table_cols].to_dict("records")

        return (
            kpi_strip,
            _fig_combo(df),
            _fig_by_category(df),
            _fig_payment(df),
            _fig_top_products(df),
            alert_rows,
            alert_badge,
            table_data,
        )

    return app


if __name__ == "__main__":
    app = build_app()
    app.run(debug=False)
