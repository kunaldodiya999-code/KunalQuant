from __future__ import annotations

import sqlite3

from paper_trading import dashboard_app


def _make_journal(path):
    with sqlite3.connect(path) as con:
        con.executescript("""
            CREATE TABLE paper_sessions (
                session_id TEXT PRIMARY KEY, status TEXT, started_at TEXT,
                starting_capital REAL, metadata_json TEXT
            );
            CREATE TABLE paper_signals (
                id INTEGER PRIMARY KEY, signal_timestamp INTEGER, symbol TEXT,
                strategy_id TEXT, direction TEXT, status TEXT,
                rejection_reason TEXT, reason TEXT
            );
            CREATE TABLE paper_trades (
                trade_id TEXT PRIMARY KEY, session_id TEXT, status TEXT,
                symbol TEXT, direction TEXT, entry_price REAL,
                remaining_quantity INTEGER, stop_loss REAL, target REAL,
                gross_pnl REAL, entry_timestamp INTEGER
            );
            CREATE TABLE paper_trade_events (
                id INTEGER PRIMARY KEY, trade_id TEXT, event_timestamp INTEGER,
                event_type TEXT, price REAL, quantity INTEGER, pnl REAL, reason TEXT
            );
            INSERT INTO paper_sessions VALUES
                ('paper-test', 'RUNNING', '2026-10-23 09:00:00', 100000, '{"underlying_key":"NIFTY50"}');
            INSERT INTO paper_signals VALUES
                (1, 1792746000, 'NSE:TESTCE', 'KTMI', 'LONG', 'RECEIVED', NULL, 'test');
            INSERT INTO paper_trades VALUES
                ('t-open', 'paper-test', 'OPEN', 'NSE:TESTCE', 'LONG', 100, 25, 70, 160, 0, 1792746000);
            INSERT INTO paper_trades VALUES
                ('t-closed', 'paper-test', 'CLOSED', 'NSE:TESTPE', 'SHORT', 80, 0, 110, 40, -1000, 1792745000);
            INSERT INTO paper_trade_events VALUES
                (1, 't-closed', 1792745500, 'EXIT', 120, 25, -1000, 'STOP_LOSS');
        """)


def test_read_summary_reads_paper_records_without_writing(tmp_path, monkeypatch):
    path = tmp_path / "paper.sqlite"
    _make_journal(path)
    monkeypatch.setattr(dashboard_app, "DB_PATH", path)

    before = path.stat().st_mtime_ns
    result = dashboard_app.read_summary()
    after = path.stat().st_mtime_ns

    assert result["database_exists"] is True
    assert result["metrics"]["sessions"] == 1
    assert result["metrics"]["signals"] == 1
    assert result["metrics"]["trades"] == 2
    assert result["metrics"]["realized_gross_pnl"] == -1000
    assert result["sessions"][0]["underlying"] == "NIFTY50"
    assert result["open_trades"][0]["symbol"] == "NSE:TESTCE"
    assert result["events"][0]["reason"] == "STOP_LOSS"
    assert result["signals"][0]["reason"] == "test"
    assert before == after


def test_read_summary_missing_database_returns_empty_state(tmp_path, monkeypatch):
    path = tmp_path / "missing.sqlite"
    monkeypatch.setattr(dashboard_app, "DB_PATH", path)

    result = dashboard_app.read_summary()

    assert result["database_exists"] is False
    assert result["metrics"]["trades"] == 0
    assert result["sessions"] == []


def test_read_summary_reports_uninitialized_database(tmp_path, monkeypatch):
    path = tmp_path / "empty.sqlite"
    sqlite3.connect(path).close()
    monkeypatch.setattr(dashboard_app, "DB_PATH", path)

    result = dashboard_app.read_summary()

    assert "not present" in result["error"]
