from __future__ import annotations

import sys
import types

import pytest

from broker.dhan import DhanClient, DhanClientConfig


def test_live_orders_are_disabled_by_default() -> None:
    config = DhanClientConfig("client", "token")
    client = DhanClient(config)

    with pytest.raises(RuntimeError, match="Live Dhan orders are disabled"):
        client.place_order(
            security_id="123",
            exchange_segment="NSE_FNO",
            transaction_type="BUY",
            quantity=65,
        )


def test_client_connects_without_live_order() -> None:
    calls: list[str] = []

    class FakeContext:
        def __init__(self, client_id: str, access_token: str) -> None:
            calls.append("context")

    class FakeDhan:
        def __init__(self, context: FakeContext) -> None:
            calls.append("client")

        def get_fund_limits(self):
            calls.append("funds")
            return {"status": "success"}

    fake_module = types.SimpleNamespace(
        DhanContext=FakeContext,
        dhanhq=FakeDhan,
    )

    original = sys.modules.get("dhanhq")
    sys.modules["dhanhq"] = fake_module

    try:
        client = DhanClient(DhanClientConfig("client", "token")).connect()
        assert client.get_fund_limits() == {"status": "success"}
        assert calls == ["context", "client", "funds"]
    finally:
        if original is None:
            sys.modules.pop("dhanhq", None)
        else:
            sys.modules["dhanhq"] = original


def test_expiry_list_is_forwarded() -> None:
    calls: list[tuple[str, object]] = []

    class FakeDhan:
        def expiry_list(self, **kwargs):
            calls.append(("expiry_list", kwargs))
            return {"status": "success", "data": ["2026-10-13"]}

    client = DhanClient(DhanClientConfig("client", "token"))
    client._dhan = FakeDhan()

    assert client.expiry_list(
        under_security_id=13,
        under_exchange_segment="IDX_I",
    ) == {"status": "success", "data": ["2026-10-13"]}

    assert calls == [
        (
            "expiry_list",
            {
                "under_security_id": 13,
                "under_exchange_segment": "IDX_I",
            },
        )
    ]
