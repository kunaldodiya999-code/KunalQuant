"""Strategy controls for the KunalQuant TradingView-style right control rail.

The UI only constructs existing V2Config/V2ExecutionPolicy values. It does not
change the underlying strategy, execution, lifecycle, accounting, or resolver.
"""
from __future__ import annotations

from dataclasses import asdict
from typing import Any

import streamlit as st

from execution.opening_breakout_v2_execution import V2ExecutionPolicy
from research.opening_breakout_1m_v2 import V2Config


STRATEGY_A = "Strategy A — Opening Breakout V2"
STRATEGY_B = "Strategy B — Not connected yet"


def _state(key: str, default: Any) -> Any:
    return st.session_state.get(key, default)


def render_strategy_parameters() -> None:
    """Render all parameters that belong to the selected strategy."""
    strategy = st.selectbox(
        "Strategy",
        [STRATEGY_A, STRATEGY_B],
        key="selected_strategy",
        help="Select the strategy whose parameters you want to configure.",
    )
    st.caption("All settings below apply only to the selected strategy.")

    if strategy == STRATEGY_B:
        st.warning(
            "Strategy B is visible in the selector but is not connected to the "
            "current historical runner. It cannot be backtested yet."
        )
        return

    with st.expander("1. Entry / signal", expanded=True):
        st.selectbox(
            "Market bias",
            ["NEUTRAL", "UP", "DOWN"],
            index=0,
            key="lab_bias",
        )
        st.selectbox(
            "Trade instrument",
            ["CALL", "PUT"],
            index=0,
            key="lab_instrument",
        )
        st.selectbox(
            "Breakout trigger",
            ["CANDLE_HIGH", "CANDLE_LOW"],
            index=0,
            key="lab_trigger",
            help="Currently connected real-data triggers.",
        )
        st.checkbox("Require OPEN = LOW", value=False, key="lab_open_low")
        st.checkbox("Require OPEN = HIGH", value=False, key="lab_open_high")
        st.number_input(
            "OPEN equality tolerance (points)",
            min_value=0.0,
            value=0.05,
            step=0.05,
            key="lab_open_tolerance",
        )

    with st.expander("2. Option selection", expanded=False):
        st.selectbox(
            "Strike selector",
            ["LOT_VALUE", "PRICE_RANGE", "ATM_DISTANCE"],
            index=0,
            key="lab_strike_mode",
        )
        st.number_input(
            "Target option value (₹ = LTP × lot)",
            min_value=100.0,
            value=10000.0,
            step=500.0,
            key="lab_lot_value",
        )
        st.number_input(
            "Option LTP minimum",
            min_value=0.01,
            value=80.0,
            step=5.0,
            key="lab_price_min",
        )
        st.number_input(
            "Option LTP maximum",
            min_value=0.01,
            value=100.0,
            step=5.0,
            key="lab_price_max",
        )
        st.number_input(
            "ATM distance (points)",
            min_value=0.0,
            value=0.0,
            step=50.0,
            key="lab_atm_distance",
        )

    with st.expander("3. Stop loss / target", expanded=True):
        st.selectbox(
            "Stop-loss mode",
            ["CUSTOM_POINTS", "CANDLE_1_LOW", "CANDLE_1_HIGH", "VALUE", "OFF"],
            index=0,
            key="lab_sl_mode",
        )
        st.number_input(
            "Stop-loss points",
            min_value=0.01,
            value=20.0,
            step=1.0,
            key="lab_custom_sl",
        )
        st.number_input(
            "Stop-loss value cap (₹)",
            min_value=100.0,
            value=10000.0,
            step=500.0,
            key="lab_sl_cap",
        )
        st.selectbox(
            "Target mode",
            ["RR_RATIO", "CUSTOM_POINTS", "VALUE", "OFF"],
            index=0,
            key="lab_tp_mode",
        )
        st.number_input(
            "Reward / Risk",
            min_value=0.1,
            value=2.0,
            step=0.25,
            key="lab_rr",
        )
        st.number_input(
            "Target points",
            min_value=0.01,
            value=20.0,
            step=1.0,
            key="lab_custom_tp",
        )
        st.number_input(
            "Target value (₹)",
            min_value=100.0,
            value=10000.0,
            step=500.0,
            key="lab_tp_value",
        )

    with st.expander("4. Position sizing", expanded=False):
        st.selectbox(
            "Risk method",
            ["FIXED_AMOUNT", "PERCENT_OF_CAPITAL"],
            index=0,
            key="lab_risk_method",
        )
        st.number_input(
            "Risk / trade (₹)",
            min_value=100.0,
            value=2000.0,
            step=100.0,
            key="lab_risk_value",
        )
        st.number_input(
            "Risk / trade (%)",
            min_value=0.01,
            max_value=100.0,
            value=1.0,
            step=0.25,
            key="lab_risk_pct",
        )
        st.number_input(
            "Capital allocation (%)",
            min_value=1.0,
            max_value=100.0,
            value=100.0,
            step=5.0,
            key="lab_allocation",
        )

    with st.expander("5. Execution assumptions", expanded=False):
        st.number_input(
            "Entry buffer (points)",
            min_value=0.0,
            value=1.0,
            step=0.5,
            key="lab_entry_buffer",
        )
        st.number_input(
            "Exit buffer (points)",
            min_value=0.0,
            value=2.0,
            step=0.5,
            key="lab_exit_buffer",
        )
        st.number_input(
            "Max slippage (points)",
            min_value=0.0,
            value=2.0,
            step=0.5,
            key="lab_max_slippage",
        )
        st.number_input(
            "Historical fill timeout (seconds)",
            min_value=1,
            value=60,
            step=5,
            key="lab_fill_timeout",
        )

    st.info(
        "Entry window 09:15–15:10 and force exit 15:15 remain locked to the "
        "current runner. Advanced VWAP/KTMI/DMI controls are not exposed until "
        "the dashboard indicator provider is connected."
    )
    st.warning(
        "ATR structural trailing remains an isolated research experiment and is "
        "not silently mixed into this strategy configuration."
    )


