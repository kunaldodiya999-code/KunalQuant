"""Compatibility re-exports for the shared instrument universe module."""
from instrument_universe import (
    ExpirySeries,
    UnderlyingSpec,
    UNIVERSE_BY_KEY,
    get_underlying,
    is_expiry_series_allowed,
    list_enabled_underlyings,
)

__all__ = [
    "ExpirySeries",
    "UnderlyingSpec",
    "UNIVERSE_BY_KEY",
    "get_underlying",
    "is_expiry_series_allowed",
    "list_enabled_underlyings",
]
