from __future__ import annotations

import csv
from pathlib import Path

import pytest

from backtest.option_trade_lifecycle import OptionTradeDirection
from database.schema import initialize_database
from paper_trading.durable_engine import DurablePaperTradingEngine, PaperStateRecoveryError
from paper_trading.dual_recorder import DualPaperTradeRecorder
from paper_trading.recorder import PaperTradeRecorder
from paper_trading.sqlite_recorder import SQLitePaperTradeRecorder


def _engine(tmp_path: Path, *, sqlite_recorder=None) -> DurablePaperTradingEngine:
    csv_recorder = PaperTradeRecorder(tmp_path / "csv")
    sqlite_recorder = sqlite_recorder or SQLitePaperTradeRecorder(
        tmp_path / "quant.db", session_id="integration-session",
        starting_capital=100_000,
    )
    return DurablePaperTradingEngine(
        recorder=DualPaperTradeRecorder(csv_recorder, sqlite_recorder),
        starting_capital=100_000,
        allocation_pct=20,
    )


def _sqlite(tmp_path: Path) -> SQLitePaperTradeRecorder:
    database_path = tmp_path / "quant.db"
    initialize_database(database_path)
    return SQLitePaperTradeRecorder(
        database_path, session_id="integration-session",
        starting_capital=100_000,
    )


def test_dual_recorder_persists_entry_exit_and_preserves_restart_recovery(tmp_path: Path) -> None:
    sqlite_recorder = _sqlite(tmp_path)
    engine = _engine(tmp_path, sqlite_recorder=sqlite_recorder)
    trade = engine.open_position(
        strategy_id="KTMI_LONG_SHORT_SPEED",
        direction=OptionTradeDirection.LONG,
        symbol="NSE:NIFTY26OCT22700CE",
        entry_price=100,
        timestamp=1792739000,
    )
    assert trade is not None

    engine.force_exit_position(
        strategy_id="KTMI_LONG_SHORT_SPEED",
        timestamp=1792739060,
        fresh_option_price=110,
    )

    with (tmp_path / "csv" / "trade_events.csv").open(
        newline="", encoding="utf-8"
    ) as handle:
        csv_rows = list(csv.DictReader(handle))
    assert [row["event_type"] for row in csv_rows] == ["ENTRY", "EXIT"]

    sqlite_open = sqlite_recorder.get_open_trades()
    assert sqlite_open == []
    sqlite_events = sqlite_recorder.get_trade_events(sqlite_recorder._trade_id(trade))
    assert [event["event_type"] for event in sqlite_events] == ["ENTRY", "EXIT"]

    restarted = _engine(tmp_path, sqlite_recorder=_sqlite(tmp_path))
    restarted.restore_state()
    restored = restarted.trades("KTMI_LONG_SHORT_SPEED")
    assert len(restored) == 1
    assert restored[0].closed


def test_sqlite_entry_failure_propagates_and_restart_fails_closed(tmp_path: Path) -> None:
    sqlite_recorder = _sqlite(tmp_path)

    def fail_open(_trade):
        raise OSError("simulated SQLite entry failure")

    sqlite_recorder.record_trade_open = fail_open
    engine = _engine(tmp_path, sqlite_recorder=sqlite_recorder)

    with pytest.raises(OSError, match="simulated SQLite entry failure"):
        engine.open_position(
            strategy_id="KTMI_LONG_SHORT_SPEED",
            direction=OptionTradeDirection.LONG,
            symbol="NSE:NIFTY26OCT22700CE",
            entry_price=100,
            timestamp=1792739000,
        )

    assert engine.all_trades() == ()
    with (tmp_path / "csv" / "trade_events.csv").open(
        newline="", encoding="utf-8"
    ) as handle:
        assert [row["event_type"] for row in csv.DictReader(handle)] == ["ENTRY"]

    restarted = _engine(tmp_path, sqlite_recorder=_sqlite(tmp_path))
    with pytest.raises(PaperStateRecoveryError, match="snapshot is missing"):
        restarted.restore_state()


def test_sqlite_exit_failure_propagates_and_journal_conflict_fails_closed(tmp_path: Path) -> None:
    sqlite_recorder = _sqlite(tmp_path)
    engine = _engine(tmp_path, sqlite_recorder=sqlite_recorder)
    engine.open_position(
        strategy_id="KTMI_LONG_SHORT_SPEED",
        direction=OptionTradeDirection.LONG,
        symbol="NSE:NIFTY26OCT22700CE",
        entry_price=100,
        timestamp=1792739000,
    )

    def fail_exit(_trade, _event):
        raise OSError("simulated SQLite exit failure")

    sqlite_recorder.record_trade_exit = fail_exit
    with pytest.raises(OSError, match="simulated SQLite exit failure"):
        engine.force_exit_position(
            strategy_id="KTMI_LONG_SHORT_SPEED",
            timestamp=1792739060,
            fresh_option_price=110,
        )

    # CSV contains the exit but the durable snapshot was not advanced. The
    # existing recovery guard must refuse to guess which journal is correct.
    restarted = _engine(tmp_path, sqlite_recorder=_sqlite(tmp_path))
    with pytest.raises(PaperStateRecoveryError, match="Exit count mismatch"):
        restarted.restore_state()
