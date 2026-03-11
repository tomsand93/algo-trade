"""
Unified Plotly Dash Dashboard.

One page, 3 columns (one per account) + combined totals.
Charts: equity curve, daily PnL bars, drawdown curve.
Event feed table at bottom.

Runs on a separate thread so it doesn't block the async manager.
"""

import logging
import threading
from typing import Any, Callable, Dict, Optional

import dash
from dash import dcc, html, dash_table
from dash.dependencies import Input, Output
import plotly.graph_objects as go
from plotly.subplots import make_subplots

log = logging.getLogger(__name__)

# Color scheme
COLORS = {
    "tradingView": "#1f77b4",
    "bitcoin4H": "#ff7f0e",
    "fvg": "#2ca02c",
    "combined": "#9467bd",
    "bg": "#1e1e2f",
    "card": "#2a2a3d",
    "text": "#e0e0e0",
    "green": "#00c853",
    "red": "#ff1744",
}

ACCOUNT_NAMES = ["tradingView", "bitcoin4H", "fvg"]


def create_dash_app(get_data_fn: Callable[[], Dict]) -> dash.Dash:
    """
    Create the Dash application.

    Args:
        get_data_fn: callable that returns dashboard data from the engine
    """
    app = dash.Dash(
        __name__,
        title="Multi-Account Strategy Manager",
        update_title=None,
    )

    app.layout = html.Div(
        style={"backgroundColor": COLORS["bg"], "minHeight": "100vh", "padding": "20px"},
        children=[
            # Header
            html.Div(
                style={"textAlign": "center", "marginBottom": "20px"},
                children=[
                    html.H1(
                        "Multi-Account Strategy Manager",
                        style={"color": COLORS["text"], "margin": "0"},
                    ),
                    html.P(
                        "PAPER TRADING ONLY",
                        style={"color": "#ffa726", "fontSize": "14px", "margin": "5px 0"},
                    ),
                    html.Div(id="last-update", style={"color": "#888", "fontSize": "12px"}),
                ],
            ),

            # Combined totals bar
            html.Div(id="combined-bar", style={
                "backgroundColor": COLORS["card"],
                "borderRadius": "8px",
                "padding": "15px",
                "marginBottom": "20px",
                "display": "flex",
                "justifyContent": "space-around",
            }),

            # 3-column account cards (metrics + positions)
            html.Div(
                style={"display": "flex", "gap": "15px", "marginBottom": "20px"},
                children=[
                    html.Div(id=f"card-{name}", style={
                        "flex": "1",
                        "backgroundColor": COLORS["card"],
                        "borderRadius": "8px",
                        "padding": "15px",
                        "borderTop": f"3px solid {COLORS[name]}",
                    })
                    for name in ACCOUNT_NAMES
                ],
            ),

            # Charts row
            html.Div(
                style={"display": "flex", "gap": "15px", "marginBottom": "20px"},
                children=[
                    html.Div(
                        style={"flex": "1", "backgroundColor": COLORS["card"],
                               "borderRadius": "8px", "padding": "10px"},
                        children=[dcc.Graph(id="equity-chart", config={"displayModeBar": False})],
                    ),
                    html.Div(
                        style={"flex": "1", "backgroundColor": COLORS["card"],
                               "borderRadius": "8px", "padding": "10px"},
                        children=[dcc.Graph(id="drawdown-chart", config={"displayModeBar": False})],
                    ),
                ],
            ),

            # Event feed
            html.Div(
                style={"backgroundColor": COLORS["card"], "borderRadius": "8px", "padding": "15px"},
                children=[
                    html.H3("Event Feed", style={"color": COLORS["text"], "marginTop": "0"}),
                    html.Div(id="event-feed"),
                ],
            ),

            # Auto-refresh every 15 seconds
            dcc.Interval(id="refresh-interval", interval=15_000, n_intervals=0),
        ],
    )

    @app.callback(
        [
            Output("combined-bar", "children"),
            Output("card-tradingView", "children"),
            Output("card-bitcoin4H", "children"),
            Output("card-fvg", "children"),
            Output("equity-chart", "figure"),
            Output("drawdown-chart", "figure"),
            Output("event-feed", "children"),
            Output("last-update", "children"),
        ],
        [Input("refresh-interval", "n_intervals")],
    )
    def update_dashboard(n):
        try:
            data = get_data_fn()
        except Exception as e:
            log.error("Dashboard data fetch error: %s", e)
            empty = html.Div("Error loading data", style={"color": COLORS["red"]})
            return [empty] * 7 + ["Error"]

        combined = data.get("combined", {})
        accounts = data.get("accounts", {})
        equity_histories = data.get("equity_histories", {})
        events = data.get("events", [])
        updated_at = data.get("updated_at", "")

        # Combined bar
        combined_children = _build_combined_bar(combined)

        # Account cards (with positions embedded)
        cards = []
        for name in ACCOUNT_NAMES:
            acct_data = accounts.get(name, {})
            cards.append(_build_account_card(name, acct_data))

        # Equity chart
        eq_fig = _build_equity_chart(equity_histories)

        # Drawdown chart
        dd_fig = _build_drawdown_chart(equity_histories, accounts)

        # Event feed
        event_children = _build_event_feed(events)

        return [
            combined_children,
            *cards,
            eq_fig,
            dd_fig,
            event_children,
            f"Last update: {updated_at}",
        ]

    return app


