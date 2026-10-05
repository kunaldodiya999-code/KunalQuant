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
from dashboard.optimizer import OPTIMIZABLE_PARAMETERS, apply_parameter, rank_sweep, sweep_values
from dashboard.strategy_controls import STRATEGY_A, get_strategy_state, render_strategy_parameters

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


def run_backtest(
    start: date,
    end: date,
    capital: float,
    config: V2Config,
    execution_policy: V2ExecutionPolicy,
):
    start_dt = datetime.combine(start, time.min)
    end_dt = datetime.combine(end + timedelta(days=1), time.min) - timedelta(seconds=1)
    candles = load_nifty_candles(epoch_seconds(start_dt), epoch_seconds(end_dt))
    if len(candles) < 2:
        raise RuntimeError("Not enough NIFTY 1-minute candles in the selected window.")
    return run_multi_session_backtest(
        candles=candles,
        config=config,
        resolver=OptionContractResolver(DATABASE_PATH),
        option_loader=FyersOptionCandleLoader(DATABASE_PATH),
        execution_policy=execution_policy,
        capital=capital,
        indicator_provider=empty_indicator_provider,
    )


def _avg_net_r(df: pd.DataFrame) -> float:
    closed = closed_trades(df)
    if closed.empty:
        return 0.0
    values = pd.to_numeric(closed["Net R"], errors="coerce").dropna()
    return float(values.mean()) if not values.empty else 0.0


