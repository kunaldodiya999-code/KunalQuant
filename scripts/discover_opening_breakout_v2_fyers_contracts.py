from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest.fyers_historical_contract_discovery import FyersHistoricalContractDiscovery


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Discover exact FYERS historical NIFTY option contracts from the acquisition manifest."
    )
    parser.add_argument("--manifest", default="opening_breakout_v2_option_acquisition_manifest.json")
    parser.add_argument("--limit-expiries", type=int, default=1)
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--output", default="opening_breakout_v2_fyers_contract_discovery.json")
    args = parser.parse_args()

    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    requested_by_expiry = defaultdict(list)

    for item in manifest["contracts"]:
        if item.get("instrument_id") is not None and not item.get("unregistered_dates"):
            continue
        requested_by_expiry[item["expiry_date"]].append(
            {"strike": float(item["strike"]), "option_type": item["option_type"]}
        )

    expiries = sorted(requested_by_expiry)
    if args.limit_expiries > 0:
        expiries = expiries[:args.limit_expiries]

    discovery = FyersHistoricalContractDiscovery()
    results = []
    total_requested = 0
    total_found = 0

    print("=" * 100)
    print("KUNAL QUANT — FYERS HISTORICAL CONTRACT DISCOVERY")
    print("=" * 100)
    print("READ-ONLY: no database registration, no candle downloads")
    print(f"Manifest contracts requiring discovery : {len(manifest['contracts'])}")
    print(f"Expiry dates selected                  : {len(expiries)}")

    for expiry_text in expiries:
        requested = requested_by_expiry[expiry_text]
        requested_keys = {(x["strike"], x["option_type"]) for x in requested}
        total_requested += len(requested_keys)

        print(f"\nChecking expiry {expiry_text} ...")
        contracts = discovery.discover_expiry(date.fromisoformat(expiry_text))
        found_by_key = {}
        if args.debug:
            print("  First 10 normalized FYERS contracts:")
            for sample in contracts[:10]:
                print("   ", repr(sample))

        for contract in contracts:
            symbol = contract.get("symbol")
            if not symbol:
                continue
            option_type = contract.get("option_type")
            strike = contract.get("strike")
            if option_type in {"CE", "PE"} and strike is not None:
                found_by_key[(float(strike), option_type)] = contract

        found_keys = requested_keys & set(found_by_key)
        total_found += len(found_keys)
        missing = [
            {"strike": strike, "option_type": option_type}
            for strike, option_type in sorted(requested_keys - set(found_keys))
        ]

        print(f"  FYERS contracts returned : {len(contracts)}")
        print(f"  Requested exact tuples   : {len(requested_keys)}")
        print(f"  Found exact tuples       : {len(found_keys)}")
        print(f"  Missing exact tuples     : {len(missing)}")

        results.append({
            "expiry_date": expiry_text,
            "requested": requested,
            "found": [
                {
                    "strike": key[0],
                    "option_type": key[1],
                    "symbol": found_by_key[key]["symbol"],
                    "raw": found_by_key[key],
                }
                for key in sorted(found_keys)
            ],
            "missing": missing,
            "returned_contract_count": len(contracts),
        })

    report = {
        "schema_version": 1,
        "source": "OPENING_BREAKOUT_V2_OPTION_ACQUISITION_MANIFEST",
        "read_only": True,
        "expiry_dates_checked": len(expiries),
        "requested_tuples": total_requested,
        "found_tuples": total_found,
        "missing_tuples": total_requested - total_found,
        "results": results,
    }

    Path(args.output).write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    print("\n" + "=" * 100)
    print("DISCOVERY SUMMARY")
    print("=" * 100)
    print(f"Requested tuples : {total_requested}")
    print(f"Found tuples     : {total_found}")
    print(f"Missing tuples   : {total_requested - total_found}")
    print(f"Report written   : {args.output}")
    print("=" * 100)


if __name__ == "__main__":
    main()
