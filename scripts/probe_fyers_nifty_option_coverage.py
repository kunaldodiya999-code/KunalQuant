"""Probe FYERS availability for representative empty NIFTY option contracts.

The probe is read-only. It does not insert or modify market data.
One CE and one PE are selected per expiry, preferring strikes near the
median available strike for that expiry. Results are written to CSV.
"""

from __future__ import annotations

import argparse
import csv
import sqlite3
import sys
import time
from datetime import date, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _extract_candles(response: dict) -> list:
    if not isinstance(response, dict):
        return []
    data = response.get("candles")
    if isinstance(data, list):
        return data
    data = response.get("data")
    if isinstance(data, dict) and isinstance(data.get("candles"), list):
        return data["candles"]
    if isinstance(data, list):
        return data
    return []


def _probe(client, symbol: str, expiry: str, days_before: int, retries: int) -> tuple[str, int, str, str, str]:
    expiry_date = date.fromisoformat(expiry)
    range_from = (expiry_date - timedelta(days=days_before)).isoformat()
    range_to = expiry
    last_error = ""

    for attempt in range(retries + 1):
        try:
            response = client.expired_history(
                symbol=symbol,
                resolution="1",
                range_from=range_from,
                range_to=range_to,
                include_oi="1",
                include_greeks="0",
            )
            candles = _extract_candles(response)
            if candles:
                first_ts = str(candles[0][0])
                last_ts = str(candles[-1][0])
            else:
                first_ts = last_ts = ""
            return "AVAILABLE" if candles else "NO_DATA", len(candles), first_ts, last_ts, ""
        except Exception as exc:  # FYERS SDK exposes heterogeneous API exceptions
            last_error = str(exc)
            if attempt < retries:
                time.sleep(1.5 * (attempt + 1))
    return "ERROR", 0, "", "", last_error


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "data" / "research" / "fyers_nifty_option_coverage_probe.csv")
    parser.add_argument("--days-before", type=int, default=30)
    parser.add_argument("--pause", type=float, default=0.7)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--max-probes", type=int, default=0, help="0 = all expiry/type probes")
    args = parser.parse_args()

    if args.database is None:
        from config.settings import DATABASE_PATH
        database_path = Path(DATABASE_PATH)
    else:
        database_path = args.database

    from api.fyers_client import FyersClient

    with sqlite3.connect(database_path) as db:
        db.row_factory = sqlite3.Row
        rows = db.execute(
            """
            WITH empty AS (
                SELECT i.id, i.symbol, i.expiry_date, i.strike, i.option_type,
                       ROW_NUMBER() OVER (
                           PARTITION BY i.expiry_date, i.option_type
                           ORDER BY ABS(i.strike - (
                               SELECT AVG(x.strike)
                               FROM instruments x
                               WHERE x.broker='FYERS'
                                 AND x.underlying='NIFTY'
                                 AND x.option_type=i.option_type
                                 AND x.expiry_date=i.expiry_date
                                 AND x.strike > 0
                           )), i.strike
                       ) AS rn
                FROM instruments i
                LEFT JOIN (
                    SELECT instrument_id, COUNT(*) AS cnt
                    FROM candles
                    WHERE resolution='1' AND source='FYERS_FNO_HISTORY'
                    GROUP BY instrument_id
                ) c ON c.instrument_id=i.id
                WHERE i.broker='FYERS'
                  AND i.underlying='NIFTY'
                  AND i.option_type IN ('CE','PE')
                  AND i.expiry_date <= date('now')
                  AND i.strike > 0
                  AND COALESCE(c.cnt,0)=0
            )
            SELECT id, symbol, expiry_date, strike, option_type
            FROM empty
            WHERE rn=1
            ORDER BY expiry_date, option_type
            """
        ).fetchall()

    if args.max_probes:
        rows = rows[: args.max_probes]

    args.output.parent.mkdir(parents=True, exist_ok=True)
    client = FyersClient()

    fields = [
        "instrument_id", "symbol", "expiry_date", "strike", "option_type",
        "range_from", "range_to", "status", "candle_count", "first_timestamp",
        "last_timestamp", "error",
    ]

    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()

        for index, row in enumerate(rows, 1):
            status, count, first_ts, last_ts, error = _probe(
                client, row["symbol"], row["expiry_date"], args.days_before, args.retries
            )
            expiry_date = date.fromisoformat(row["expiry_date"])
            range_from = (expiry_date - timedelta(days=args.days_before)).isoformat()
            writer.writerow({
                "instrument_id": row["id"],
                "symbol": row["symbol"],
                "expiry_date": row["expiry_date"],
                "strike": row["strike"],
                "option_type": row["option_type"],
                "range_from": range_from,
                "range_to": row["expiry_date"],
                "status": status,
                "candle_count": count,
                "first_timestamp": first_ts,
                "last_timestamp": last_ts,
                "error": error,
            })
            print(f"[{index:03d}/{len(rows):03d}] {row['expiry_date']} {row['option_type']} {row['symbol']} -> {status} candles={count}")
            handle.flush()
            if index < len(rows):
                time.sleep(max(0.0, args.pause))

    print("=" * 90)
    print("FYERS OPTION COVERAGE PROBE COMPLETE")
    print("=" * 90)
    print(f"Probe rows : {len(rows)}")
    print(f"Output     : {args.output}")


if __name__ == "__main__":
    main()
