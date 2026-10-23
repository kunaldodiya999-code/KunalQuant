"""SQLite-backed paper-trade journal.

Call database.schema.initialize_database() before constructing this recorder.
It implements the same record_signal/record_trade_open/record_trade_exit
interface as PaperTradeRecorder, so the engine can use it without broker APIs.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


class SQLitePaperTradeRecorder:
    """Persist paper sessions, signals, positions, and lifecycle events in SQLite."""

    def __init__(
        self,
        database_path: str | Path = "data/database/kunal_quant.db",
        *,
        session_id: str | None = None,
        starting_capital: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.session_id = session_id or uuid4().hex
        self._ensure_session(starting_capital, metadata or {})

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _ensure_session(self, starting_capital: float | None, metadata: dict[str, Any]) -> None:
        with self._connect() as connection:
            connection.execute(
                """INSERT OR IGNORE INTO paper_sessions
                   (session_id, mode, status, starting_capital, metadata_json)
                   VALUES (?, 'paper', 'RUNNING', ?, ?)""",
                (self.session_id, starting_capital, json.dumps(metadata, default=str)),
            )

    @staticmethod
    def _strategy(value: Any) -> str:
        return str(getattr(value, "value", value))

    @staticmethod
    def _trade_id(trade: Any) -> str:
        p = trade.position
        return f"{SQLitePaperTradeRecorder._strategy(trade.strategy_id)}:{int(trade.entry_timestamp)}:{p.symbol}"

    def record_signal(self, signal: Any, *, symbol: str) -> None:
        strategy = self._strategy(getattr(signal, "strategy_id", ""))
        key = f"{strategy}:{getattr(signal, 'direction', '')}:{int(signal.timestamp)}:{int(signal.index)}"
        with self._connect() as connection:
            connection.execute(
                """INSERT OR IGNORE INTO paper_signals
                   (session_id, signal_key, signal_timestamp, strategy_id, direction,
                    bar_index, symbol, reason)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (self.session_id, key, int(signal.timestamp), strategy,
                 str(getattr(signal, "direction", "")), int(signal.index), symbol,
                 str(getattr(signal, "reason", ""))),
            )

    def record_trade_open(self, trade: Any) -> None:
        p = trade.position
        strategy = self._strategy(trade.strategy_id)
        trade_id = self._trade_id(trade)
        with self._connect() as connection:
            connection.execute(
                """INSERT OR IGNORE INTO paper_trades
                   (trade_id, session_id, strategy_id, symbol, direction,
                    entry_timestamp, entry_price, quantity, lots, stop_loss, target,
                    remaining_quantity, remaining_lots, gross_pnl, status,
                    last_processed_timestamp)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (trade_id, self.session_id, strategy, str(p.symbol),
                 self._strategy(p.direction), int(trade.entry_timestamp),
                 float(p.entry_price), int(p.quantity), int(p.lots),
                 float(p.stop_loss), float(p.target), int(p.remaining_quantity),
                 int(p.remaining_lots), float(p.gross_pnl),
                 "CLOSED" if p.closed else "OPEN", trade.last_processed_timestamp),
            )
            connection.execute(
                """INSERT OR IGNORE INTO paper_trade_events
                   (trade_id, event_key, event_type, event_timestamp, price,
                    quantity, lots, pnl, reason, payload_json)
                   VALUES (?, ?, 'ENTRY', ?, ?, ?, ?, 0, 'ENTRY', ?)""",
                (trade_id, f"ENTRY:{int(trade.entry_timestamp)}",
                 int(trade.entry_timestamp), float(p.entry_price), int(p.quantity),
                 int(p.lots), json.dumps({"stop_loss": p.stop_loss, "target": p.target})),
            )

    def record_trade_exit(self, trade: Any, exit_event: Any) -> None:
        p = trade.position
        trade_id = self._trade_id(trade)
        timestamp = int(exit_event.timestamp)
        reason = str(getattr(exit_event, "reason", "EXIT"))
        qty = int(getattr(exit_event, "quantity", 0))
        lots = int(getattr(exit_event, "lots", 0))
        event_key = f"{timestamp}:{reason}:{qty}:{float(exit_event.price):.8f}"
        with self._connect() as connection:
            connection.execute(
                """INSERT OR IGNORE INTO paper_trade_events
                   (trade_id, event_key, event_type, event_timestamp, price,
                    quantity, lots, pnl, reason, payload_json)
                   VALUES (?, ?, 'EXIT', ?, ?, ?, ?, ?, ?, ?)""",
                (trade_id, event_key, timestamp, float(exit_event.price), qty, lots,
                 float(exit_event.pnl), reason, json.dumps({
                     "remaining_quantity": int(exit_event.remaining_quantity),
                     "remaining_lots": int(exit_event.remaining_lots),
                 })),
            )
            connection.execute(
                """UPDATE paper_trades SET remaining_quantity=?, remaining_lots=?,
                   gross_pnl=?, status=?, last_processed_timestamp=?, closed_at=?,
                   updated_at=CURRENT_TIMESTAMP WHERE trade_id=? AND session_id=?""",
                (int(p.remaining_quantity), int(p.remaining_lots), float(p.gross_pnl),
                 "CLOSED" if p.closed else "OPEN", trade.last_processed_timestamp,
                 timestamp if p.closed else None, trade_id, self.session_id),
            )

    def get_open_trades(self) -> list[dict[str, Any]]:
        """Read open trades for dashboards/recovery audits; does not mutate engine state."""
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT * FROM paper_trades
                   WHERE session_id=? AND status='OPEN'
                   ORDER BY entry_timestamp, trade_id""",
                (self.session_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_trade_events(self, trade_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT * FROM paper_trade_events WHERE trade_id=?
                   ORDER BY event_timestamp, id""",
                (trade_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def close_session(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """UPDATE paper_sessions SET status='STOPPED', ended_at=?
                   WHERE session_id=? AND status='RUNNING'""",
                (datetime.now(timezone.utc).isoformat(), self.session_id),
            )
