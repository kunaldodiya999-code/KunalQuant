"""Read-only FYERS expired-option API probe.

No database writes. Used to confirm the broker's historical contract-discovery
response shape before implementing targeted option acquisition.
"""
from __future__ import annotations

import json
from api.fyers_client import FyersClient


def main() -> None:
    client = FyersClient()

    print("=" * 90)
    print("KUNAL QUANT — FYERS EXPIRED OPTION API PROBE")
    print("=" * 90)
    print("READ-ONLY — no database changes")
    print()

    print("EXPIRY DATES")
    response = client.expired_expiry_dates(
        symbol="NIFTY",
        range_from="2026-08-01",
        range_to="2026-09-23",
    )
    print(json.dumps(response, indent=2, default=str))

    print()
    print("CONTRACTS FOR 2026-09-22")
    response = client.expired_contracts(
        symbol="NIFTY",
        expiry_date="2026-09-22",
    )
    print(json.dumps(response, indent=2, default=str))


if __name__ == "__main__":
    main()
