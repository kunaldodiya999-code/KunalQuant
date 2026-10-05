"""KunalQuant control dashboard.

Thin Streamlit UI over the existing Opening Breakout V2 historical engine.
Production strategy/risk/execution modules are not modified here.
"""

from __future__ import annotations

import sqlite3
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest.opening_breakout_v2_multi_session import run_multi_session_backtest
from config.settings import DATABASE_PATH
from execution.opening_breakout_v2_execution import V2ExecutionPolicy
from research.opening_breakout_1m_v2 import Candle, IndicatorSnapshot, V2Config
from strategies.option_contract_resolver import OptionContractResolver
from backtest.fyers_option_candles import FyersOptionCandleLoader
from dashboard.analytics import (
    build_trade_dataframe,
    closed_trades,
    exit_summary,
    key_metrics,
    monthly_summary,
)

IST = ZoneInfo("Asia/Kolkata")


@st.cache_data(show_spinner=False)
def load_nifty_candles(start_ts: int, end_ts: int) -> list[Candle]:
    with sqlite3.connect(DATABASE_PATH) as connection:
        rows = connection.execute(
            """
            SELECT c.timestamp, c.open, c.high, c.low, c.close
            FROM candles c
            JOIN instruments i ON i.id = c.instrument_id
            WHERE i.broker = 'FYERS'
              AND i.symbol = 'NSE:NIFTY50-INDEX'
              AND c.resolution = '1'
              AND c.timestamp BETWEEN ? AND ?
            ORDER BY c.timestamp
            """,
            (start_ts, end_ts),
        ).fetchall()
    return [Candle(int(ts), float(o), float(h), float(l), float(c)) for ts, o, h, l, c in rows]


def epoch_seconds(value: datetime) -> int:
    return int(value.replace(tzinfo=IST).timestamp())


def empty_indicator_provider(timestamp: int, candle: Candle) -> IndicatorSnapshot:
    return IndicatorSnapshot()


def run_backtest(start: date, end: date, capital: float, risk: float):
    start_dt = datetime.combine(start, time.min)
    end_dt = datetime.combine(end + timedelta(days=1), time.min) - timedelta(seconds=1)

    candles = load_nifty_candles(epoch_seconds(start_dt), epoch_seconds(end_dt))
    if len(candles) < 2:
        raise RuntimeError("Not enough NIFTY 1-minute candles in the selected window.")

    config = V2Config(
        trade_instrument="CALL",
        market_bias="NEUTRAL",
        selected_timeframes=("1M",),
        selected_triggers=("CANDLE_HIGH",),
        filter_open_high=False,
        filter_open_low=False,
        custom_sl_points=20.0,
        tp_mode="RR_RATIO",
        rr_multiplier=2.0,
        risk_per_trade_value=risk,
        capital_allocation_percent=100.0,
    )

    return run_multi_session_backtest(
        candles=candles,
        config=config,
        resolver=OptionContractResolver(DATABASE_PATH),
        option_loader=FyersOptionCandleLoader(DATABASE_PATH),
        execution_policy=V2ExecutionPolicy(
            entry_buffer_points=1.0,
            max_slippage_points=2.0,
            fill_timeout_seconds=60,
        ),
        capital=capital,
        indicator_provider=empty_indicator_provider,
    )


