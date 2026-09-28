
from __future__ import annotations

"""Probe FYERS 10-second historical-data availability.

This is intentionally a small, read-only diagnostic. It does not write
candles to the Kunal Quant database and does not modify any strategy.

The option and futures symbols are supplied explicitly so the probe never
guesses a contract.
"""

import argparse
import json
from datetime import datetime, timedelta

from api.fyers_client import FyersClient


def _date(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d")


def _probe(
    client: FyersClient,
    *,
    name: str,
    symbol: str,
    mode: str,
    range_from: str,
    range_to: str,
) -> dict:
    try:
        if mode == "standard":
            response = client.history(
                symbol=symbol,
                resolution="10S",
                range_from=range_from,
                range_to=range_to,
                date_format="1",
                cont_flag="0",
            )
        elif mode == "expired":
            response = client.expired_history(
                symbol=symbol,
                resolution="10S",
                range_from=range_from,
                range_to=range_to,
                include_oi="1",
                include_greeks="1",
                date_format="1",
            )
        else:
            raise ValueError(f"Unsupported mode: {mode}")

        candles = response.get("candles") or []
        first = candles[0][0] if candles else None
        last = candles[-1][0] if candles else None

        return {
            "name": name,
            "symbol": symbol,
            "mode": mode,
            "range_from": range_from,
            "range_to": range_to,
            "status": response.get("s"),
            "candles": len(candles),
            "first_timestamp": first,
            "last_timestamp": last,
            "response_keys": sorted(response.keys()),
        }
    except Exception as exc:
        return {
            "name": name,
            "symbol": symbol,
            "mode": mode,
            "range_from": range_from,
            "range_to": range_to,
            "status": "ERROR",
            "error": str(exc),
        }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Probe FYERS 10-second historical data availability."
    )
    parser.add_argument("--option-symbol", required=True)
    parser.add_argument("--futures-symbol", required=True)
    parser.add_argument("--from", dest="range_from", required=True)
    parser.add_argument("--to", dest="range_to", required=True)
    parser.add_argument(
        "--days-back",
        type=int,
        default=0,
        help="Shift the probe window backwards by this many calendar days.",
    )
    parser.add_argument(
        "--json",
        default=None,
        help="Optional output JSON path.",
    )
    args = parser.parse_args()

    start = _date(args.range_from)
    end = _date(args.range_to)

    if end < start:
        raise SystemExit("--to must be >= --from")

    if args.days_back < 0:
        raise SystemExit("--days-back cannot be negative")

    shifted_start = start - timedelta(days=args.days_back)
    shifted_end = end - timedelta(days=args.days_back)

    range_from = shifted_start.strftime("%Y-%m-%d")
    range_to = shifted_end.strftime("%Y-%m-%d")

    client = FyersClient()

    results = [
        _probe(
            client,
            name="NIFTY_INDEX",
            symbol="NSE:NIFTY50-INDEX",
            mode="standard",
            range_from=range_from,
            range_to=range_to,
        ),
        _probe(
            client,
            name="NIFTY_FUTURES",
            symbol=args.futures_symbol,
            mode="expired",
            range_from=range_from,
            range_to=range_to,
        ),
        _probe(
            client,
            name="NIFTY_OPTION",
            symbol=args.option_symbol,
            mode="expired",
            range_from=range_from,
            range_to=range_to,
        ),
    ]

    report = {
        "resolution": "10S",
        "range_from": range_from,
        "range_to": range_to,
        "results": results,
    }

    print("=" * 88)
    print("KUNAL QUANT — FYERS 10-SECOND HISTORICAL CAPABILITY PROBE")
    print("=" * 88)
    print(json.dumps(report, indent=2))

    if args.json:
        from pathlib import Path

        output = Path(args.json)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(report, indent=2),
            encoding="utf-8",
        )
        print(f"\nJSON written to: {output}")


if __name__ == "__main__":
    main()
