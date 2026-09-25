from __future__ import annotations

import sqlite3
from collections import Counter
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from config.settings import DATABASE_PATH, EXPECTED_1M_CANDLES, TIMEZONE


SYMBOL = "NSE:NIFTY50-INDEX"
RESOLUTION = "1"
SOURCE = "FYERS_HISTORY"
MARKET_TZ = ZoneInfo(TIMEZONE)
EXPECTED_INTERVAL_SECONDS = 60


def _load_rows(connection: sqlite3.Connection) -> list[tuple]:
    return connection.execute(
        """
        SELECT c.timestamp, c.open, c.high, c.low, c.close
        FROM candles AS c
        JOIN instruments AS i ON i.id = c.instrument_id
        WHERE i.broker = 'FYERS'
          AND i.symbol = ?
          AND c.resolution = ?
          AND c.source = ?
        ORDER BY c.timestamp
        """,
        (SYMBOL, RESOLUTION, SOURCE),
    ).fetchall()


def main() -> None:
    print("=" * 80)
    print("KUNAL QUANT — NIFTY 1-MINUTE DATA QUALITY VALIDATION")
    print("=" * 80)
    print(f"Symbol    : {SYMBOL}")
    print(f"Resolution: {RESOLUTION}")
    print(f"Source    : {SOURCE}")
    print(f"Database  : {DATABASE_PATH}")
    print()

    if not Path(DATABASE_PATH).exists():
        raise FileNotFoundError(f"Database not found: {DATABASE_PATH}")

    with sqlite3.connect(DATABASE_PATH) as connection:
        rows = _load_rows(connection)

    if not rows:
        raise RuntimeError("No matching NIFTY 1-minute candles found.")

    timestamps = [row[0] for row in rows]
    distinct_timestamps = len(set(timestamps))

    invalid_ohlc = []
    non_positive_prices = []

    for timestamp, open_price, high, low, close in rows:
        if not (low <= open_price <= high and low <= close <= high and low <= high):
            invalid_ohlc.append(timestamp)
        if min(open_price, high, low, close) <= 0:
            non_positive_prices.append(timestamp)

    daily: dict[object, list[int]] = {}
    for timestamp in timestamps:
        day = datetime.fromtimestamp(timestamp, tz=MARKET_TZ).date()
        daily.setdefault(day, []).append(timestamp)

    wrong_first = []
    wrong_last = []
    unexpected_daily_counts = []
    intraday_gaps = []

    for day, day_timestamps in daily.items():
        local_times = [
            datetime.fromtimestamp(ts, tz=MARKET_TZ).time()
            for ts in day_timestamps
        ]

        first = local_times[0]
        last = local_times[-1]

        if (first.hour, first.minute) != (9, 15):
            wrong_first.append((day, first.isoformat()))

        if (last.hour, last.minute) != (15, 29):
            wrong_last.append((day, last.isoformat()))

        if len(day_timestamps) != EXPECTED_1M_CANDLES:
            unexpected_daily_counts.append((day, len(day_timestamps)))

        for previous, current in zip(day_timestamps, day_timestamps[1:]):
            delta = current - previous
            if delta != EXPECTED_INTERVAL_SECONDS:
                intraday_gaps.append((day, previous, current, delta))

    yearly_counts = Counter(
        datetime.fromtimestamp(ts, tz=MARKET_TZ).year for ts in timestamps
    )

    min_dt = datetime.fromtimestamp(min(timestamps), tz=MARKET_TZ)
    max_dt = datetime.fromtimestamp(max(timestamps), tz=MARKET_TZ)

    print("SUMMARY")
    print(f"Database rows       : {len(rows):,}")
    print(f"Distinct timestamps : {distinct_timestamps:,}")
    print(f"Duplicate timestamps: {len(rows) - distinct_timestamps:,}")
    print(f"Trading days        : {len(daily):,}")
    print(f"Min timestamp       : {min_dt.isoformat()}")
    print(f"Max timestamp       : {max_dt.isoformat()}")
    print()

    print("OHLC VALIDATION")
    print(f"Invalid OHLC rows   : {len(invalid_ohlc):,}")
    print(f"Non-positive prices : {len(non_positive_prices):,}")
    print()

    print("SESSION VALIDATION")
    print(f"Wrong first candle  : {len(wrong_first):,}")
    print(f"Wrong last candle   : {len(wrong_last):,}")
    print(f"Days != {EXPECTED_1M_CANDLES} candles: {len(unexpected_daily_counts):,}")
    print(f"Intraday gaps       : {len(intraday_gaps):,}")
    print()

    print("YEARLY COVERAGE")
    for year in sorted(yearly_counts):
        print(f"{year}: {yearly_counts[year]:,}")

    if invalid_ohlc:
        raise RuntimeError(f"Found {len(invalid_ohlc)} invalid OHLC row(s).")
    if non_positive_prices:
        raise RuntimeError(
            f"Found {len(non_positive_prices)} row(s) with non-positive prices."
        )
    if distinct_timestamps != len(rows):
        raise RuntimeError(
            f"Found {len(rows) - distinct_timestamps} duplicate timestamp(s)."
        )
    if intraday_gaps:
        print()
        print("INTRADAY GAP SAMPLE")
        for day, previous, current, delta in intraday_gaps[:5]:
            print(f"{day}: {previous} -> {current} (delta={delta}s)")
        raise RuntimeError(
            f"Found {len(intraday_gaps)} intraday timestamp gap(s)."
        )

    print()
    print("=" * 80)
    print("NIFTY 1-MINUTE DATA QUALITY VALIDATION PASSED")
    print("=" * 80)


if __name__ == "__main__":
    main()
