"""Read-only Dhan NIFTY option-chain diagnostic.

This script first calls the official SDK expiry endpoint. If that endpoint
returns a failure, it makes the same HTTP request directly so the raw HTTP
status/body can be inspected. No credentials are printed and no order API
is called.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from broker.dhan import DhanClient, DhanClientConfig


NIFTY_SECURITY_ID = 13
NIFTY_UNDERLYING_SEGMENT = "IDX_I"
DHAN_API_BASE = "https://api.dhan.co/v2"


def raw_expiry_request(client_id: str, access_token: str) -> tuple[int, str]:
    response = requests.post(
        f"{DHAN_API_BASE}/optionchain/expirylist",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "access-token": access_token,
            "client-id": client_id,
        },
        json={
            "UnderlyingScrip": NIFTY_SECURITY_ID,
            "UnderlyingSeg": NIFTY_UNDERLYING_SEGMENT,
        },
        timeout=20,
    )
    return response.status_code, response.text


def main() -> int:
    config = DhanClientConfig.from_env()
    client = DhanClient(
        DhanClientConfig(
            client_id=config.client_id,
            access_token=config.access_token,
            enable_live_orders=False,
        )
    ).connect()

    sdk_response = client.expiry_list(
        under_security_id=NIFTY_SECURITY_ID,
        under_exchange_segment=NIFTY_UNDERLYING_SEGMENT,
    )

    print("=" * 80)
    print("KUNAL QUANT — DHAN NIFTY OPTION CHAIN DIAGNOSTIC")
    print("=" * 80)
    print(f"NIFTY security ID : {NIFTY_SECURITY_ID}")
    print(f"Underlying segment: {NIFTY_UNDERLYING_SEGMENT}")
    print("Live orders       : DISABLED")
    print(f"SDK response      : {sdk_response}")

    if sdk_response.get("status") == "success":
        expiries = sdk_response.get("data") or []
        print(f"Expiry count      : {len(expiries)}")
        print(f"Nearest expiry    : {expiries[0] if expiries else 'NONE'}")
        return 0 if expiries else 1

    print()
    print("SDK expiry_list failed. Calling the same Dhan endpoint directly...")
    status_code, raw_body = raw_expiry_request(
        config.client_id,
        config.access_token,
    )
    print(f"HTTP status       : {status_code}")
    print("Raw response body :")
    print(raw_body)

    try:
        parsed = json.loads(raw_body)
        print("Parsed response   :")
        print(json.dumps(parsed, indent=2))
    except json.JSONDecodeError:
        print("Raw body is not JSON.")

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
