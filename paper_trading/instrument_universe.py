"""Initial paper-trading instrument universe and expiry-series policy.

The universe describes supported underlyings, not broker contract symbols.
Actual option symbols, strikes, lot sizes, tick sizes and listed expiry dates
must always come from the broker's current contract master. No order API is used.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ExpirySeries(str, Enum):
    WEEKLY_AND_MONTHLY = "WEEKLY_AND_MONTHLY"
    MONTHLY_ONLY = "MONTHLY_ONLY"


@dataclass(frozen=True)
class UnderlyingSpec:
    key: str
    display_name: str
    exchange: str
    broker_underlying_candidates: tuple[str, ...]
    expiry_series: ExpirySeries
    enabled: bool = True


# These aliases are discovery hints only. The contract master remains the
# authority for the actual broker symbol and listed expiry dates.
_INITIAL_UNIVERSE: tuple[UnderlyingSpec, ...] = (
    UnderlyingSpec(
        key="NIFTY50",
        display_name="Nifty 50",
        exchange="NSE",
        broker_underlying_candidates=("NIFTY", "NIFTY50"),
        expiry_series=ExpirySeries.WEEKLY_AND_MONTHLY,
    ),
    UnderlyingSpec(
        key="SENSEX",
        display_name="BSE Sensex",
        exchange="BSE",
        broker_underlying_candidates=("SENSEX",),
        expiry_series=ExpirySeries.WEEKLY_AND_MONTHLY,
    ),
    UnderlyingSpec(
        key="BANKNIFTY",
        display_name="Nifty Bank",
        exchange="NSE",
        broker_underlying_candidates=("BANKNIFTY", "NIFTYBANK"),
        expiry_series=ExpirySeries.MONTHLY_ONLY,
    ),
)

UNIVERSE_BY_KEY: dict[str, UnderlyingSpec] = {
    spec.key: spec for spec in _INITIAL_UNIVERSE
}


def get_underlying(key: str) -> UnderlyingSpec:
    """Return one enabled configured underlying, case-insensitively."""
    normalized = str(key).strip().upper()
    try:
        spec = UNIVERSE_BY_KEY[normalized]
    except KeyError as exc:
        raise ValueError(f"Unsupported paper-trading underlying: {key!r}") from exc
    if not spec.enabled:
        raise ValueError(f"Paper-trading underlying is disabled: {normalized}")
    return spec


def is_expiry_series_allowed(underlying: str, series: str | ExpirySeries) -> bool:
    """Validate a proposed series policy; never calculate or invent expiry dates.

    Callers should first identify the series from broker/exchange contract data.
    """
    spec = get_underlying(underlying)
    try:
        normalized_series = series if isinstance(series, ExpirySeries) else ExpirySeries(str(series).strip().upper())
    except ValueError:
        return False
    if spec.expiry_series is ExpirySeries.MONTHLY_ONLY:
        return normalized_series is ExpirySeries.MONTHLY_ONLY
    return normalized_series in (ExpirySeries.WEEKLY_AND_MONTHLY, ExpirySeries.MONTHLY_ONLY)


def list_enabled_underlyings() -> tuple[UnderlyingSpec, ...]:
    """Return configured underlyings in deterministic display order."""
    return tuple(spec for spec in _INITIAL_UNIVERSE if spec.enabled)


__all__ = [
    "ExpirySeries",
    "UnderlyingSpec",
    "UNIVERSE_BY_KEY",
    "get_underlying",
    "is_expiry_series_allowed",
    "list_enabled_underlyings",
]
