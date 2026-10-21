"""Durable state adapter for paper-only trades.

The adapter stores a validated atomic snapshot beside the append-only journal.
It never submits broker orders. Corrupt snapshots fail closed rather than
starting with an empty engine and potentially duplicating a paper entry.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any

from backtest.option_trade_lifecycle import OptionTradeDirection, OptionTradeExit, OptionTradePosition
from paper_trading.engine import PaperEngineConfig, PaperStrategyId, PaperTradeRecord, PaperTradingEngine


class PaperStateRecoveryError(RuntimeError):
    """Persisted paper state is missing, malformed, or contradictory."""


class DurablePaperTradingEngine(PaperTradingEngine):
    """PaperTradingEngine with atomic state snapshots after each state mutation."""

    STATE_VERSION = 1

    def __init__(self, *args: Any, state_path: str | Path, **kwargs: Any) -> None:
        self.state_path = Path(state_path)
        super().__init__(*args, **kwargs)

    @staticmethod
    def _finite_number(value: Any, label: str) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError) as exc:
            raise PaperStateRecoveryError(f"Invalid {label} in paper state.") from exc
        if not math.isfinite(number):
            raise PaperStateRecoveryError(f"Non-finite {label} in paper state.")
        return number

    def _snapshot(self) -> dict[str, Any]:
        trades = []
        for trade in self.all_trades():
            p = trade.position
            trades.append({
                "strategy_id": trade.strategy_id.value,
                "entry_timestamp": trade.entry_timestamp,
                "last_processed_timestamp": trade.last_processed_timestamp,
                "position": {
                    "strategy_id": p.strategy_id,
                    "direction": p.direction.value,
                    "symbol": p.symbol,
                    "entry_price": p.entry_price,
                    "lots": p.lots,
                    "quantity": p.quantity,
                    "stop_loss": p.stop_loss,
                    "target": p.target,
                    "remaining_lots": p.remaining_lots,
                    "remaining_quantity": p.remaining_quantity,
                    "partial_exit_done": p.partial_exit_done,
                    "closed": p.closed,
                    "gross_pnl": p.gross_pnl,
                },
                "exits": [{
                    "timestamp": e.timestamp,
                    "reason": getattr(e.reason, "value", e.reason),
                    "price": e.price,
                    "quantity": e.quantity,
                    "lots": e.lots,
                    "pnl": e.pnl,
                    "remaining_quantity": e.remaining_quantity,
                    "remaining_lots": e.remaining_lots,
                } for e in trade.exits],
            })
        return {
            "version": self.STATE_VERSION,
            "starting_capital": self.starting_capital,
            "allocation_pct": self.allocation_pct,
            "trades": trades,
        }

    def persist_state(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.state_path.with_suffix(self.state_path.suffix + ".tmp")
        payload = json.dumps(self._snapshot(), sort_keys=True, allow_nan=False)
        with temp.open("w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        temp.replace(self.state_path)

    def restore_state(self) -> None:
        if not self.state_path.exists():
            # A journal without its corresponding state is ambiguous: never
            # silently start fresh and risk duplicating/reopening trades.
            if self.recorder is not None and self.recorder.trades_path.exists() and self.recorder.trades_path.stat().st_size:
                raise PaperStateRecoveryError(
                    "Trade journal exists but paper state snapshot is missing; reconcile manually before starting."
                )
            return
        try:
            raw = json.loads(self.state_path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict) or raw.get("version") != self.STATE_VERSION:
                raise PaperStateRecoveryError("Unsupported paper state snapshot version.")
            if raw.get("starting_capital") != self.starting_capital or raw.get("allocation_pct") != self.allocation_pct:
                raise PaperStateRecoveryError("Saved capital/allocation does not match current session settings.")
            rows = raw.get("trades")
            if not isinstance(rows, list):
                raise PaperStateRecoveryError("Paper state trades must be a list.")
            rebuilt: dict[PaperStrategyId, list[PaperTradeRecord]] = {sid: [] for sid in PaperStrategyId}
            active: dict[PaperStrategyId, PaperTradeRecord] = {}
            seen_ids: set[tuple[str, int, str]] = set()
            for row in rows:
                sid = PaperStrategyId(row["strategy_id"])
                entry_ts = int(row["entry_timestamp"])
                pd = row["position"]
                symbol = str(pd["symbol"])
                identity = (sid.value, entry_ts, symbol)
                if identity in seen_ids:
                    raise PaperStateRecoveryError("Duplicate trade identity in paper state.")
                seen_ids.add(identity)
                direction = OptionTradeDirection(str(pd["direction"]))
                entry_price = self._finite_number(pd["entry_price"], "entry price")
                stop_loss = self._finite_number(pd["stop_loss"], "stop loss")
                target_raw = pd.get("target")
                target = None if target_raw is None else self._finite_number(target_raw, "target")
                quantity, lots = int(pd["quantity"]), int(pd["lots"])
                remaining_quantity, remaining_lots = int(pd["remaining_quantity"]), int(pd["remaining_lots"])
                if entry_price <= 0 or stop_loss <= 0 or stop_loss >= entry_price:
                    raise PaperStateRecoveryError("Invalid entry/stop relationship in paper state.")
                if quantity <= 0 or lots <= 0 or not 0 <= remaining_quantity <= quantity or not 0 <= remaining_lots <= lots:
                    raise PaperStateRecoveryError("Invalid quantity/lot counts in paper state.")
                closed = bool(pd["closed"])
                if closed != (remaining_quantity == 0 and remaining_lots == 0):
                    raise PaperStateRecoveryError("Closed flag conflicts with remaining quantity.")
                position = OptionTradePosition(
                    strategy_id=str(pd["strategy_id"]), direction=direction, symbol=symbol,
                    entry_price=entry_price, lots=lots, quantity=quantity,
                    stop_loss=stop_loss, target=target, remaining_lots=remaining_lots,
                    remaining_quantity=remaining_quantity,
                    partial_exit_done=bool(pd["partial_exit_done"]), closed=closed,
                    gross_pnl=self._finite_number(pd["gross_pnl"], "gross P&L"),
                )
                exits = []
                for ed in row["exits"]:
                    exits.append(OptionTradeExit(
                        timestamp=int(ed["timestamp"]), reason=ed["reason"],
                        price=self._finite_number(ed["price"], "exit price"),
                        quantity=int(ed["quantity"]), lots=int(ed["lots"]),
                        pnl=self._finite_number(ed["pnl"], "exit P&L"),
                        remaining_quantity=int(ed["remaining_quantity"]),
                        remaining_lots=int(ed["remaining_lots"]),
                    ))
                last_ts = row.get("last_processed_timestamp")
                trade = PaperTradeRecord(
                    strategy_id=sid, entry_timestamp=entry_ts, position=position,
                    exits=exits, last_processed_timestamp=None if last_ts is None else int(last_ts),
                )
                if exits:
                    if sum(e.pnl for e in exits) and not math.isclose(sum(e.pnl for e in exits), position.gross_pnl, rel_tol=1e-8, abs_tol=1e-6):
                        raise PaperStateRecoveryError("Exit-event P&L conflicts with saved gross P&L.")
                    final_exit = exits[-1]
                    if final_exit.remaining_quantity != remaining_quantity or final_exit.remaining_lots != remaining_lots:
                        raise PaperStateRecoveryError("Last exit event conflicts with saved remaining position.")
                if not closed:
                    if sid in active and not active[sid].closed:
                        raise PaperStateRecoveryError("Multiple open trades for one strategy in saved state.")
                    active[sid] = trade
                rebuilt[sid].append(trade)
            self.trade_logs = rebuilt
            self.active_positions = active
            self._validate_journal()
        except PaperStateRecoveryError:
            raise
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError, OverflowError) as exc:
            raise PaperStateRecoveryError(f"Could not safely restore paper state: {exc}") from exc

    def _validate_journal(self) -> None:
        """Require journal identities and latest exit states to agree with snapshot."""
        if self.recorder is None or not self.recorder.trades_path.exists():
            return
        import csv
        with self.recorder.trades_path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        journal_entries: dict[str, dict[str, str]] = {}
        journal_exits: dict[str, list[dict[str, str]]] = {}
        for row in rows:
            event = row.get("event_type")
            trade_id = row.get("trade_id")
            if not trade_id:
                raise PaperStateRecoveryError("Trade journal contains a row without trade_id.")
            if event == "ENTRY":
                if trade_id in journal_entries:
                    raise PaperStateRecoveryError("Trade journal contains duplicate ENTRY events.")
                journal_entries[trade_id] = row
                journal_exits[trade_id] = []
            elif event == "EXIT":
                if trade_id not in journal_entries:
                    raise PaperStateRecoveryError("Trade journal has an EXIT without a preceding ENTRY.")
                journal_exits[trade_id].append(row)
            else:
                raise PaperStateRecoveryError(f"Unknown trade journal event type: {event!r}")
        snapshot_trades = {f"{t.strategy_id.value}:{t.entry_timestamp}:{t.position.symbol}": t for t in self.all_trades()}
        if set(journal_entries) != set(snapshot_trades):
            raise PaperStateRecoveryError("Trade journal and snapshot contain different trade identities.")
        for trade_id, trade in snapshot_trades.items():
            rows_for_trade = journal_exits[trade_id]
            if len(rows_for_trade) != len(trade.exits):
                raise PaperStateRecoveryError(f"Exit count mismatch between journal and snapshot for {trade_id}.")
            for journal, exit_event in zip(rows_for_trade, trade.exits):
                if int(journal["event_timestamp"]) != int(exit_event.timestamp) or not math.isclose(float(journal["event_pnl"]), float(exit_event.pnl), rel_tol=1e-8, abs_tol=1e-6):
                    raise PaperStateRecoveryError(f"Exit journal conflicts with snapshot for {trade_id}.")


    def open_position(self, **kwargs: Any):
        result = super().open_position(**kwargs)
        if result is not None:
            self.persist_state()
        return result

    def process_option_candle(self, **kwargs: Any):
        result = super().process_option_candle(**kwargs)
        # Persist even when no exit occurred: this is the duplicate-candle guard.
        if self.active_positions.get(self._strategy_id(kwargs["strategy_id"])) is not None:
            self.persist_state()
        return result

    def update_manual_stop(self, **kwargs: Any):
        result = super().update_manual_stop(**kwargs)
        self.persist_state()
        return result

    def force_exit_position(self, **kwargs: Any):
        result = super().force_exit_position(**kwargs)
        self.persist_state()
        return result


__all__ = ["DurablePaperTradingEngine", "PaperStateRecoveryError"]
