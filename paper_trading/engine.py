"""Deterministic paper-trading core; deliberately has no broker/order API.

This module coordinates independent strategy positions while delegating all
option position sizing and exit rules to the locked OptionTradeLifecycle V1.
It accepts already-resolved contracts and observed prices; market-data and
contract-resolution adapters are intentionally separate.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite
from enum import Enum
from typing import Optional

from backtest.option_trade_lifecycle import (
    OptionTradeDirection,
    OptionTradeExit,
    OptionTradeLifecycle,
    OptionTradeLifecycleConfig,
    OptionTradePosition,
)
from paper_trading.recorder import PaperTradeRecorder


class PaperStrategyId(str, Enum):
    STRATEGY_A = "KTMI_LONG_SHORT_SPEED"
    STRATEGY_B = "KTMI_MOMENTUM_ONLY"
    MODULE_CONFLUENCE = "KTMI_MODULE_CONFLUENCE"


@dataclass(frozen=True)
class PaperEngineConfig:
    """Independent ON/OFF switches; all three strategies default to enabled."""

    strategy_a_enabled: bool = True
    strategy_b_enabled: bool = True
    module_confluence_enabled: bool = True
    lifecycle_config: OptionTradeLifecycleConfig = field(
        default_factory=OptionTradeLifecycleConfig
    )

    def is_enabled(self, strategy_id: PaperStrategyId) -> bool:
        return {
            PaperStrategyId.STRATEGY_A: self.strategy_a_enabled,
            PaperStrategyId.STRATEGY_B: self.strategy_b_enabled,
            PaperStrategyId.MODULE_CONFLUENCE: self.module_confluence_enabled,
        }[strategy_id]


@dataclass
class PaperTradeRecord:
    """One paper trade and all lifecycle exit events belonging to it."""

    strategy_id: PaperStrategyId
    entry_timestamp: int
    position: OptionTradePosition
    exits: list[OptionTradeExit] = field(default_factory=list)
    last_processed_timestamp: Optional[int] = None

    @property
    def closed(self) -> bool:
        return self.position.closed

    @property
    def gross_pnl(self) -> float:
        return self.position.gross_pnl


class PaperTradingEngine:
    """Strategy-isolated paper position state using locked lifecycle rules.

    At most one position per strategy may be open at a time. Different
    strategies can hold independent positions simultaneously, including on
    the same symbol. Disabled strategies cannot open new positions.
    This class never creates a broker client or submits an order.
    """

    def __init__(
        self,
        config: Optional[PaperEngineConfig] = None,
        *,
        recorder: PaperTradeRecorder | None = None,
        lifecycle: object | None = None,
        starting_capital: float | None = None,
        allocation_pct: int | None = None,
    ) -> None:
        self.config = config or PaperEngineConfig()
        self.recorder = recorder
        if starting_capital is not None and (not isfinite(starting_capital) or starting_capital <= 0):
            raise ValueError("starting_capital must be finite and positive")
        if allocation_pct is not None and not 1 <= allocation_pct <= 100:
            raise ValueError("allocation_pct must be between 1 and 100")
        self.starting_capital = starting_capital
        self.allocation_pct = allocation_pct
        # Default remains the locked V1 lifecycle. Buyer-only paper behaviour
        # must be explicitly injected; historical V1 is never rewritten.
        self.lifecycle = (
            lifecycle if lifecycle is not None
            else OptionTradeLifecycle(self.config.lifecycle_config)
        )
        self.trade_logs: dict[PaperStrategyId, list[PaperTradeRecord]] = {
            strategy_id: [] for strategy_id in PaperStrategyId
        }
        self.active_positions: dict[PaperStrategyId, PaperTradeRecord] = {}

    @staticmethod
    def _strategy_id(value: PaperStrategyId | str | Enum) -> PaperStrategyId:
        raw = value.value if isinstance(value, Enum) else value
        try:
            return PaperStrategyId(str(raw))
        except ValueError as exc:
            raise ValueError(f"Unsupported paper strategy: {raw}") from exc

    @staticmethod
    def _direction(value: OptionTradeDirection | str | Enum) -> OptionTradeDirection:
        raw = value.value if isinstance(value, Enum) else value
        try:
            return OptionTradeDirection(str(raw).upper())
        except ValueError as exc:
            raise ValueError(f"Unsupported trade direction: {raw}") from exc

    def available_cash(self) -> float | None:
        """Cash basis: starting capital + realized P&L - open-position entry cost."""
        if self.starting_capital is None:
            return None
        realized = sum(
            event.pnl for trade in self.all_trades() for event in trade.exits
        )
        open_entry_cost = sum(
            trade.position.entry_price * trade.position.remaining_quantity
            for trade in self.all_trades() if not trade.closed
        )
        return self.starting_capital + realized - open_entry_cost

    def open_position(
        self,
        *,
        strategy_id: PaperStrategyId | str | Enum,
        direction: OptionTradeDirection | str | Enum,
        symbol: str,
        entry_price: float,
        timestamp: int,
    ) -> Optional[PaperTradeRecord]:
        """Open a simulated position from a validated option entry quote.

        Returns None when the strategy is disabled or already has an open
        position. Invalid price/allocation inputs are rejected by V1.
        """
        strategy = self._strategy_id(strategy_id)
        if not self.config.is_enabled(strategy):
            return None

        current = self.active_positions.get(strategy)
        if current is not None and not current.closed:
            return None

        position = self.lifecycle.create_position(
            strategy_id=strategy.value,
            direction=self._direction(direction),
            symbol=symbol,
            entry_price=entry_price,
        )
        if self.starting_capital is not None and self.allocation_pct is not None:
            cash = self.available_cash()
            assert cash is not None
            budget = max(0.0, cash) * self.allocation_pct / 100.0
            lot_size = int(getattr(getattr(self.lifecycle, "config", None), "lot_size", 0))
            if lot_size < 1:
                raise ValueError("Capital allocation requires a valid configured lot size.")
            allowed_lots = int(budget // (position.entry_price * lot_size))
            if allowed_lots < 1:
                raise ValueError("Available cash allocation cannot purchase one complete lot.")
            if allowed_lots < position.lots:
                position.lots = allowed_lots
                position.quantity = allowed_lots * lot_size
                position.remaining_lots = allowed_lots
                position.remaining_quantity = position.quantity
        record = PaperTradeRecord(
            strategy_id=strategy,
            entry_timestamp=int(timestamp),
            position=position,
            last_processed_timestamp=int(timestamp),
        )
        # Persist the entry before exposing it as an accepted paper position.
        # A disk error therefore fails visibly instead of silently losing the entry.
        if self.recorder is not None:
            self.recorder.record_trade_open(record)
        self.trade_logs[strategy].append(record)
        self.active_positions[strategy] = record
        return record

    def process_option_candle(
        self,
        *,
        strategy_id: PaperStrategyId | str | Enum,
        timestamp: int,
        option_high: float,
        option_low: float,
        option_close: float,
        underlying_close: float | None,
        kama_value: Optional[float],
    ) -> list[OptionTradeExit]:
        """Advance only the selected strategy's position through lifecycle V1."""
        strategy = self._strategy_id(strategy_id)
        record = self.active_positions.get(strategy)
        if record is None or record.closed:
            return []

        candle_timestamp = int(timestamp)
        if record.last_processed_timestamp is not None and candle_timestamp <= record.last_processed_timestamp:
            raise ValueError(
                "Option candle timestamps must be strictly increasing and later than entry."
            )

        exits = self.lifecycle.process_candle(
            position=record.position,
            timestamp=candle_timestamp,
            option_high=float(option_high),
            option_low=float(option_low),
            option_close=float(option_close),
            underlying_close=(
                float(underlying_close)
                if underlying_close is not None
                else None
            ),
            kama_value=kama_value,
        )
        record.exits.extend(exits)
        record.last_processed_timestamp = candle_timestamp
        if self.recorder is not None:
            for exit_event in exits:
                self.recorder.record_trade_exit(record, exit_event)
        return exits

    def update_manual_stop(
        self,
        *,
        strategy_id: PaperStrategyId | str | Enum,
        stop_loss: float,
        allow_loosen: bool = True,
    ) -> PaperTradeRecord:
        """Update an open paper position's premium stop, never a broker order.

        For bought option premium, a lower stop loosens risk and a higher stop
        tightens it. Loosening is allowed only when explicitly enabled.
        """
        strategy = self._strategy_id(strategy_id)
        record = self.open_trade(strategy)
        if record is None:
            raise ValueError("No open paper position for this strategy.")
        value = float(stop_loss)
        if not isfinite(value) or value <= 0:
            raise ValueError("Manual stop must be finite and positive.")
        if value >= record.position.entry_price:
            raise ValueError("Manual stop must remain below the option entry premium.")
        if not allow_loosen and value < record.position.stop_loss:
            raise ValueError("Loosening the manual stop is disabled.")
        record.position.stop_loss = value
        return record

    def force_exit_position(
        self,
        *,
        strategy_id: PaperStrategyId | str | Enum,
        timestamp: int,
        fresh_option_price: float,
    ) -> OptionTradeExit:
        """Close a paper position at an externally validated fresh option quote.

        Caller must validate symbol, exchange timestamp and quote freshness first.
        This method deliberately does not estimate a price when data is missing.
        """
        strategy = self._strategy_id(strategy_id)
        record = self.open_trade(strategy)
        if record is None:
            raise ValueError("No open paper position for this strategy.")
        price = float(fresh_option_price)
        if not isfinite(price) or price <= 0:
            raise ValueError("Forced-exit price must be finite and positive.")
        position = record.position
        quantity, lots = position.remaining_quantity, position.remaining_lots
        pnl = (price - position.entry_price) * quantity
        position.gross_pnl += pnl
        position.remaining_quantity = 0
        position.remaining_lots = 0
        position.closed = True
        event = OptionTradeExit(
            timestamp=int(timestamp), reason="FORCED_EXIT",
            price=price, quantity=quantity, lots=lots, pnl=pnl,
            remaining_quantity=0, remaining_lots=0,
        )
        record.exits.append(event)
        record.last_processed_timestamp = int(timestamp)
        if self.recorder is not None:
            self.recorder.record_trade_exit(record, event)
        return event

    def open_trade(self, strategy_id: PaperStrategyId | str | Enum) -> Optional[PaperTradeRecord]:
        """Return the selected strategy's active trade, if any."""
        strategy = self._strategy_id(strategy_id)
        record = self.active_positions.get(strategy)
        return record if record is not None and not record.closed else None

    def trades(self, strategy_id: PaperStrategyId | str | Enum) -> tuple[PaperTradeRecord, ...]:
        """Return an immutable snapshot of one strategy's paper trade log."""
        return tuple(self.trade_logs[self._strategy_id(strategy_id)])

    def all_trades(self) -> tuple[PaperTradeRecord, ...]:
        """Return all trade records grouped by strategy insertion order."""
        return tuple(
            trade
            for strategy in PaperStrategyId
            for trade in self.trade_logs[strategy]
        )
