"""Read-only DhanHQ connectivity check.

Required environment:
    DHAN_CLIENT_ID
    DHAN_ACCESS_TOKEN

This script never places an order.
"""

from __future__ import annotations

from broker.dhan import DhanClient, DhanClientConfig


def main() -> int:
    config = DhanClientConfig.from_env()

    read_only_config = DhanClientConfig(
        client_id=config.client_id,
        access_token=config.access_token,
        enable_live_orders=False,
    )

    client = DhanClient(read_only_config).connect()
    response = client.get_fund_limits()

    print("=" * 72)
    print("KUNAL QUANT — DHAN READ-ONLY CONNECTION CHECK")
    print("=" * 72)
    print("Connection : OK")
    print("Live orders: DISABLED")
    print("Fund limits:")
    print(response)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
