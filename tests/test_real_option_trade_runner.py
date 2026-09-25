from pathlib import Path

import sqlite3

from backtest.fyers_option_candles import FyersOptionCandleLoader
from backtest.models import BacktestBar
from backtest.real_option_trade_runner import calculate_nifty_kama
from strategies.ktmi_trigger_strategy import (
    KTMITriggerEvent,
    TriggerDirection,
    TriggerStrategyId,
)


def test_real_runner_uses_existing_kama_implementation():
    bars = [
        BacktestBar(100, 100, 101, 99, 100),
        BacktestBar(101, 101, 102, 100, 101),
        BacktestBar(102, 102, 103, 101, 102),
    ]

    results = calculate_nifty_kama(bars)

    assert len(results) == len(bars)


def test_option_loader_reads_real_data_contract(tmp_path: Path):
    db = tmp_path / "real.db"

    with sqlite3.connect(db) as connection:
        connection.execute(
            """
            CREATE TABLE candles (
                instrument_id INTEGER,
                timestamp INTEGER,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                volume INTEGER,
                open_interest INTEGER,
                resolution TEXT,
                source TEXT
            )
            """
        )
        connection.execute(
            "INSERT INTO candles VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (99, 10, 10, 11, 9, 10.5, 1, 1, "1", "FYERS_FNO_HISTORY"),
        )

    loader = FyersOptionCandleLoader(db)
    candles = loader(99, 10, 10)

    assert candles[0].timestamp == 10
    assert candles[0].close == 10.5