def render():
    st.set_page_config(
        page_title="KunalQuant Control Terminal",
        page_icon="📈",
        layout="wide",
    )

    # TradingView-style right control rail. The active tab is intentionally
    # collapsible: clicking it again closes the panel without losing settings.
    if "control_tab" not in st.session_state:
        st.session_state["control_tab"] = "Strategy"

    main_col, rail_col = st.columns([5.7, 1.35], gap="small")

    with rail_col:
        st.markdown("### KUNAL QUANT")
        st.caption("CONTROL RAIL")
        for tab_name, icon in (
            ("Strategy", "⚙"),
            ("Backtest", "◫"),
            ("Optimizer", "⌁"),
            ("Research", "🧪"),
        ):
            label = f"{icon}  {tab_name}"
            if st.button(
                label,
                key=f"rail_tab_{tab_name.lower()}",
                use_container_width=True,
                type="primary" if st.session_state["control_tab"] == tab_name else "secondary",
            ):
                if st.session_state["control_tab"] == tab_name:
                    st.session_state["control_tab"] = None
                else:
                    st.session_state["control_tab"] = tab_name

        st.divider()

        if st.session_state["control_tab"] == "Strategy":
            with st.container(border=True):
                render_strategy_parameters()
        elif st.session_state["control_tab"] == "Backtest":
            with st.container(border=True):
                st.markdown("#### Backtest")
                st.selectbox(
                    "Mode",
                    ["BACKTEST", "PAPER (coming next)", "LIVE (locked)"],
                    key="bt_mode",
                )
                st.selectbox("Index", ["NIFTY"], key="bt_index")
                st.selectbox("Timeframe", ["1-minute"], key="bt_timeframe")
                st.date_input("From", value=date(2025, 1, 1), key="bt_start")
                st.date_input("To", value=date(2025, 10, 31), key="bt_end")
                st.number_input(
                    "Initial capital (₹)",
                    min_value=1_000.0,
                    value=100_000.0,
                    step=5_000.0,
                    key="bt_capital",
                )
        elif st.session_state["control_tab"] == "Optimizer":
            with st.container(border=True):
                st.markdown("#### Strategy Optimizer")
                opt_state = get_strategy_state(2000.0)
                if not opt_state["available"]:
                    st.warning("Select Strategy A in the Strategy tab before optimizing.")
                else:
                    st.caption(
                        "One parameter at a time. Research only; no automatic promotion."
                    )
                    opt_param = st.selectbox(
                        "Parameter",
                        list(OPTIMIZABLE_PARAMETERS),
                        format_func=lambda x: (
                            f"{OPTIMIZABLE_PARAMETERS[x][0]} · "
                            f"{OPTIMIZABLE_PARAMETERS[x][1]}"
                        ),
                        key="opt_parameter",
                    )
                    ranges = {
                        "custom_sl_points": (10.0, 40.0, 5.0),
                        "rr_multiplier": (1.0, 4.0, 0.5),
                        "custom_tp_points": (10.0, 50.0, 5.0),
                        "lot_value_target": (7500.0, 15000.0, 2500.0),
                        "risk_per_trade_value": (1000.0, 3000.0, 500.0),
                        "risk_per_trade_percent": (0.5, 2.0, 0.25),
                        "capital_allocation_percent": (50.0, 100.0, 10.0),
                        "entry_buffer_points": (0.0, 2.0, 0.5),
                        "exit_buffer_points": (1.0, 3.0, 0.5),
                        "max_slippage_points": (1.0, 3.0, 0.5),
                        "fill_timeout_seconds": (30.0, 90.0, 15.0),
                    }
                    d_start, d_end, d_step = ranges[opt_param]
                    opt_start = st.number_input(
                        "Sweep start", value=d_start, key="opt_start"
                    )
                    opt_end = st.number_input(
                        "Sweep end", value=d_end, key="opt_end"
                    )
                    opt_step = st.number_input(
                        "Sweep step", min_value=0.01, value=d_step, key="opt_step"
                    )
                    objective = st.selectbox(
                        "Optimize for",
                        ["Net P&L", "Profit Factor", "Avg Net R", "Max DD"],
                        key="opt_objective",
                    )
                    max_runs = st.number_input(
                        "Maximum runs",
                        min_value=2,
                        max_value=25,
                        value=9,
                        step=1,
                    )
                    optimize = st.button(
                        "RUN OPTIMIZER",
                        use_container_width=True,
                        key="run_optimizer",
                    )
                    if optimize:
                        try:
                            values = sweep_values(opt_start, opt_end, opt_step)
                            if len(values) > int(max_runs):
                                raise ValueError(
                                    f"{len(values)} values requested; reduce the range "
                                    f"or increase the step. Maximum is {int(max_runs)}."
                                )
                            rows = []
                            with st.spinner(f"Running {len(values)} parameter tests…"):
                                for value in values:
                                    cfg, policy = apply_parameter(
                                        opt_state["config"],
                                        opt_state["execution_policy"],
                                        opt_param,
                                        value,
                                    )
                                    result = run_backtest(
                                        st.session_state.get("bt_start", date(2025, 1, 1)),
                                        st.session_state.get("bt_end", date(2025, 10, 31)),
                                        float(st.session_state.get("bt_capital", 100_000.0)),
                                        cfg,
                                        policy,
                                    )
                                    intended_risk = (
                                        cfg.risk_per_trade_value
                                        if cfg.risk_method == "FIXED_AMOUNT"
                                        else float(st.session_state.get("bt_capital", 100_000.0))
                                        * cfg.risk_per_trade_percent / 100.0
                                    )
                                    trade_df = build_trade_dataframe(result, intended_risk)
                                    km = key_metrics(trade_df)
                                    rows.append(
                                        {
                                            "Value": value,
                                            "Net P&L": result.net_pnl,
                                            "Profit Factor": km["profit_factor"],
                                            "Avg Net R": _avg_net_r(trade_df),
                                            "Max DD": result.max_drawdown,
                                            "Trades": result.closed,
                                            "Win Rate %": result.win_rate_pct,
                                        }
                                    )
                            ranked = rank_sweep(rows, objective)
                            st.success(f"Completed {len(ranked)} tests.")
                            st.dataframe(
                                ranked.style.format(
                                    {
                                        "Net P&L": "₹{:,.2f}",
                                        "Profit Factor": "{:.2f}",
                                        "Avg Net R": "{:.3f}",
                                        "Max DD": "₹{:,.2f}",
                                        "Win Rate %": "{:.2f}%",
                                    }
                                ),
                                use_container_width=True,
                                hide_index=True,
                            )
                            if not ranked.empty:
                                best = ranked.iloc[0]
                                st.info(
                                    f"Best by {objective}: {opt_param} = {best['Value']} · "
                                    f"Net P&L ₹{best['Net P&L']:,.2f} · "
                                    f"Max DD ₹{best['Max DD']:,.2f}"
                                )
                                st.caption(
                                    "In-sample ranking only. Any candidate must pass "
                                    "out-of-sample and robustness validation."
                                )
                        except Exception as exc:
                            st.error(str(exc))

        elif st.session_state["control_tab"] == "Research":
            with st.container(border=True):
                st.markdown("#### Research switches")
                st.checkbox("Strategy A", value=True, disabled=True, key="research_a")
                st.checkbox("Strategy B", value=False, disabled=True, key="research_b")
                st.checkbox(
                    "YT Structural Trailing",
                    value=False,
                    disabled=True,
                    key="research_trailing",
                )
                st.caption(
                    "Research modules remain isolated until independently validated "
                    "and integrated."
                )

        st.divider()
        run_requested = st.button(
            "▶ RUN BACKTEST",
            type="primary",
            use_container_width=True,
            key="rail_run_backtest",
        )

    # Strategy state survives even when the Strategy tab is collapsed.
    lab_state = get_strategy_state(2000.0)

    # Backtest controls also survive when their tab is collapsed.
    mode = st.session_state.get("bt_mode", "BACKTEST")
    index = st.session_state.get("bt_index", "NIFTY")
    timeframe = st.session_state.get("bt_timeframe", "1-minute")
    start = st.session_state.get("bt_start", date(2025, 1, 1))
    end = st.session_state.get("bt_end", date(2025, 10, 31))
    capital = float(st.session_state.get("bt_capital", 100_000.0))

    # If the user opens Strategy before Backtest, make the backtest button
    # immediately usable with the same baseline date/capital defaults.
    with main_col:
        st.title("KUNAL QUANT — CONTROL TERMINAL")
        st.caption(
            "TradingView-style right control rail. Select a strategy, edit its "
            "parameters, collapse the rail, and run the configured historical engine."
        )

        st.info(
            f"Current engine: {lab_state['strategy']} · {index} · {timeframe} · "
            f"{start.isoformat()} → {end.isoformat()}"
        )

        if lab_state["strategy"] != STRATEGY_A:
            st.warning(
                "The selected strategy is not connected to the current historical "
                "runner. Select Strategy A — Opening Breakout V2 to run a backtest."
            )

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
            f"Current engine: {lab_state['strategy']} · {index} · {timeframe} · "
            f"{start.isoformat()} → {end.isoformat()}"
        )
    
        if run_requested:
            if not lab_state["available"]:
                st.error("Select Strategy A — Opening Breakout V2 before running the backtest.")
                return
            with st.spinner("Running real historical backtest…"):
                try:
                    result = run_backtest(
                        start, end, capital,
                        lab_state["config"],
                        lab_state["execution_policy"],
                    )
                    intended_risk = (
                        lab_state["config"].risk_per_trade_value
                        if lab_state["config"].risk_method == "FIXED_AMOUNT"
                        else capital * lab_state["config"].risk_per_trade_percent / 100.0
                    )
                    st.session_state["result"] = result
                    st.session_state["trade_df"] = build_trade_dataframe(result, intended_risk)
                    st.session_state["run_start"] = start
                    st.session_state["run_end"] = end
                    st.session_state["run_risk"] = intended_risk
                    st.session_state["run_config"] = lab_state["config"]
                    st.session_state["run_policy"] = lab_state["execution_policy"]
                except Exception as exc:
                    st.exception(exc)
                    return
    
        result = st.session_state.get("result")
        if result is None:
            st.warning("Open ⚙ Strategy Lab, review the rules, then press RUN CONFIGURED BACKTEST.")
            st.markdown(
                """
                **What the current engine actually does**
    
                **Entry:** opening candidate + selected breakout trigger. The currently connected dashboard triggers are CANDLE_HIGH and CANDLE_LOW.
                
                **Option:** existing Option Contract Resolver V2 selects expiry/strike; Strategy Lab exposes its supported selection modes.
                
                **Stop / target:** fixed points, candle level, VWAP/value modes where supported; target can be points, value or RR. Current baseline is 20-point SL + 2R target.
                
                **Execution:** entry/exit buffers, max slippage and historical fill timeout are configurable. Entry window 09:15–15:10 and force exit 15:15 remain locked in this runner.
                
                **Risk:** position size is constrained by risk budget, capital allocation and complete lots, so risk budget is not always equal to actual stop risk.
                
                **Research:** ATR Structural Trailing remains isolated and is not silently mixed into this optimizer.
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
