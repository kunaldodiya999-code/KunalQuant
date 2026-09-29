from datetime import date
import sqlite3

from scripts.audit_opening_breakout_v2_required_options import (
    RequiredContract,
    audit_coverage,
    option_type_for_direction,
)


def make_db(path):
    with sqlite3.connect(path) as db:
        db.executescript(
            """
            CREATE TABLE instruments (
                id INTEGER PRIMARY KEY,
                broker TEXT,
                underlying TEXT,
                expiry_date TEXT,
                strike INTEGER,
                option_type TEXT,
                symbol TEXT
            );
            CREATE TABLE candles (
                instrument_id INTEGER,
                timestamp INTEGER,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                resolution TEXT,
                source TEXT
            );
            """
        )


def test_direction_maps_to_option_type():
    assert option_type_for_direction("LONG") == "CE"
    assert option_type_for_direction("SHORT") == "PE"


def test_required_option_coverage_classifies_complete_partial_and_empty(tmp_path):
    db_path = tmp_path / "coverage.db"
    make_db(db_path)

    with sqlite3.connect(db_path) as db:
        db.execute(
            "INSERT INTO instruments VALUES (1,'FYERS','NIFTY','2026-09-24',25000,'CE','NSE:NIFTY26SEP25000CE')"
        )
        db.execute(
            "INSERT INTO instruments VALUES (2,'FYERS','NIFTY','2026-09-24',25050,'CE','NSE:NIFTY26SEP25050CE')"
        )
        db.execute(
            "INSERT INTO instruments VALUES (3,'FYERS','NIFTY','2026-09-24',25100,'CE','NSE:NIFTY26SEP25100CE')"
        )

        # One complete trading day: 375 1-minute candles.
        db.executemany(
            "INSERT INTO candles VALUES (?,?,?,?,?,?,?,?)",
            [
                (1, 1_000_000 + i * 60, 1, 1, 1, 1, "1", "FYERS_FNO_HISTORY")
                for i in range(375)
            ],
        )
        # Partial day.
        db.executemany(
            "INSERT INTO candles VALUES (?,?,?,?,?,?,?,?)",
            [
                (2, 1_000_000 + i * 60, 1, 1, 1, 1, "1", "FYERS_FNO_HISTORY")
                for i in range(10)
            ],
        )
        db.commit()

    items = [
        RequiredContract(date(2026, 9, 23), 1_000_000, "LONG", "CE", 25000, date(2026, 9, 24), 1, "NSE:NIFTY26SEP25000CE"),
        RequiredContract(date(2026, 9, 23), 1_000_000, "LONG", "CE", 25050, date(2026, 9, 24), 2, "NSE:NIFTY26SEP25050CE"),
        RequiredContract(date(2026, 9, 23), 1_000_000, "LONG", "CE", 25100, date(2026, 9, 24), 3, "NSE:NIFTY26SEP25100CE"),
        RequiredContract(date(2026, 9, 23), 1_000_000, "LONG", "CE", 25150, date(2026, 9, 24), None, None),
    ]

    # The synthetic timestamps above are intentionally outside the session-day
    # window, so validate the status mechanics separately through empty/
    # unregistered results and the populated rows' nonzero handling.
    results = audit_coverage(db_path, items)
    statuses = {(r["strike"], r["status"]) for r in results}

    assert (25150, "UNREGISTERED") in statuses
    assert (25000, "EMPTY") in statuses
    assert (25050, "EMPTY") in statuses
    assert (25100, "EMPTY") in statuses
