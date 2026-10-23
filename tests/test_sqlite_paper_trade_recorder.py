from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from database.schema import initialize_database, get_schema_summary
from paper_trading.sqlite_recorder import SQLitePaperTradeRecorder


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

    position = SimpleNamespace(
        symbol="NSE:NIFTY26OCT22700CE", direction="LONG", entry_price=100.0,
        quantity=50, lots=1, stop_loss=80.0, target=140.0,
        remaining_quantity=50, remaining_lots=1, gross_pnl=0.0, closed=False,
    )
    trade = SimpleNamespace(
        strategy_id="KTMI_LONG_SHORT_SPEED", entry_timestamp=1792739000,
        position=position, last_processed_timestamp=1792739000,
    )
    recorder.record_trade_open(trade)
    recorder.record_trade_open(trade)

    opened = recorder.get_open_trades()
    assert len(opened) == 1
    assert opened[0]["symbol"] == position.symbol
    assert opened[0]["stop_loss"] == 80.0
    assert opened[0]["target"] == 140.0
    events = recorder.get_trade_events(opened[0]["trade_id"])
    assert [event["event_type"] for event in events] == ["ENTRY"]