def _metric_box(label: str, value: str, color: str = "#e0e0e0") -> html.Div:
    return html.Div(
        style={"textAlign": "center"},
        children=[
            html.Div(label, style={"color": "#888", "fontSize": "11px"}),
            html.Div(value, style={"color": color, "fontSize": "20px", "fontWeight": "bold"}),
        ],
    )


def _pnl_color(val: float) -> str:
    return COLORS["green"] if val >= 0 else COLORS["red"]


def _build_combined_bar(combined: Dict) -> list:
    equity = combined.get("total_equity", 0)
    daily = combined.get("total_daily_pnl", 0)
    daily_pct = combined.get("total_daily_pnl_pct", 0)
    total = combined.get("total_pnl", 0)
    total_pct = combined.get("total_pnl_pct", 0)
    positions = combined.get("total_positions", 0)

    return [
        _metric_box("Combined Equity", f"${equity:,.2f}"),
        _metric_box("Daily PnL", f"${daily:+,.2f} ({daily_pct:+.2f}%)", _pnl_color(daily)),
        _metric_box("Total PnL", f"${total:+,.2f} ({total_pct:+.2f}%)", _pnl_color(total)),
        _metric_box("Positions", str(positions)),
    ]


def _build_account_card(name: str, acct_data: Dict) -> list:
    m = acct_data.get("metrics", {})
    risk = acct_data.get("risk", {})
    running = acct_data.get("running", False)

    equity = m.get("equity", 0)
    daily = m.get("daily_pnl", 0)
    daily_pct = m.get("daily_pnl_pct", 0)
    total = m.get("total_pnl", 0)
    total_pct = m.get("total_pnl_pct", 0)
    exposure = m.get("exposure", 0)
    dd = m.get("max_drawdown_pct", 0)
    trades = m.get("trades_today", 0)
    win_rate = m.get("win_rate", 0)
    halted = risk.get("is_halted", False)

    status_color = COLORS["red"] if halted else (COLORS["green"] if running else "#888")
    status_text = "HALTED" if halted else ("RUNNING" if running else "STOPPED")

    children = [
        html.Div(
            style={"display": "flex", "justifyContent": "space-between", "alignItems": "center"},
            children=[
                html.H3(name, style={"color": COLORS[name], "margin": "0"}),
                html.Span(status_text, style={
                    "color": status_color, "fontSize": "12px",
                    "border": f"1px solid {status_color}",
                    "borderRadius": "4px", "padding": "2px 8px",
                }),
            ],
        ),
        html.Hr(style={"borderColor": "#444", "margin": "8px 0"}),
        html.Div(style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "8px"}, children=[
            _small_metric("Equity", f"${equity:,.2f}"),
            _small_metric("Cash", f"${m.get('cash', 0):,.2f}"),
            _small_metric("Daily PnL", f"${daily:+,.2f} ({daily_pct:+.1f}%)", _pnl_color(daily)),
            _small_metric("Total PnL", f"${total:+,.2f} ({total_pct:+.1f}%)", _pnl_color(total)),
            _small_metric("Unrealized", f"${m.get('unrealized_pnl', 0):+,.2f}"),
            _small_metric("Realized", f"${m.get('realized_pnl', 0):+,.2f}"),
            _small_metric("Trades Today", str(trades)),
            _small_metric("Win Rate", f"{win_rate:.1f}%"),
            _small_metric("Max DD", f"{dd:.2f}%", COLORS["red"] if dd > 5 else COLORS["text"]),
            _small_metric("Exposure", f"{exposure:.1f}%"),
        ]),
    ]

    # Positions table embedded in card
    positions = m.get("positions", [])
    children.append(html.Hr(style={"borderColor": "#444", "margin": "10px 0 6px 0"}))
    children.append(html.Div(
        style={"display": "flex", "justifyContent": "space-between", "alignItems": "center"},
        children=[
            html.Div("Open Positions", style={"color": COLORS["text"], "fontSize": "13px", "fontWeight": "bold"}),
            html.Span(f"{len(positions)} open", style={"color": "#888", "fontSize": "11px"}),
        ],
    ))

    if not positions:
        children.append(html.Div(
            "No open positions",
            style={"color": "#666", "fontSize": "11px", "padding": "6px 0"},
        ))
    else:
        col_style = {"fontSize": "10px", "color": "#888", "padding": "3px 4px"}
        table_header = html.Div(
            style={"display": "flex", "borderBottom": "1px solid #555", "marginTop": "4px"},
            children=[
                html.Div("Symbol", style={**col_style, "width": "55px", "fontWeight": "bold"}),
                html.Div("Qty", style={**col_style, "width": "35px", "textAlign": "right"}),
                html.Div("Entry", style={**col_style, "width": "60px", "textAlign": "right"}),
                html.Div("Value", style={**col_style, "width": "65px", "textAlign": "right"}),
                html.Div("P&L", style={**col_style, "flex": "1", "textAlign": "right"}),
            ],
        )

        rows = [table_header]
        for p in positions:
            upl = p.get("unrealized_pl", 0)
            rows.append(html.Div(
                style={"display": "flex", "borderBottom": "1px solid #333", "padding": "1px 0"},
                children=[
                    html.Div(
                        p.get("symbol", ""),
                        style={"fontSize": "11px", "color": COLORS["text"],
                               "width": "55px", "padding": "3px 4px"},
                    ),
                    html.Div(
                        str(p.get("qty", 0)),
                        style={"fontSize": "11px", "color": COLORS["text"],
                               "width": "35px", "padding": "3px 4px", "textAlign": "right"},
                    ),
                    html.Div(
                        f"${p.get('avg_entry', 0):,.2f}",
                        style={"fontSize": "11px", "color": COLORS["text"],
                               "width": "60px", "padding": "3px 4px", "textAlign": "right"},
                    ),
                    html.Div(
                        f"${p.get('market_value', 0):,.2f}",
                        style={"fontSize": "11px", "color": COLORS["text"],
                               "width": "65px", "padding": "3px 4px", "textAlign": "right"},
                    ),
                    html.Div(
                        f"${upl:+,.2f}",
                        style={"fontSize": "11px", "color": _pnl_color(upl), "flex": "1",
                               "padding": "3px 4px", "textAlign": "right", "fontWeight": "bold"},
                    ),
                ],
            ))

        children.append(html.Div(
            style={"maxHeight": "160px", "overflowY": "auto"},
            children=rows,
        ))

    return children


