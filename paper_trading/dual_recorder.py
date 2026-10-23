"""Fail-closed dual journal for paper trading.

CSV remains the recovery engine's canonical append-only journal. SQLite is a
secondary structured journal for dashboards and audits. Both writes are
synchronous; errors propagate so the caller cannot treat a partially persisted
operation as successful. A failed second write may leave a journal mismatch,
which intentionally causes the existing recovery validator to fail closed.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from paper_trading.recorder import PaperTradeRecorder
from paper_trading.sqlite_recorder import SQLitePaperTradeRecorder


class DualPaperTradeRecorder:
    """Write paper events to the existing CSV journal and SQLite journal.

    CSV is written first to preserve the current engine's recovery contract.
    This class deliberately does not swallow errors or pretend that two
    independent stores can be updated atomically.
    """

    def __init__(
        self,
        csv_recorder: PaperTradeRecorder,
        sqlite_recorder: SQLitePaperTradeRecorder,
    ) -> None:
        self.csv_recorder = csv_recorder
        self.sqlite_recorder = sqlite_recorder
        # DurablePaperTradingEngine uses these paths to locate its snapshot
        # and validate the existing CSV journal on restart.
        self.output_dir: Path = csv_recorder.output_dir
        self.signals_path: Path = csv_recorder.signals_path
        self.trades_path: Path = csv_recorder.trades_path

    def record_signal(self, signal: Any, *, symbol: str) -> None:
        self.csv_recorder.record_signal(signal, symbol=symbol)
        self.sqlite_recorder.record_signal(signal, symbol=symbol)

    def record_trade_open(self, trade: Any) -> None:
        self.csv_recorder.record_trade_open(trade)
        self.sqlite_recorder.record_trade_open(trade)

    def record_trade_exit(self, trade: Any, exit_event: Any) -> None:
        self.csv_recorder.record_trade_exit(trade, exit_event)
        self.sqlite_recorder.record_trade_exit(trade, exit_event)


__all__ = ["DualPaperTradeRecorder"]
