"""Targeted acquisition of FYERS expired NIFTY option candles.

This layer discovers only the exact contracts required by the existing KTMI
event/resolver pipeline. It does not change resolver or strategy logic.
"""

from __future__ import annotations

import argparse
import re
import sqlite3
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from api.fyers_client import FyersClient
from backtest.ktmi_trigger_pipeline import run_ktmi_trigger_pipeline
from config.settings import DATABASE_PATH
from scripts.run_real_option_sample import (
    build_ktmi_config,
    load_complete_3m_bars,
)
from strategies.option_contract_resolver import OptionContractResolver
from downloader.historical import HistoricalDownloader

TZ = ZoneInfo("Asia/Kolkata")
UNDERLYING_SYMBOL = "NSE:NIFTY50-INDEX"
OPTION_SYMBOL_RE = re.compile(r"^(?P<prefix>NSE:NIFTY)(?P<code>\d+)(?P<strike>\d{4,5})(?P<type>CE|PE)$")


def _extract_symbols(value) -> set[str]:
    """Recursively extract FYERS NIFTY option symbols from an API response."""
    found: set[str] = set()
    if isinstance(value, str):
        if value.startswith("NSE:NIFTY") and value.endswith(("CE", "PE")):
            found.add(value)
    elif isinstance(value, dict):
        for item in value.values():
            found.update(_extract_symbols(item))
    elif isinstance(value, (list, tuple)):
        for item in value:
            found.update(_extract_symbols(item))
    return found


def _strike_from_symbol(symbol: str) -> int | None:
    match = OPTION_SYMBOL_RE.match(symbol)
    if not match:
        return None
    return int(match.group("strike"))


def _option_type_from_symbol(symbol: str) -> str | None:
    if symbol.endswith("CE"):
        return "CE"
    if symbol.endswith("PE"):
        return "PE"
    return None


def _discover_required_symbols(
    client: FyersClient,
    required_by_expiry: dict[str, set[tuple[int, str]]],
) -> dict[tuple[str, int, str], str]:
    discovered: dict[tuple[str, int, str], str] = {}
    for expiry, requirements in sorted(required_by_expiry.items()):
        response = client.expired_contracts(
            symbol=UNDERLYING_SYMBOL,
            expiry_date=expiry,
        )
        symbols = _extract_symbols(response)
        for symbol in symbols:
            strike = _strike_from_symbol(symbol)
            option_type = _option_type_from_symbol(symbol)
            if strike is None or option_type is None:
                continue
            key = (expiry, strike, option_type)
            if key in requirements:
                discovered[key] = symbol
    return discovered


def _register_instrument(
    database_path: Path | str,
    symbol: str,
    expiry: str,
    strike: int,
    option_type: str,
) -> int:
    with sqlite3.connect(database_path) as db:
        row = db.execute(
            "SELECT id FROM instruments WHERE broker='FYERS' AND symbol=?",
            (symbol,),
        ).fetchone()
        if row:
            return int(row[0])

        # Reuse metadata from any existing NIFTY option instrument where possible.
        template = db.execute(
            """
            SELECT exchange, segment, lot_size, tick_size, currency
            FROM instruments
            WHERE broker='FYERS' AND underlying='NIFTY'
              AND instrument_type='OPTION'
            ORDER BY id
            LIMIT 1
            """
        ).fetchone()

        exchange, segment, lot_size, tick_size, currency = (
            template if template else ("NSE", "11", 65, 0.05, "INR")
        )

        db.execute(
            """
            INSERT INTO instruments (
                broker, exchange, segment, symbol, underlying,
                instrument_type, expiry_date, strike, option_type,
                lot_size, tick_size, currency, is_active
            )
            VALUES (?, ?, ?, ?, 'NIFTY', 'OPTION', ?, ?, ?, ?, ?, ?, 1)
            ON CONFLICT(broker, symbol) DO UPDATE SET
                expiry_date=excluded.expiry_date,
                strike=excluded.strike,
                option_type=excluded.option_type,
                is_active=1,
                updated_at=CURRENT_TIMESTAMP
            """,
            (
                "FYERS", exchange, segment, symbol, expiry,
                float(strike), option_type, lot_size, tick_size, currency,
            ),
        )
        db.commit()
        row = db.execute(
            "SELECT id FROM instruments WHERE broker='FYERS' AND symbol=?",
            (symbol,),
        ).fetchone()
        if not row:
            raise RuntimeError(f"Failed to register instrument: {symbol}")
        return int(row[0])


def build_required_contracts() -> tuple[dict[str, set[tuple[int, str]]], int, int]:
    bars = load_complete_3m_bars()
    pipeline = run_ktmi_trigger_pipeline(bars, build_ktmi_config())
    resolver = OptionContractResolver(DATABASE_PATH)

    required: dict[str, set[tuple[int, str]]] = defaultdict(set)
    for event in pipeline.events:
        bar = bars[event.index]
        entry_date = datetime.fromtimestamp(bar.timestamp, tz=TZ).date()
        option_type = "CE" if event.direction.value == "LONG" else "PE"
        expiry = resolver.find_nearest_expiry(entry_date, option_type)
        strike = resolver.calculate_atm_strike(bar.close)
        required[expiry.isoformat()].add((strike, option_type))

    return required, len(bars), len(pipeline.events)


def main() -> None:
    parser = argparse.ArgumentParser(description="Acquire targeted NIFTY option history.")
    parser.add_argument("--from-date", default=None, help="Optional earliest event date YYYY-MM-DD.")
    parser.add_argument("--to-date", default=None, help="Optional latest event date YYYY-MM-DD.")
    args = parser.parse_args()

    required, bar_count, event_count = build_required_contracts()
    if args.from_date or args.to_date:
        # The current sample loader is intentionally fixed; filtering belongs in a
        # future general runner. Refuse silently misleading partial requests.
        raise SystemExit("Date filtering is not implemented; run the bounded sample as configured.")

    client = FyersClient()
    discovered = _discover_required_symbols(client, required)

    print("=" * 80)
    print("KUNAL QUANT — TARGETED NIFTY OPTION ACQUISITION")
    print("=" * 80)
    print(f"3M bars examined       : {bar_count:,}")
    print(f"KTMI events examined   : {event_count:,}")
    print(f"Required contract keys : {sum(len(v) for v in required.values()):,}")
    print(f"FYERS contracts found  : {len(discovered):,}")
    print(f"Missing from FYERS     : {sum(len(v) for v in required.values()) - len(discovered):,}")
    print()

    downloader = HistoricalDownloader()
    totals = {"inserted": 0, "received": 0, "failed": 0}
    for expiry, requirements in sorted(required.items()):
        for strike, option_type in sorted(requirements):
            key = (expiry, strike, option_type)
            symbol = discovered.get(key)
            if symbol is None:
                print(f"[MISS] {expiry} {strike} {option_type}")
                continue

            instrument_id = _register_instrument(
                DATABASE_PATH, symbol, expiry, strike, option_type
            )
            print(f"[OK] {expiry} {strike} {option_type} -> {symbol} (instrument={instrument_id})")

            result = downloader.download_symbol(
                symbol=symbol,
                range_from=expiry,
                range_to=expiry,
                resolution="1",
                mode="expired",
            )
            totals["received"] += int(result["received"])
            totals["inserted"] += int(result["inserted"])
            totals["failed"] += int(result["failed"])

    print()
    print(f"Candles received : {totals['received']:,}")
    print(f"Candles inserted : {totals['inserted']:,}")
    print(f"Failed chunks    : {totals['failed']:,}")
    print("TARGETED ACQUISITION COMPLETE")


if __name__ == "__main__":
    main()
