"""Isolated YT structural trailing simulator for Opening Breakout V2.

This module deliberately does not modify production fill-engine code.
It replays an already-resolved V2 option trade using the same initial stop,
target, entry and force-exit rules, while replacing only the stop-management
layer with the experimental ATR structural trail.

Research rule:
- Entry is unchanged.
- Initial stop is unchanged.
- Target is unchanged.
- Broker cost model is unchanged.
- Only the post-entry stop-management rule changes.
- Decisions use closed option bars only.
- Stop wins over target when both are touched in the same bar.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

from backtest.opening_breakout_v2_fill_engine import FillResult, HistoricalBar
from execution.opening_breakout_v2_execution import V2ExecutionPolicy
from research.opening_breakout_1m_v2 import Direction


@dataclass(frozen=True)
class StructuralTrailConfig:
    atr_period: int = 5
    swing_atr_mult: float = 2.5
    stop_atr_buffer: float = 0.25

    def __post_init__(self) -> None:
        if self.atr_period < 2:
            raise ValueError("atr_period must be >= 2")
        if self.swing_atr_mult <= 0:
            raise ValueError("swing_atr_mult must be > 0")
        if self.stop_atr_buffer < 0:
            raise ValueError("stop_atr_buffer must be >= 0")


@dataclass(frozen=True)
class StructuralTrailResult:
    exit: FillResult
    final_stop: float | None
    updates: tuple[float, ...]


class _TrailState:
    def __init__(self, config: StructuralTrailConfig) -> None:
        self.config = config
        self.trs: list[float] = []
        self.prev_close: Optional[float] = None
        self.extreme: Optional[float] = None
        self.last_stop: Optional[float] = None

    def atr(self) -> Optional[float]:
        if len(self.trs) < self.config.atr_period:
            return None
        return sum(self.trs[-self.config.atr_period:]) / self.config.atr_period

    def update(self, bar: HistoricalBar, direction: Direction) -> Optional[float]:
        tr = (
            bar.high - bar.low
            if self.prev_close is None
            else max(
                bar.high - bar.low,
                abs(bar.high - self.prev_close),
                abs(bar.low - self.prev_close),
            )
        )
        self.trs.append(float(tr))
        atr = self.atr()
        self.prev_close = bar.close
        if atr is None:
            return None

        if direction == "LONG":
            if self.extreme is None or bar.low < self.extreme:
                self.extreme = bar.low
            if bar.high - self.extreme >= self.config.swing_atr_mult * atr:
                candidate = self.extreme - self.config.stop_atr_buffer * atr
                if self.last_stop is None or candidate > self.last_stop:
                    self.last_stop = candidate
                    self.extreme = bar.high
                    return candidate
                self.extreme = bar.high
                return None

        else:
            if self.extreme is None or bar.high > self.extreme:
                self.extreme = bar.high
            if self.extreme - bar.low >= self.config.swing_atr_mult * atr:
                candidate = self.extreme + self.config.stop_atr_buffer * atr
                if self.last_stop is None or candidate < self.last_stop:
                    self.last_stop = candidate
                    self.extreme = bar.low
                    return candidate
                self.extreme = bar.low

        return None


def simulate_structural_exit(
    bars: Sequence[HistoricalBar],
    *,
    entry_timestamp: int,
    direction: Direction,
    stop_price: float,
    target_price: float | None,
    policy: V2ExecutionPolicy,
    force_exit_timestamp: int | None,
    config: StructuralTrailConfig,
    entry_price: float,
) -> StructuralTrailResult:
    if stop_price <= 0:
        raise ValueError("stop_price must be > 0")
    state = _TrailState(config)
    current_stop = stop_price
    updates: list[float] = []

    for bar in bars:
        if bar.timestamp <= entry_timestamp:
            continue

        if force_exit_timestamp is not None and bar.timestamp >= force_exit_timestamp:
            return StructuralTrailResult(
                FillResult(True, bar.timestamp, bar.open, "FORCE_EXIT"),
                current_stop,
                tuple(updates),
            )

        stop_hit = (
            bar.low <= current_stop
            if direction == "LONG"
            else bar.high >= current_stop
        )
        if stop_hit:
            trigger = current_stop
            limit = (
                trigger - policy.exit_buffer_points
                if direction == "LONG"
                else trigger + policy.exit_buffer_points
            )
            price = min(trigger, limit) if direction == "LONG" else max(trigger, limit)
            return StructuralTrailResult(
                FillResult(True, bar.timestamp, price, "STOP_LOSS"),
                current_stop,
                tuple(updates),
            )

        target_hit = (
            target_price is not None
            and (
                bar.high >= target_price
                if direction == "LONG"
                else bar.low <= target_price
            )
        )
        if target_hit:
            side = "SELL" if direction == "LONG" else "BUY"
            limit = (
                target_price - policy.exit_buffer_points
                if side == "SELL"
                else target_price + policy.exit_buffer_points
            )
            if side == "SELL":
                price = min(bar.open, limit) if bar.low <= limit else target_price
            else:
                price = max(bar.open, limit) if bar.high >= limit else target_price
            return StructuralTrailResult(
                FillResult(True, bar.timestamp, price, "TARGET"),
                current_stop,
                tuple(updates),
            )

        # Update only after evaluating this bar's existing stop/target.
        candidate = state.update(bar, direction)
        if candidate is not None:
            # Never loosen the original stop and never move against the trade.
            if direction == "LONG":
                if candidate > current_stop:
                    current_stop = candidate
                    updates.append(candidate)
            else:
                if candidate < current_stop and candidate > 0:
                    current_stop = candidate
                    updates.append(candidate)

    return StructuralTrailResult(
        FillResult(False, None, None, "NO_EXIT"),
        current_stop,
        tuple(updates),
    )