def render():
    st.set_page_config(
        page_title="KunalQuant Control Terminal",
        page_icon="📈",
        layout="wide",
    )

    st.title("KUNAL QUANT — CONTROL TERMINAL")
    st.caption("Interactive research/control layer over the existing historical backtest engine.")

    with st.sidebar:
        st.header("Backtest Controls")
        mode = st.selectbox("Mode", ["BACKTEST", "PAPER (coming next)", "LIVE (locked)"])
        strategy = st.selectbox("Strategy", ["Opening Breakout V2"])
        index = st.selectbox("Index", ["NIFTY"])
        timeframe = st.selectbox("Timeframe", ["1-minute"])
        start = st.date_input("From", value=date(2025, 1, 1))
        end = st.date_input("To", value=date(2025, 10, 31))
        capital = st.number_input(
            "Initial capital (₹)", min_value=1_000.0, value=100_000.0, step=5_000.0
        )
        risk = st.number_input(
            "Risk / trade (₹)", min_value=100.0, value=2_000.0, step=100.0
        )

        st.subheader("Research switches")
        st.checkbox("Strategy A", value=True, disabled=True)
        st.checkbox("Strategy B", value=False, disabled=True)
        st.checkbox("YT Structural Trailing", value=False, disabled=True)
        st.caption(
            "Research switches remain locked until independently integrated and validated."
        )

        run = st.button("▶ RUN BACKTEST", type="primary", use_container_width=True)

    if mode != "BACKTEST":
        st.warning(f"{mode} is intentionally disabled in this milestone.")
        st.info(
            "Paper mode will reuse the same strategy/risk/analytics layer after "
            "the historical control panel is validated."
        )
        return

    if start > end:
        st.error("From date must be on or before To date.")
        return

    st.info(
        f"Current engine: {strategy} · {index} · {timeframe} · "
        f"{start.isoformat()} → {end.isoformat()}"
    )

    if run:
        with st.spinner("Running real historical backtest…"):
            try:
                result = run_backtest(start, end, capital, risk)
                st.session_state["result"] = result
                st.session_state["trade_df"] = build_trade_dataframe(result, risk)
                st.session_state["run_start"] = start
                st.session_state["run_end"] = end
                st.session_state["run_risk"] = risk
            except Exception as exc:
                st.exception(exc)
                return

    result = st.session_state.get("result")
    if result is None:
        st.warning("Set the controls and press RUN BACKTEST.")
        st.markdown(
            """
            **What is already connected**

            - Real FYERS-stored NIFTY 1-minute candles
            - Existing Opening Breakout V2 signal engine
            - Existing option contract resolver
            - Existing historical option candle loader
            - Existing execution/fill policy
            - Existing broker cost model
            - Existing portfolio accounting
            """
        )
        return

    df = st.session_state.get("trade_df", pd.DataFrame())
    closed = closed_trades(df)
    metrics = key_metrics(df)
    net_pct = (
        result.net_pnl / result.initial_capital * 100.0
        if result.initial_capital
        else 0.0
    )

    st.subheader("Performance")
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Net P&L", f"₹{result.net_pnl:,.2f}", f"{net_pct:.2f}%")
    c2.metric("Trades", result.closed)
    c3.metric("Win rate", f"{result.win_rate_pct:.2f}%")
    c4.metric("Max DD", f"₹{result.max_drawdown:,.2f}")
    c5.metric("Gross P&L", f"₹{result.gross_pnl:,.2f}")
    c6.metric("Costs", f"₹{result.total_costs:,.2f}")

    k1, k2, k3, k4, k5, k6 = st.columns(6)
    pf = metrics["profit_factor"]
    k1.metric("Profit Factor", "∞" if pf == float("inf") else f"{pf:.2f}")
    k2.metric("Expectancy / trade", f"₹{metrics['expectancy']:,.2f}")
    k3.metric("Avg Winner", f"₹{metrics['avg_winner']:,.2f}")
    k4.metric("Avg Loser", f"₹{metrics['avg_loser']:,.2f}")
    k5.metric("Best Trade", f"₹{metrics['best_trade']:,.2f}")
    k6.metric("Worst Trade", f"₹{metrics['worst_trade']:,.2f}")

    left, right = st.columns([2, 1])
    with left:
        st.subheader("Equity Curve")
        equity = pd.DataFrame(
            {
                "Equity": [point.equity for point in result.equity_curve],
            },
            index=[
                datetime.fromtimestamp(point.timestamp, tz=IST)
                for point in result.equity_curve
            ],
        )
        st.line_chart(equity, height=320)

        st.subheader("Drawdown")
        drawdown = pd.DataFrame(
            {
                "Drawdown": [point.drawdown for point in result.equity_curve],
            },
            index=[
                datetime.fromtimestamp(point.timestamp, tz=IST)
                for point in result.equity_curve
            ],
        )
        st.area_chart(drawdown, height=240)

    with right:
        st.subheader("Run Summary")
        st.write(
            {
                "NIFTY candles": len(
                    load_nifty_candles(
                        epoch_seconds(datetime.combine(st.session_state.get("run_start", date(2025, 1, 1)), time.min)),
                        epoch_seconds(
                            datetime.combine(
                                st.session_state.get("run_end", date(2025, 10, 31)) + timedelta(days=1),
                                time.min,
                            )
                            - timedelta(seconds=1)
                        ),
                    )
                ),
                "Sessions": result.sessions,
                "Signals": result.signals,
                "Closed": result.closed,
                "Rejected": result.rejected,
                "Wins": result.wins,
                "Losses": result.losses,
                "Ending equity": round(result.ending_equity, 2),
            }
        )

        st.subheader("Data Quality / Rejections")
        if result.rejection_reasons:
            rejection_rows = [
                {"Reason": reason, "Count": count}
                for reason, count in result.rejection_reasons
            ]
            st.dataframe(pd.DataFrame(rejection_rows), use_container_width=True, hide_index=True)
        else:
            st.success("No rejected trades in this run.")

    st.subheader("Monthly Performance")
    monthly = monthly_summary(df)
    if not monthly.empty:
        chart = monthly.set_index("Month")[["Net P&L"]]
        st.bar_chart(chart, height=280)
        st.dataframe(
            monthly.style.format(
                {
                    "Win Rate %": "{:.2f}%",
                    "Gross P&L": "₹{:,.2f}",
                    "Costs": "₹{:,.2f}",
                    "Net P&L": "₹{:,.2f}",
                    "Avg Net/Trade": "₹{:,.2f}",
                }
            ),
            use_container_width=True,
            hide_index=True,
        )

    st.subheader("Exit Analysis")
    exits = exit_summary(df)
    if not exits.empty:
        st.dataframe(
            exits.style.format(
                {
                    "Win Rate %": "{:.2f}%",
                    "Gross P&L": "₹{:,.2f}",
                    "Net P&L": "₹{:,.2f}",
                }
            ),
            use_container_width=True,
            hide_index=True,
        )

    st.subheader("Risk & Trade Mechanics")
    r1, r2, r3, r4, r5, r6 = st.columns(6)
    r1.metric("Avg holding", f"{metrics['avg_holding_minutes']:.1f} min")
    r2.metric("Max win streak", int(metrics["max_win_streak"]))
    r3.metric("Max loss streak", int(metrics["max_loss_streak"]))
    if not closed.empty:
        avg_r = closed["Realized R"].dropna().mean()
        avg_net_r = closed["Net R"].dropna().mean()
        avg_risk = closed["Strategy Risk"].dropna().mean()
        r4.metric("Avg realized R", f"{avg_r:.2f}" if pd.notna(avg_r) else "N/A")
        r5.metric("Avg net R", f"{avg_net_r:.2f}" if pd.notna(avg_net_r) else "N/A")
        r6.metric("Avg actual stop risk", f"₹{avg_risk:,.2f}" if pd.notna(avg_risk) else "N/A")
    else:
        r4.metric("Avg realized R", "N/A")
        r5.metric("Avg net R", "N/A")
        r6.metric("Avg actual stop risk", "N/A")

    if not closed.empty:
        cost_cols = ["Brokerage", "Exchange Txn", "STT", "SEBI", "Stamp Duty", "IPFT", "GST"]
        cost_values = closed[cost_cols].sum()
        cost_df = pd.DataFrame({"Cost Component": cost_values.index, "Amount": cost_values.values})
        mc1, mc2 = st.columns([1, 2])
        with mc1:
            st.subheader("Broker Cost Breakdown")
            st.dataframe(
                cost_df.style.format({"Amount": "₹{:,.2f}"}),
                use_container_width=True,
                hide_index=True,
            )
        with mc2:
            st.subheader("Cost Components")
            st.bar_chart(cost_df.set_index("Cost Component")[["Amount"]], height=260)

    st.subheader("Trade Log")
    if not df.empty:
        f1, f2, f3 = st.columns(3)
        with f1:
            status_filter = st.multiselect(
                "Status",
                sorted(df["Status"].dropna().unique()),
                default=sorted(df["Status"].dropna().unique()),
            )
        with f2:
            exit_filter = st.multiselect(
                "Exit reason",
                sorted(df["Exit Reason"].dropna().unique()),
                default=sorted(df["Exit Reason"].dropna().unique()),
            )
        with f3:
            contract_filter = st.text_input("Contract contains", "")

        filtered = df[df["Status"].isin(status_filter)]
        if exit_filter:
            filtered = filtered[filtered["Exit Reason"].isin(exit_filter) | filtered["Exit Reason"].isna()]
        if contract_filter:
            filtered = filtered[
                filtered["Contract"].str.contains(contract_filter, case=False, na=False)
            ]

        display_columns = [
            "Date", "Time", "Contract", "Direction", "Status", "Entry", "Exit",
            "Qty", "Lots", "Stop", "Target", "Gross P&L", "Costs", "Net P&L",
            "Exit Reason", "Holding (min)", "Strategy Risk", "Realized R", "Net R",
        ]
        st.dataframe(
            filtered[display_columns],
            use_container_width=True,
            hide_index=True,
        )

    st.caption(
        "Dashboard is display/control only. It does not alter locked strategy definitions, "
        "option selection, risk rules, execution behavior, lifecycle, or accounting."
    )


if __name__ == "__main__":
    render()
