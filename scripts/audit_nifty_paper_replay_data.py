"""Read-only readiness audit for replaying today's NIFTY 50 paper signals.

Run from repository root:
    python scripts/audit_nifty_paper_replay_data.py
Optional:
    python scripts/audit_nifty_paper_replay_data.py --date 2026-10-23

This reports data coverage only; it does not fabricate entries or claim a backtest.
"""
from __future__ import annotations

import argparse
import sqlite3
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from config.settings import DATABASE_PATH

TZ = ZoneInfo("Asia/Kolkata")
ALIASES = ("NIFTY", "NIFTY50")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=DATABASE_PATH)
    parser.add_argument("--date", help="Trading date YYYY-MM-DD; defaults to today's India date.")
    args = parser.parse_args()
    trading_date = date.fromisoformat(args.date) if args.date else datetime.now(TZ).date()
    start = int(datetime.combine(trading_date, datetime.min.time(), TZ).timestamp())
    end = start + 24 * 60 * 60

    print("KUNAL QUANT — NIFTY 50 REPLAY DATA AUDIT")
    print(f"trading_date={trading_date.isoformat()}")
    print(f"database={args.database.resolve()}")
    if not args.database.is_file():
        print("RESULT=DATABASE_MISSING")
        return 2

    with sqlite3.connect(args.database.resolve().as_uri() + "?mode=ro", uri=True) as con:
        con.row_factory = sqlite3.Row
        tables = {row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {"instruments", "candles"}.issubset(tables):
            print("RESULT=SCHEMA_MISSING")
            return 2

        index_rows = con.execute(
            """SELECT i.id,i.symbol,i.underlying,i.instrument_type,i.exchange,i.is_active,
                      COUNT(c.id) AS today_candles,
                      MIN(c.timestamp) AS first_ts, MAX(c.timestamp) AS last_ts,
                      GROUP_CONCAT(DISTINCT c.resolution) AS resolutions,
                      GROUP_CONCAT(DISTINCT c.source) AS sources
               FROM instruments i LEFT JOIN candles c
                 ON c.instrument_id=i.id AND c.timestamp>=? AND c.timestamp<?
               WHERE i.broker='FYERS'
                 AND (i.symbol='NSE:NIFTY50-INDEX'
                      OR (i.underlying IN (?,?) AND UPPER(i.instrument_type) IN ('INDEX','IDX')))
               GROUP BY i.id
               ORDER BY i.symbol""",
            (start, end, *ALIASES),
        ).fetchall()
        print("\nINDEX INSTRUMENTS")
        if not index_rows:
            print("  No matching NIFTY 50 index instrument rows found.")
        for row in index_rows:
            print(f"  id={row['id']} symbol={row['symbol']} underlying={row['underlying']} "
                  f"type={row['instrument_type']} exchange={row['exchange']} active={row['is_active']} "
                  f"candles_today={row['today_candles']} resolutions={row['resolutions']} sources={row['sources']} "
                  f"first_ts={row['first_ts']} last_ts={row['last_ts']}")

        options = con.execute(
            """SELECT i.id,i.symbol,i.underlying,i.expiry_date,i.strike,i.option_type,
                      i.lot_size,i.exchange,COUNT(c.id) AS today_candles,
                      GROUP_CONCAT(DISTINCT c.resolution) AS resolutions,
                      MIN(c.timestamp) AS first_ts,MAX(c.timestamp) AS last_ts
               FROM instruments i LEFT JOIN candles c
                 ON c.instrument_id=i.id AND c.timestamp>=? AND c.timestamp<?
               WHERE i.broker='FYERS' AND i.exchange='NSE'
                 AND i.underlying IN (?,?) AND i.instrument_type IN ('OPTION','OPTIDX','OPT')
                 AND i.expiry_date>=? AND i.is_active=1
               GROUP BY i.id
               ORDER BY i.expiry_date,i.strike,i.option_type""",
            (start, end, *ALIASES, trading_date.isoformat()),
        ).fetchall()
        with_candles = [r for r in options if r["today_candles"]]
        print("\nNIFTY OPTION CANDLE COVERAGE")
        print(f"  eligible_option_contracts={len(options)}")
        print(f"  option_contracts_with_candles_today={len(with_candles)}")
        print(f"  total_option_candles_today={sum(int(r['today_candles']) for r in with_candles)}")
        for row in with_candles[:20]:
            print(f"  symbol={row['symbol']} expiry={row['expiry_date']} strike={row['strike']} "
                  f"type={row['option_type']} lot_size={row['lot_size']} candles={row['today_candles']} "
                  f"resolutions={row['resolutions']} first_ts={row['first_ts']} last_ts={row['last_ts']}")
        if len(with_candles) > 20:
            print(f"  ... {len(with_candles)-20} more option contracts omitted")

    if not index_rows or not any(int(row["today_candles"]) for row in index_rows):
        print("\nRESULT=INDEX_CANDLES_MISSING — a faithful signal replay cannot be done from today's stored index data.")
        return 1
    if not with_candles:
        print("\nRESULT=OPTION_CANDLES_MISSING — signals may be reconstructable, but option entry/exit replay is not supported by today's stored option candles.")
        return 1
    print("\nRESULT=DATA_PRESENT_FOR_REPLAY_REVIEW — this audit only confirms coverage, not strategy outcomes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
