from __future__ import annotations

import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

from database.schema import initialize_database, get_schema_summary
from paper_trading.sqlite_recorder import SQLitePaperTradeRecorder


def _trade(*, timestamp: int = 1792739000) -> SimpleNamespace:
    position = SimpleNamespace(
        symbol="NSE:NIFTY26OCT22700CE", direction="LONG", entry_price=100.0,
        quantity=50, lots=1, stop_loss=80.0, target=140.0,
        remaining_quantity=50, remaining_lots=1, gross_pnl=0.0, closed=False,
    )
    return SimpleNamespace(
        strategy_id="KTMI_LONG_SHORT_SPEED", entry_timestamp=timestamp,
        position=position, last_processed_timestamp=timestamp,
    )


def test_schema_v5_creates_paper_tables_without_dropping_existing_tables(tmp_path: Path) -> None:
    path = tmp_path / "quant.db"
    initialize_database(path)
    summary = get_schema_summary(path)
    assert int(summary["schema_version"]) == 5
    assert {"instruments", "candles", "paper_sessions", "paper_signals",
            "paper_trades", "paper_trade_events"}.issubset(set(summary["tables"]))


def test_sqlite_recorder_persists_entry_and_is_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "quant.db"
    initialize_database(path)
    recorder = SQLitePaperTradeRecorder(path, session_id="test-session", starting_capital=100000)
    trade = _trade()

    recorder.record_trade_open(trade)
    recorder.record_trade_open(trade)

    opened = recorder.get_open_trades()
    assert len(opened) == 1
    assert opened[0]["symbol"] == trade.position.symbol
    assert opened[0]["stop_loss"] == 80.0
    assert opened[0]["target"] == 140.0
    events = recorder.get_trade_events(opened[0]["trade_id"])
    assert [event["event_type"] for event in events] == ["ENTRY"]


def test_sqlite_recorder_persists_partial_and_final_exits_idempotently(tmp_path: Path) -> None:
    path = tmp_path / "quant.db"
    initialize_database(path)
    recorder = SQLitePaperTradeRecorder(path, session_id="exit-session")
    trade = _trade()
    recorder.record_trade_open(trade)

    partial = SimpleNamespace(
        timestamp=1792739060, price=120.0, pnl=1000.0, quantity=25, lots=0,
        reason="PARTIAL_TARGET", remaining_quantity=25, remaining_lots=1,
    )
    trade.position.remaining_quantity = 25
    trade.position.gross_pnl = 1000.0
    trade.last_processed_timestamp = partial.timestamp
    recorder.record_trade_exit(trade, partial)
    recorder.record_trade_exit(trade, partial)

    opened = recorder.get_open_trades()
    assert len(opened) == 1
    assert opened[0]["remaining_quantity"] == 25
    assert opened[0]["gross_pnl"] == 1000.0

    final = SimpleNamespace(
        timestamp=1792739120, price=130.0, pnl=750.0, quantity=25, lots=1,
        reason="TARGET", remaining_quantity=0, remaining_lots=0,
    )
    trade.position.remaining_quantity = 0
    trade.position.remaining_lots = 0
    trade.position.gross_pnl = 1750.0
    trade.position.closed = True
    trade.last_processed_timestamp = final.timestamp
    recorder.record_trade_exit(trade, final)

    assert recorder.get_open_trades() == []
    events = recorder.get_trade_events(recorder._trade_id(trade))
    assert [event["event_type"] for event in events] == ["ENTRY", "EXIT", "EXIT"]
    assert events[1]["quantity"] == 25
    assert events[1]["pnl"] == 1000.0
    assert events[2]["reason"] == "TARGET"


def test_trade_ids_are_isolated_between_sessions(tmp_path: Path) -> None:
    path = tmp_path / "quant.db"
    initialize_database(path)
    first = SQLitePaperTradeRecorder(path, session_id="session-a")
    second = SQLitePaperTradeRecorder(path, session_id="session-b")
    trade = _trade()

    first.record_trade_open(trade)
    second.record_trade_open(trade)

    assert len(first.get_open_trades()) == 1
    assert len(second.get_open_trades()) == 1
    assert first.get_open_trades()[0]["trade_id"] != second.get_open_trades()[0]["trade_id"]


def test_signals_are_deduplicated_per_session(tmp_path: Path) -> None:
    path = tmp_path / "quant.db"
    initialize_database(path)
    recorder = SQLitePaperTradeRecorder(path, session_id="signal-session")
    signal = SimpleNamespace(
        strategy_id="KTMI", direction="LONG", timestamp=1792739000, index=12,
        reason="crossed threshold",
    )

    recorder.record_signal(signal, symbol="NSE:NIFTY26OCT22700CE")
    recorder.record_signal(signal, symbol="NSE:NIFTY26OCT22700CE")

    with sqlite3.connect(path) as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM paper_signals WHERE session_id=?",
            ("signal-session",),
        ).fetchone()[0]
    assert count == 1


def test_exit_for_unknown_trade_fails_instead_of_silently_creating_event(tmp_path: Path) -> None:
    path = tmp_path / "quant.db"
    initialize_database(path)
    recorder = SQLitePaperTradeRecorder(path, session_id="missing-trade-session")
    trade = _trade()
    exit_event = SimpleNamespace(
        timestamp=1792739060, price=120.0, pnl=1000.0, quantity=50, lots=1,
        reason="TARGET", remaining_quantity=0, remaining_lots=0,
    )

    with pytest.raises(sqlite3.IntegrityError):
        recorder.record_trade_exit(trade, exit_event)


def test_close_session_marks_only_running_session_stopped(tmp_path: Path) -> None:
    path = tmp_path / "quant.db"
    initialize_database(path)
    recorder = SQLitePaperTradeRecorder(path, session_id="close-session")
    recorder.close_session()
    recorder.close_session()

    with sqlite3.connect(path) as connection:
        status, ended_at = connection.execute(
            "SELECT status, ended_at FROM paper_sessions WHERE session_id=?",
            ("close-session",),
        ).fetchone()
    assert status == "STOPPED"
    assert ended_at
