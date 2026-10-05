"""Small, auditable parameter-sweep helpers for Strategy Lab."""
from __future__ import annotations

from dataclasses import replace
from typing import Any, Callable, Iterable

import pandas as pd

from execution.opening_breakout_v2_execution import V2ExecutionPolicy
from research.opening_breakout_1m_v2 import V2Config


OPTIMIZABLE_PARAMETERS: dict[str, tuple[str, str]] = {
    "custom_sl_points": ("Strategy", "Stop-loss points"),
    "rr_multiplier": ("Strategy", "Reward / Risk"),
    "custom_tp_points": ("Strategy", "Target points"),
    "lot_value_target": ("Option", "Target option value"),
    "risk_per_trade_value": ("Risk", "Fixed risk / trade"),
    "risk_per_trade_percent": ("Risk", "Risk / trade %"),
    "capital_allocation_percent": ("Risk", "Capital allocation %"),
    "entry_buffer_points": ("Execution", "Entry buffer"),
    "exit_buffer_points": ("Execution", "Exit buffer"),
    "max_slippage_points": ("Execution", "Max slippage"),
    "fill_timeout_seconds": ("Execution", "Fill timeout"),
}


def sweep_values(start: float, end: float, step: float) -> list[float]:
    if step <= 0:
        raise ValueError("step must be > 0")
    if end < start:
        raise ValueError("end must be >= start")
    values: list[float] = []
    current = float(start)
    while current <= float(end) + step * 1e-9:
        values.append(round(current, 10))
        current += step
        if len(values) > 101:
            raise ValueError("sweep is limited to 101 values")
    return values


def apply_parameter(
    config: V2Config,
    policy: V2ExecutionPolicy,
    parameter: str,
    value: float,
) -> tuple[V2Config, V2ExecutionPolicy]:
    if parameter in {
        "custom_sl_points",
        "rr_multiplier",
        "custom_tp_points",
        "lot_value_target",
        "risk_per_trade_value",
        "risk_per_trade_percent",
        "capital_allocation_percent",
    }:
        return replace(config, **{parameter: value}), policy
    if parameter == "fill_timeout_seconds":
        return config, replace(policy, fill_timeout_seconds=int(value))
    return config, replace(policy, **{parameter: value})


def rank_sweep(
    rows: Iterable[dict[str, Any]],
    objective: str,
) -> pd.DataFrame:
    df = pd.DataFrame(list(rows))
    if df.empty:
        return df
    ascending = objective == "Max DD"
    return df.sort_values(objective, ascending=ascending, kind="stable").reset_index(drop=True)


__all__ = [
    "OPTIMIZABLE_PARAMETERS",
    "apply_parameter",
    "rank_sweep",
    "sweep_values",
]
