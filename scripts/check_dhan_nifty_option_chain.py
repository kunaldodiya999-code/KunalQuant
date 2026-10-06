"""Read-only Dhan NIFTY option-chain verification.

This script:
1. fetches active NIFTY option expiries,
2. selects the nearest returned expiry,
3. fetches the corresponding option chain,
4. prints representative CE/PE contract security IDs.

It never places an order.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from broker.dhan import DhanClient, DhanClientConfig


NIFTY_SECURITY_ID = 13
NIFTY_UNDERLYING_SEGMENT = "IDX_I"


def main() -> int:
    config = DhanClientConfig.from_env()
    read_only_config = DhanClientConfig(
        client_id=config.client_id,
        access_token=config.access_token,
        enable_live_orders=False,
    )

    client = DhanClient(read_only_config).connect()

    expiry_response = client.expiry_list(
        under_security_id=NIFTY_SECURITY_ID,
        under_exchange_segment=NIFTY_UNDERLYING_SEGMENT,
    )

    if expiry_response.get("status") != "success":
        print("Expiry list failed:")
        print(expiry_response)
        return 1

    expiries = expiry_response.get("data") or []
    if not expiries:
        print("No active NIFTY option expiries returned.")
        return 1

    nearest_expiry = expiries[0]

    # Dhan documents a 1 unique option-chain request / 3 seconds limit.
    time.sleep(3.1)

    chain_response = client.option_chain(
        under_security_id=NIFTY_SECURITY_ID,
        under_exchange_segment=NIFTY_UNDERLYING_SEGMENT,
        expiry=nearest_expiry,
    )

    if chain_response.get("status") != "success":
        print("Option chain failed:")
        print(chain_response)
        return 1

    data = chain_response.get("data") or {}
    spot = data.get("last_price")
    option_chain = data.get("oc") or {}

    print("=" * 80)
    print("KUNAL QUANT — DHAN NIFTY OPTION CHAIN CHECK")
    print("=" * 80)
    print(f"Underlying security ID : {NIFTY_SECURITY_ID}")
    print(f"Underlying segment     : {NIFTY_UNDERLYING_SEGMENT}")
    print(f"Nearest expiry        : {nearest_expiry}")
    print(f"NIFTY spot             : {spot}")
    print(f"Strike count           : {len(option_chain)}")

    if option_chain:
        first_strike = sorted(option_chain, key=float)[0]
        row = option_chain[first_strike]
        ce = row.get("ce") or {}
        pe = row.get("pe") or {}

        print(f"Sample strike          : {first_strike}")
        print(f"CE security ID         : {ce.get('security_id')}")
        print(f"CE LTP                 : {ce.get('last_price')}")
        print(f"PE security ID         : {pe.get('security_id')}")
        print(f"PE LTP                 : {pe.get('last_price')}")

    print("Live orders            : DISABLED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
