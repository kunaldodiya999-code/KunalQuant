"""Opening Breakout V2 -> real historical option integration.

Research-only orchestration layer.

It connects the new V2 signal events to:
- existing Option Contract Resolver V2 (unchanged)
- existing stored FYERS 1-minute option candles
- V2 historical fill engine
- V2 risk sizing and SL/TP helpers

The bridge does not change resolver, lifecycle, or locked trade-management
logic.

Timing:
- signal timestamp is treated as the information-available boundary
- option quote used for slippage is the latest completed option candle at or
  before the signal timestamp
- entry fill search begins strictly after the signal timestamp
- the entry candle is not processed for exits
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Sequence, Callable
from zoneinfo import ZoneInfo

from backtest.opening_breakout_v2_fill_engine import (
    HistoricalBar,
    HistoricalTrade,
    simulate_limit_fill,
    simulate_exit,
)
from backtest.opening_breakout_v2_signal_engine import OpeningBreakoutEvent
from execution.opening_breakout_v2_execution import V2ExecutionPolicy
from research.opening_breakout_1m_v2 import (
    Candle,
    V2Config,
    calculate_position_size,
    stop_loss_price,
    target_price,
)
from strategies.option_contract_resolver import OptionContractResolver, ResolvedOptionContract

TIMEZONE = ZoneInfo("Asia/Kolkata")


@dataclass(frozen=True)
class ResolvedOpeningBreakoutTrade:
    event: OpeningBreakoutEvent
    contract: ResolvedOptionContract
    signal_underlying_price: float
    option_signal_price: float
    quantity: int
    lots: int
    entry: object
    exit: object
    stop_price: float | None
    target_price: float | None
    final_stop_price: float | None
    gross_pnl: float
    status: str


OptionCandleLoader = Callable[[int, int, int], Sequence[object]]


def _entry_date(timestamp: int) -> date:
    return datetime.fromtimestamp(timestamp, tz=TIMEZONE).date()


def _to_historical_bar(candle: object) -> HistoricalBar:
    return HistoricalBar(
        timestamp=int(candle.timestamp),
        open=float(candle.open),
        high=float(candle.high),
        low=float(candle.low),
        close=float(candle.close),
    )


def _find_underlying_price(candles: Sequence[Candle], timestamp: int) -> float:
    candidates = [c for c in candles if c.timestamp <= timestamp]
    if not candidates:
        raise LookupError("no underlying candle available at signal timestamp")
    return float(max(candidates, key=lambda c: c.timestamp).close)


def _find_option_signal_price(bars: Sequence[HistoricalBar], timestamp: int) -> float:
    candidates = [bar for bar in bars if bar.timestamp <= timestamp]
    if not candidates:
        raise LookupError("no option quote available at signal timestamp")
    return float(max(candidates, key=lambda bar: bar.timestamp).close)


def _setup_option_candle(bars: Sequence[HistoricalBar]) -> HistoricalBar:
    if not bars:
        raise LookupError("option candle history is empty")
    return min(bars, key=lambda bar: bar.timestamp)


def run_opening_breakout_trade(
    *,
    event: OpeningBreakoutEvent,
    underlying_candles: Sequence[Candle],
    resolver: OptionContractResolver,
    option_loader: OptionCandleLoader,
    config: V2Config,
    execution_policy: V2ExecutionPolicy,
    capital: float,
    force_exit_timestamp: int | None = None,
) -> ResolvedOpeningBreakoutTrade:
    """Resolve and simulate one V2 signal against real stored option data."""
    if event.instrument not in {"CALL", "PUT"}:
        raise ValueError("this bridge currently targets CALL/PUT option events")

    underlying_price = _find_underlying_price(
        underlying_candles,
        event.trigger_timestamp,
    )

    contract = resolver.resolve(
        underlying_price=underlying_price,
        entry_date=_entry_date(event.trigger_timestamp),
        direction=event.direction,
    )

    raw_candles = list(
        option_loader(
            contract.instrument_id,
            event.setup_timestamp,
            force_exit_timestamp or event.trigger_timestamp + 86400,
        )
    )
    option_bars = sorted(
        (_to_historical_bar(candle) for candle in raw_candles),
        key=lambda bar: bar.timestamp,
    )
    if not option_bars:
        raise LookupError(f"no option candles for {contract.symbol}")

    signal_price = _find_option_signal_price(option_bars, event.trigger_timestamp)

    distance = (
        signal_price - event.breakout_price
        if event.direction == "LONG"
        else event.breakout_price - signal_price
    )
    if distance > execution_policy.max_slippage_points:
        from backtest.opening_breakout_v2_fill_engine import FillResult
        return ResolvedOpeningBreakoutTrade(
            event, contract, underlying_price, signal_price, 0, 0,
            FillResult(False, None, None, "SLIPPAGE_REJECTED"),
            FillResult(False, None, None, "NO_EXIT"),
            None, None, None, 0.0, "REJECTED",
        )

    # First prove the entry fill with one unit. Quantity does not alter the
    # historical price path, so sizing can safely occur after the fill price
    # is known and before exit simulation.
    entry_intent_price = signal_price + execution_policy.entry_buffer_points
    entry = simulate_limit_fill(
        option_bars,
        start_after_timestamp=event.trigger_timestamp,
        side="BUY",
        limit_price=entry_intent_price,
        timeout_seconds=execution_policy.fill_timeout_seconds,
    )
    if not entry.filled:
        return ResolvedOpeningBreakoutTrade(
            event, contract, underlying_price, signal_price, 0, 0,
            entry, type(entry)(False, None, None, "NO_EXIT"),
            None, None, None, 0.0, "FILL_TIMEOUT",
        )

    setup = _setup_option_candle(option_bars)
    stop = stop_loss_price(
        entry.price,
        Candle(setup.timestamp, setup.open, setup.high, setup.low, setup.close),
        config.sl_mode,
        event.direction,
        custom_points=config.custom_sl_points,
    )
    if stop is None:
        raise ValueError("historical integration requires an actual stop for sizing")

    sizing = calculate_position_size(
        capital=capital,
        entry_price=entry.price,
        stop_loss_price_value=stop,
        lot_size=contract_lot_size(contract),
        config=config,
    )
    if sizing.quantity <= 0:
        return ResolvedOpeningBreakoutTrade(
            event, contract, underlying_price, signal_price, 0, 0,
            entry, type(entry)(False, None, None, "NO_EXIT"),
            stop, None, stop, 0.0, "REJECTED_NO_POSITION_SIZE",
        )

    target = target_price(
        entry.price,
        stop,
        config.tp_mode,
        event.direction,
        custom_points=config.custom_tp_points,
        value_target=config.tp_value_target,
        rr_multiplier=config.rr_multiplier,
        quantity=sizing.quantity,
    )

    exit_result, final_stop = simulate_exit(
        option_bars,
        entry_timestamp=entry.timestamp,
        direction=event.direction,
        quantity=sizing.quantity,
        stop_price=stop,
        target_price=target,
        policy=execution_policy,
        force_exit_timestamp=force_exit_timestamp,
        trailing_enabled=config.trailing_enabled,
        trailing_mode="RR_STEPS" if config.trail_rr_steps else "POINTS",
        trail_trigger_points=config.trail_trigger_points,
        trail_distance_points=config.trail_distance_points,
        trail_to_cost=config.trail_to_cost,
        trail_rr_steps=config.trail_rr_steps,
        entry_price=entry.price,
    )

    pnl = 0.0
    if exit_result.filled:
        multiplier = 1.0 if event.direction == "LONG" else -1.0
        pnl = (exit_result.price - entry.price) * sizing.quantity * multiplier

    return ResolvedOpeningBreakoutTrade(
        event=event,
        contract=contract,
        signal_underlying_price=underlying_price,
        option_signal_price=signal_price,
        quantity=sizing.quantity,
        lots=sizing.lots,
        entry=entry,
        exit=exit_result,
        stop_price=stop,
        target_price=target,
        final_stop_price=final_stop,
        gross_pnl=pnl,
        status="CLOSED" if exit_result.filled else "OPEN",
    )


def contract_lot_size(contract: ResolvedOptionContract) -> int:
    """Return the known lot size without changing Resolver V2 metadata."""
    # Resolver V2 deliberately exposes instrument identity, not lot size.
    # The canonical NIFTY lot size is supplied by the caller through the
    # integration's contract metadata adapter in the next phase.
    raise NotImplementedError(
        "Provide lot size from canonical instrument metadata before real execution"
    )


__all__ = ["ResolvedOpeningBreakoutTrade", "run_opening_breakout_trade"]