def get_strategy_state(default_risk: float = 2000.0) -> dict[str, Any]:
    """Build the active strategy state from Streamlit session values.

    This is also used when the right rail is collapsed, so collapsing the panel
    does not reset the configured strategy.
    """
    strategy = _state("selected_strategy", STRATEGY_A)
    if strategy != STRATEGY_A:
        return {
            "strategy": strategy,
            "available": False,
            "config": None,
            "execution_policy": None,
            "summary": {},
        }

    risk_value = float(_state("lab_risk_value", default_risk))
    config = V2Config(
        capital_allocation_percent=float(_state("lab_allocation", 100.0)),
        selected_timeframes=("1M",),
        market_bias=_state("lab_bias", "NEUTRAL"),
        trade_instrument=_state("lab_instrument", "CALL"),
        filter_open_high=bool(_state("lab_open_high", False)),
        filter_open_low=bool(_state("lab_open_low", False)),
        open_equal_tolerance_points=float(_state("lab_open_tolerance", 0.05)),
        selected_triggers=(_state("lab_trigger", "CANDLE_HIGH"),),
        strike_selector_mode=_state("lab_strike_mode", "LOT_VALUE"),
        lot_value_target=float(_state("lab_lot_value", 10000.0)),
        option_price_min=float(_state("lab_price_min", 80.0)),
        option_price_max=float(_state("lab_price_max", 100.0)),
        atm_distance_points=float(_state("lab_atm_distance", 0.0)),
        sl_mode=_state("lab_sl_mode", "CUSTOM_POINTS"),
        custom_sl_points=float(_state("lab_custom_sl", 20.0)),
        sl_value_cap=float(_state("lab_sl_cap", 10000.0)),
        tp_mode=_state("lab_tp_mode", "RR_RATIO"),
        custom_tp_points=float(_state("lab_custom_tp", 20.0)),
        tp_value_target=float(_state("lab_tp_value", 10000.0)),
        rr_multiplier=float(_state("lab_rr", 2.0)),
        trailing_enabled=False,
        risk_method=_state("lab_risk_method", "FIXED_AMOUNT"),
        risk_per_trade_value=risk_value,
        risk_per_trade_percent=float(_state("lab_risk_pct", 1.0)),
    )
    policy = V2ExecutionPolicy(
        entry_buffer_points=float(_state("lab_entry_buffer", 1.0)),
        exit_buffer_points=float(_state("lab_exit_buffer", 2.0)),
        max_slippage_points=float(_state("lab_max_slippage", 2.0)),
        fill_timeout_seconds=int(_state("lab_fill_timeout", 60)),
    )
    return {
        "strategy": strategy,
        "available": True,
        "config": config,
        "execution_policy": policy,
        "summary": asdict(config),
    }
