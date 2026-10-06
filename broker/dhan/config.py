"""Configuration for the DhanHQ adapter.

Credentials are loaded from environment variables and are never stored in
source control.
"""

from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class DhanClientConfig:
    """Dhan credentials and live-order safety gate."""

    client_id: str
    access_token: str
    enable_live_orders: bool = False

    @classmethod
    def from_env(cls) -> "DhanClientConfig":
        client_id = os.getenv("DHAN_CLIENT_ID", "").strip()
        access_token = os.getenv("DHAN_ACCESS_TOKEN", "").strip()

        if not client_id:
            raise ValueError("DHAN_CLIENT_ID is not set.")

        if not access_token:
            raise ValueError("DHAN_ACCESS_TOKEN is not set.")

        enabled = os.getenv("DHAN_ENABLE_LIVE_ORDERS", "false").strip().lower()

        return cls(
            client_id=client_id,
            access_token=access_token,
            enable_live_orders=enabled in {"1", "true", "yes", "on"},
        )
