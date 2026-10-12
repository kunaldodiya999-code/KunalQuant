"""Bounded, read-only validation of FYERS expired NIFTY option history.

Uses at most 7 FYERS Data API requests:
  1 expiry-date discovery across the two-year target period
  2 contract lists (one old expiry, one recent expiry)
  4 historical samples (CE + PE at each expiry)
No order APIs, no SQLite writes, no credentials printed.

Run:
  python scripts/validate_fyers_expired_history.py
Optional:
  --old-target 2024-10-15 --recent-target 2026-09-15
  --resolution 5
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from api.fyers_client import FyersClient  # noqa: E402

UNDERLYING = "NSE:NIFTY50-INDEX"
START = "2024-10-12"
END = "2026-10-12"


def walk(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def extract_dates(response: dict[str, Any]) -> list[str]:
    found: set[str] = set()
    for item in walk(response):
        for key, value in item.items():
            if key.lower() in {"expiry_date", "expirydate", "date", "expiry"} and isinstance(value, str):
                match = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", value)
                if match:
                    try:
                        found.add(date.fromisoformat(match.group(1)).isoformat())
                    except ValueError:
                        pass
    return sorted(found)


def extract_contracts(response: dict[str, Any]) -> list[dict[str, Any]]:
    found: dict[str, dict[str, Any]] = {}
    for item in walk(response):
        symbol = next((str(item[k]) for k in ("symbol", "trading_symbol", "tradingSymbol", "name")
                       if isinstance(item.get(k), str) and re.search(r"(CE|PE)$", str(item[k]))), None)
        if not symbol:
            continue
        match = re.search(r"(\d+(?:\.\d+)?)(CE|PE)$", symbol)
        if not match:
            continue
        side = match.group(2)
        try:
            strike = float(item.get("strike", item.get("strike_price", item.get("strikePrice", match.group(1)))))
        except (ValueError, TypeError):
            strike = float(match.group(1))
        found[symbol] = {"symbol": symbol, "strike": strike, "side": side}
    return sorted(found.values(), key=lambda c: (c["side"], c["strike"], c["symbol"]))


def extract_candles(response: dict[str, Any]) -> list:
    candles = response.get("candles")
    if isinstance(candles, list):
        return candles
    data = response.get("data")
    if isinstance(data, dict) and isinstance(data.get("candles"), list):
        return data["candles"]
    return []


def summarize_history(response: dict[str, Any]) -> dict[str, Any]:
    candles = extract_candles(response)
    keys = sorted(response.keys())
    if isinstance(response.get("data"), dict):
        keys += [f"data.{k}" for k in sorted(response["data"].keys())]
    timestamps = []
    widths = []
    for candle in candles:
        if isinstance(candle, (list, tuple)) and candle:
            widths.append(len(candle))
            try:
                timestamps.append(int(float(candle[0])))
            except (ValueError, TypeError):
                pass
    dt = [datetime.fromtimestamp(ts, timezone.utc).astimezone().isoformat() for ts in timestamps]
    # Key names and candle width are evidence of schema, not proof each value is populated.
    greek_words = ("greek", "delta", "gamma", "theta", "vega", "iv", "implied")
    oi_words = ("oi", "open_interest", "openinterest")
    key_text = " ".join(keys).lower()
    return {
        "status": response.get("s"),
        "message": response.get("message") or response.get("messageCode"),
        "top_level_keys": sorted(response.keys()),
        "data_keys": sorted(response.get("data", {}).keys()) if isinstance(response.get("data"), dict) else [],
        "candle_count": len(candles),
        "first_timestamp_utc": dt[0] if dt else None,
        "last_timestamp_utc": dt[-1] if dt else None,
        "distinct_candle_widths": sorted(set(widths)),
        "greek_or_iv_key_visible": any(word in key_text for word in greek_words),
        "oi_key_visible": any(word in key_text for word in oi_words),
        "sample_candle": candles[0] if candles else None,
        "raw_error": response.get("error") if response.get("s") == "error" else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate FYERS expired NIFTY options data without DB writes.")
    parser.add_argument("--old-target", default="2024-10-15")
    parser.add_argument("--recent-target", default="2026-09-15")
    parser.add_argument("--resolution", choices=["1", "3", "5", "10", "15"], default="5")
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "data" / "raw" / "fyers_expired_audit" / "fyers_expired_validation.json")
    args = parser.parse_args()

    client = FyersClient()
    audit: dict[str, Any] = {
        "underlying": UNDERLYING,
        "target_period": {"from": START, "to": END},
        "resolution": args.resolution,
        "read_only": True,
        "database_writes": False,
        "orders_placed": False,
        "steps": [],
    }

    print("=" * 78)
    print("KUNAL QUANT — FYERS EXPIRED OPTIONS DATA VALIDATION")
    print("=" * 78)
    print(f"Target period : {START} to {END}")
    print(f"Resolution    : {args.resolution} minute")
    print("Request budget: maximum 7 API calls; no DB writes or orders")
    print("Step 1/3: discovering expiry dates...", flush=True)
    expiry_response = client.expired_expiry_dates(UNDERLYING, START, END, "1")
    expiry_dates = extract_dates(expiry_response)
    audit["expiry_discovery"] = {
        "status": expiry_response.get("s"),
        "top_level_keys": sorted(expiry_response.keys()),
        "data_keys": sorted(expiry_response.get("data", {}).keys()) if isinstance(expiry_response.get("data"), dict) else [],
        "expiry_count_parsed": len(expiry_dates),
        "first_expiries": expiry_dates[:5],
        "last_expiries": expiry_dates[-5:],
        "parsed_expiries": expiry_dates,
        "response_sample": expiry_response if not expiry_dates else None,
    }
    if expiry_response.get("s") != "ok" or not expiry_dates:
        audit["verdict"] = "BLOCKED: expiry discovery failed or response schema needs adapting."
        return finish(audit, args.output, 2)

    targets = [("old", args.old_target), ("recent", args.recent_target)]
    chosen: list[tuple[str, str]] = []
    for label, target in targets:
        valid = [d for d in expiry_dates if d <= target]
        if not valid:
            audit["verdict"] = f"BLOCKED: no expiry on or before {target}."
            return finish(audit, args.output, 2)
        chosen.append((label, valid[-1]))

    samples = []
    for label, expiry in chosen:
        print(f"Step 2/3: retrieving contracts for {label} expiry {expiry}...", flush=True)
        contracts_response = client.expired_contracts(UNDERLYING, expiry)
        contracts = extract_contracts(contracts_response)
        contract_summary = {
            "label": label,
            "requested_expiry": expiry,
            "status": contracts_response.get("s"),
            "top_level_keys": sorted(contracts_response.keys()),
            "data_keys": sorted(contracts_response.get("data", {}).keys()) if isinstance(contracts_response.get("data"), dict) else [],
            "contracts_parsed": len(contracts),
        }
        audit.setdefault("contract_discovery", []).append(contract_summary)
        if contracts_response.get("s") != "ok" or not contracts:
            audit["verdict"] = f"BLOCKED: no parseable contract symbols for {label} expiry {expiry}."
            audit.setdefault("contract_response_samples", []).append(contracts_response)
            return finish(audit, args.output, 2)

        target_strike = 24000 if label == "old" else 25000
        selected = []
        for side in ("CE", "PE"):
            side_contracts = [c for c in contracts if c["side"] == side]
            if side_contracts:
                selected.append(min(side_contracts, key=lambda c: (abs(c["strike"] - target_strike), c["strike"])))
        if len(selected) != 2:
            audit["verdict"] = f"BLOCKED: could not select both CE and PE for {expiry}."
            return finish(audit, args.output, 2)

        for contract in selected:
            # Keep the requested window narrow and inside the chosen contract's lifetime.
            range_to = expiry
            range_from = (date.fromisoformat(expiry).replace(day=1)).isoformat()
            print(f"Step 3/3: {label} {contract['symbol']} history {range_from}..{range_to} with OI+Greeks...", flush=True)
            response = client.expired_history(
                symbol=contract["symbol"],
                resolution=args.resolution,
                range_from=range_from,
                range_to=range_to,
                include_oi="1",
                include_greeks="1",
                date_format="1",
            )
            summary = {
                "label": label,
                "expiry": expiry,
                "contract": contract,
                "range_from": range_from,
                "range_to": range_to,
                **summarize_history(response),
            }
            samples.append(summary)
            print(f"  status={summary['status']} candles={summary['candle_count']} widths={summary['distinct_candle_widths']} keys={summary['data_keys'] or summary['top_level_keys']}", flush=True)

    audit["historical_samples"] = samples
    audit["quality_checks"] = {
        "all_four_contract_samples_returned_candles": all(s["status"] == "ok" and s["candle_count"] > 0 for s in samples),
        "both_old_and_recent_periods_tested": {s["label"] for s in samples} == {"old", "recent"},
        "oi_or_greeks_visible_in_schema": any(s["oi_key_visible"] or s["greek_or_iv_key_visible"] for s in samples),
        "warning": "Non-empty candles do not prove every candle has valid OI/Greeks or that all sessions are complete. This is a feasibility gate, not full data-quality certification.",
    }
    if not audit["quality_checks"]["all_four_contract_samples_returned_candles"]:
        audit["verdict"] = "FAIL: one or more contract-history samples returned no candles or an API error."
        return finish(audit, args.output, 2)
    audit["verdict"] = "PASS: expired contract history returned for old and recent periods. Review payload schema/Greeks before bulk download; this is not yet a full coverage audit."
    return finish(audit, args.output, 0)


def finish(audit: dict[str, Any], output: Path, code: int) -> int:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(audit, indent=2, default=str), encoding="utf-8")
    print("-" * 78)
    print(f"VERDICT: {audit.get('verdict')}")
    print(f"Report : {output}")
    print("No credentials were printed. No database was modified. No orders were placed.")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