def _small_metric(label: str, value: str, color: str = "#e0e0e0") -> html.Div:
    return html.Div(children=[
        html.Div(label, style={"color": "#888", "fontSize": "10px"}),
        html.Div(value, style={"color": color, "fontSize": "14px"}),
    ])


def _build_equity_chart(equity_histories: Dict) -> go.Figure:
    fig = go.Figure()
    fig.update_layout(
        title="Equity Curves",
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=40, r=20, t=40, b=30),
        height=300,
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )

    for name in ACCOUNT_NAMES:
        history = equity_histories.get(name, [])
        if history:
            times = [h["timestamp"] for h in history]
            equities = [h["equity"] for h in history]
            fig.add_trace(go.Scatter(
                x=times, y=equities, name=name,
                line=dict(color=COLORS[name], width=2),
            ))

    return fig


def _build_drawdown_chart(equity_histories: Dict, accounts: Dict) -> go.Figure:
    fig = go.Figure()
    fig.update_layout(
        title="Drawdown (%)",
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=40, r=20, t=40, b=30),
        height=300,
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )

    for name in ACCOUNT_NAMES:
        history = equity_histories.get(name, [])
        if history:
            equities = [h["equity"] for h in history]
            times = [h["timestamp"] for h in history]

            # Compute running drawdown
            peak = equities[0] if equities else 0
            dd_pcts = []
            for eq in equities:
                if eq > peak:
                    peak = eq
                dd = (peak - eq) / peak * 100 if peak > 0 else 0
                dd_pcts.append(-dd)  # Negative so it goes down

            fig.add_trace(go.Scatter(
                x=times, y=dd_pcts, name=name,
                line=dict(color=COLORS[name], width=2),
                fill="tozeroy",
                fillcolor=f"rgba({_hex_to_rgb(COLORS[name])}, 0.1)",
            ))

    return fig


