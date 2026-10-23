from datetime import date
import sqlite3

import pytest

from strategies.option_contract_resolver import OptionContractResolver


def _db(path, rows):
    with sqlite3.connect(path) as con:
        con.execute("""CREATE TABLE instruments (
            id INTEGER PRIMARY KEY, broker TEXT, exchange TEXT, segment TEXT,
            symbol TEXT, underlying TEXT, instrument_type TEXT, expiry_date TEXT,
            strike REAL, option_type TEXT, is_active INTEGER DEFAULT 1
        )""")
        con.executemany(
            """INSERT INTO instruments
            (id, broker, exchange, segment, symbol, underlying, instrument_type,
             expiry_date, strike, option_type, is_active)
            VALUES (?, 'FYERS', 'NSE', 'NFO', ?, ?, 'OPTIDX', ?, ?, ?, 1)""",
            rows,
        )


def test_resolver_selects_nifty_contract_for_configured_underlying(tmp_path):
    path = tmp_path / "instruments.db"
    _db(path, [
        (1, "NSE:NIFTY26102925000CE", "NIFTY", "2026-10-29", 25000, "CE"),
    ])
    resolver = OptionContractResolver(path, underlying_key="NIFTY50")
    contract = resolver.resolve(
        underlying_price=25000, entry_date=date(2026, 10, 23), direction="LONG"
    )
    assert contract.symbol == "NSE:NIFTY26102925000CE"
    assert contract.underlying == "NIFTY"


def test_banknifty_resolver_skips_earlier_weekly_expiry(tmp_path):
    path = tmp_path / "instruments.db"
    _db(path, [
        (1, "NSE:BANKNIFTY26102750000CE", "BANKNIFTY", "2026-10-27", 50000, "CE"),
        (2, "NSE:BANKNIFTY26102950000CE", "BANKNIFTY", "2026-10-29", 50000, "CE"),
        (3, "NSE:BANKNIFTY26102750000PE", "BANKNIFTY", "2026-10-27", 50000, "PE"),
        (4, "NSE:BANKNIFTY26102950000PE", "BANKNIFTY", "2026-10-29", 50000, "PE"),
    ])
    resolver = OptionContractResolver(
        path, underlying_key="BANKNIFTY"
    )
    contract = resolver.resolve(
        underlying_price=50000, entry_date=date(2026, 10, 23), direction="LONG"
    )
    assert contract.expiry_date == date(2026, 10, 29)


def test_resolver_fails_closed_when_requested_underlying_missing(tmp_path):
    path = tmp_path / "instruments.db"
    _db(path, [
        (1, "NSE:NIFTY26102925000CE", "NIFTY", "2026-10-29", 25000, "CE"),
    ])
    resolver = OptionContractResolver(path, underlying_key="SENSEX")
    with pytest.raises(LookupError, match="No eligible"):
        resolver.resolve(
            underlying_price=25000, entry_date=date(2026, 10, 23), direction="LONG"
        )
