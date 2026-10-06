"""Thin KunalQuant wrapper around the official DhanHQ Python SDK.

No strategy, option-selection, risk, or automatic live-trading logic lives
here. Live order placement is disabled unless explicitly enabled.
"""

from __future__ import annotations

from typing import Any

from .config import DhanClientConfig


class DhanClient:
    """Broker-specific DhanHQ API boundary."""

    def __init__(self, config: DhanClientConfig) -> None:
        self.config = config
        self._dhan: Any | None = None

    def connect(self) -> "DhanClient":
        try:
            from dhanhq import DhanContext, dhanhq
        except ImportError as exc:
            raise RuntimeError(
                "DhanHQ SDK is not installed. Install requirements-dhan.txt."
            ) from exc

        context = DhanContext(
            self.config.client_id,
            self.config.access_token,
        )
        self._dhan = dhanhq(context)
        return self

    @property
    def raw(self) -> Any:
        if self._dhan is None:
            raise RuntimeError("DhanClient is not connected.")
        return self._dhan

    def get_fund_limits(self) -> Any:
        return self.raw.get_fund_limits()

    def get_positions(self) -> Any:
        return self.raw.get_positions()

    def get_order_list(self) -> Any:
        return self.raw.get_order_list()

    def get_trade_book(self, order_id: str | None = None) -> Any:
        if order_id is None:
            return self.raw.get_trade_book()
        return self.raw.get_trade_book(order_id)

    def option_chain(
        self,
        *,
        under_security_id: int | str,
        under_exchange_segment: str,
        expiry: str,
    ) -> Any:
        return self.raw.option_chain(
            under_security_id=under_security_id,
            under_exchange_segment=under_exchange_segment,
            expiry=expiry,
        )

    def place_order(self, **kwargs: Any) -> Any:
        """Place a live Dhan order only after explicit enablement."""

        if not self.config.enable_live_orders:
            raise RuntimeError(
                "Live Dhan orders are disabled. "
                "Set DHAN_ENABLE_LIVE_ORDERS=true only after paper validation."
            )

        return self.raw.place_order(**kwargs)