def _hex_to_rgb(hex_color: str) -> str:
    h = hex_color.lstrip("#")
    return ", ".join(str(int(h[i : i + 2], 16)) for i in (0, 2, 4))


def _build_event_feed(events: list) -> html.Div:
    if not events:
        return html.Div("No events yet", style={"color": "#888", "padding": "10px"})

    rows = []
    for ev in events[:50]:
        type_colors = {
            "signal": "#ffa726",
            "order": "#42a5f5",
            "fill": COLORS["green"],
            "error": COLORS["red"],
            "info": "#888",
        }
        color = type_colors.get(ev.get("type", ""), "#888")

        rows.append(html.Div(
            style={
                "display": "flex", "gap": "10px", "padding": "4px 0",
                "borderBottom": "1px solid #333", "fontSize": "12px",
            },
            children=[
                html.Span(ev.get("timestamp", "")[-8:], style={"color": "#888", "width": "60px"}),
                html.Span(
                    ev.get("account", ""),
                    style={"color": COLORS.get(ev.get("account", ""), "#888"), "width": "90px"},
                ),
                html.Span(
                    ev.get("type", "").upper(),
                    style={"color": color, "width": "60px", "fontWeight": "bold"},
                ),
                html.Span(ev.get("message", ""), style={"color": COLORS["text"], "flex": "1"}),
            ],
        ))

    return html.Div(
        style={"maxHeight": "300px", "overflowY": "auto"},
        children=rows,
    )


def start_dashboard_thread(
    get_data_fn: Callable[[], Dict], port: int = 8050
) -> threading.Thread:
    """Launch the Dash dashboard on a background thread."""
    app = create_dash_app(get_data_fn)

    def _run():
        log.info("Dashboard starting on http://localhost:%d", port)
        app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

    t = threading.Thread(target=_run, daemon=True, name="dashboard")
    t.start()
    return t
