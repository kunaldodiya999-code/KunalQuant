"""Interactive Opening Breakout V2 strategy controls for the dashboard.

This module only builds user-selected V2Config/V2ExecutionPolicy values.
It does not alter the underlying strategy or execution engine.
"""
from __future__ import annotations

from dataclasses import asdict
from typing import Any

import streamlit as st

from execution.opening_breakout_v2_execution import V2ExecutionPolicy
from research.opening_breakout_1m_v2 import V2Config


def render_strategy_lab(default_risk: float) -> dict[str, Any]:
    """Render the right-side Strategy Lab popover and return selected settings."""
    st.markdown("### Strategy Lab")
    st.caption(
        "Change one rule at a time, run the backtest, then validate any improvement out-of-sample."
    )

    with st.expander("1. Entry / signal", expanded=True):
        bias = st.selectbox(
            "Market bias",
            ["NEUTRAL", "UP", "DOWN"],
            index=0,
            key="lab_bias",
            help="NEUTRAL allows the configured instrument direction; UP/DOWN filters direction.",
        )
        instrument = st.selectbox(
            "Trade instrument",
            ["CALL", "PUT"],
            index=0,
            key="lab_instrument",
        )
        trigger = st.selectbox(
            "Breakout trigger",
            ["CANDLE_HIGH", "CANDLE_LOW"],
            index=0,
            key="lab_trigger",
            help="These are the triggers currently connected to the real historical runner.",
        )
        filter_open_low = st.checkbox(
            "Require OPEN = LOW",
            value=False,
            key="lab_open_low",
            help="Current dashboard baseline is OFF.",
        )
        filter_open_high = st.checkbox(
            "Require OPEN = HIGH",
            value=False,
            key="lab_open_high",
            help="Current dashboard baseline is OFF.",
        )
        open_tolerance = st.number_input(
            "OPEN equality tolerance (points)",
            min_value=0.0,
            value=0.05,
            step=0.05,
            key="lab_open_tolerance",
        )

    with st.expander("2. Option selection", expanded=False):
        strike_mode = st.selectbox(
            "Strike selector",
            ["LOT_VALUE", "PRICE_RANGE", "ATM_DISTANCE"],
            index=0,
            key="lab_strike_mode",
            help="The resolver uses this deterministic selection mode.",
        )
        lot_value = st.number_input(
            "Target option value (₹ = LTP × lot)",
            min_value=100.0,
            value=10000.0,
            step=500.0,
            key="lab_lot_value",
        )
        price_min = st.number_input(
            "Option LTP minimum",
            min_value=0.01,
            value=80.0,
            step=5.0,
            key="lab_price_min",
        )
        price_max = st.number_input(
            "Option LTP maximum",
            min_value=0.01,
            value=100.0,
            step=5.0,
            key="lab_price_max",
        )
        atm_distance = st.number_input(
            "ATM distance (points)",
            min_value=0.0,
            value=0.0,
            step=50.0,
            key="lab_atm_distance",
        )

    with st.expander("3. Stop loss / target", expanded=True):
        sl_mode = st.selectbox(
            "Stop-loss mode",
            ["CUSTOM_POINTS", "CANDLE_1_LOW", "CANDLE_1_HIGH", "VWAP", "VALUE", "OFF"],
            index=0,
            key="lab_sl_mode",
        )
        custom_sl = st.number_input(
            "Stop-loss points",
            min_value=0.01,
            value=20.0,
            step=1.0,
            key="lab_custom_sl",
        )
        sl_cap = st.number_input(
            "Stop-loss value cap (₹)",
            min_value=100.0,
            value=10000.0,
            step=500.0,
            key="lab_sl_cap",
        )
        tp_mode = st.selectbox(
            "Target mode",
            ["RR_RATIO", "CUSTOM_POINTS", "VALUE", "OFF"],
            index=0,
            key="lab_tp_mode",
        )
        rr = st.number_input(
            "Reward / Risk",
            min_value=0.1,
            value=2.0,
            step=0.25,
            key="lab_rr",
        )
        custom_tp = st.number_input(
            "Target points",
            min_value=0.01,
            value=20.0,
            step=1.0,
            key="lab_custom_tp",
        )
        tp_value = st.number_input(
            "Target value (₹)",
            min_value=100.0,
            value=10000.0,
            step=500.0,
            key="lab_tp_value",
        )

    with st.expander("4. Position sizing", expanded=False):
        risk_method = st.selectbox(
            "Risk method",
            ["FIXED_AMOUNT", "PERCENT_OF_CAPITAL"],
            index=0,
            key="lab_risk_method",
        )
        risk_value = st.number_input(
            "Risk / trade (₹)",
            min_value=100.0,
            value=float(default_risk),
            step=100.0,
            key="lab_risk_value",
        )
        risk_pct = st.number_input(
            "Risk / trade (%)",
            min_value=0.01,
            max_value=100.0,
            value=1.0,
            step=0.25,
            key="lab_risk_pct",
        )
        allocation = st.number_input(
            "Capital allocation (%)",
            min_value=1.0,
            max_value=100.0,
            value=100.0,
            step=5.0,
            key="lab_allocation",
        )

    with st.expander("5. Execution assumptions", expanded=False):
        entry_buffer = st.number_input(
            "Entry buffer (points)",
            min_value=0.0,
            value=1.0,
            step=0.5,
            key="lab_entry_buffer",
        )
        exit_buffer = st.number_input(
            "Exit buffer (points)",
            min_value=0.0,
            value=2.0,
            step=0.5,
            key="lab_exit_buffer",
        )
        max_slippage = st.number_input(
            "Max slippage (points)",
            min_value=0.0,
            value=2.0,
            step=0.5,
            key="lab_max_slippage",
        )
        fill_timeout = st.number_input(
            "Historical fill timeout (seconds)",
            min_value=1,
            value=60,
            step=5,
            key="lab_fill_timeout",
        )
        st.info(
            "Entry window 09:15–15:10 and force exit 15:15 remain locked to the current runner."
        )

    st.warning(
        "Trailing management is intentionally not editable here. "
        "The ATR structural trailing work remains an isolated research experiment."
    )

    config = V2Config(
        capital_allocation_percent=float(allocation),
        selected_timeframes=("1M",),
        market_bias=bias,
        trade_instrument=instrument,
        filter_open_high=filter_open_high,
        filter_open_low=filter_open_low,
        open_equal_tolerance_points=float(open_tolerance),
        selected_triggers=(trigger,),
        strike_selector_mode=strike_mode,
        lot_value_target=float(lot_value),
        option_price_min=float(price_min),
        option_price_max=float(price_max),
        atm_distance_points=float(atm_distance),
        sl_mode=sl_mode,
        custom_sl_points=float(custom_sl),
        sl_value_cap=float(sl_cap),
        tp_mode=tp_mode,
        custom_tp_points=float(custom_tp),
        tp_value_target=float(tp_value),
        rr_multiplier=float(rr),
        trailing_enabled=False,
        risk_method=risk_method,
        risk_per_trade_value=float(risk_value),
        risk_per_trade_percent=float(risk_pct),
    )
    policy = V2ExecutionPolicy(
        entry_buffer_points=float(entry_buffer),
        exit_buffer_points=float(exit_buffer),
        max_slippage_points=float(max_slippage),
        fill_timeout_seconds=int(fill_timeout),
    )
    return {"config": config, "execution_policy": policy, "summary": asdict(config)}
