from __future__ import annotations

import pytest

from paper_trading.instrument_universe import (
    ExpirySeries,
    get_underlying,
    is_expiry_series_allowed,
    list_enabled_underlyings,
)


def test_initial_universe_contains_only_requested_indices():
    assert [item.key for item in list_enabled_underlyings()] == [
        "NIFTY50", "SENSEX", "BANKNIFTY"
    ]


def test_banknifty_is_monthly_only():
    spec = get_underlying("banknifty")
    assert spec.expiry_series is ExpirySeries.MONTHLY_ONLY
    assert is_expiry_series_allowed("BANKNIFTY", ExpirySeries.MONTHLY_ONLY)
    assert not is_expiry_series_allowed("BANKNIFTY", ExpirySeries.WEEKLY_AND_MONTHLY)


@pytest.mark.parametrize("underlying", ["NIFTY50", "SENSEX"])
def test_nifty_and_sensex_allow_weekly_monthly_contract_families(underlying):
    assert is_expiry_series_allowed(underlying, ExpirySeries.WEEKLY_AND_MONTHLY)
    assert is_expiry_series_allowed(underlying, ExpirySeries.MONTHLY_ONLY)


def test_unknown_underlying_fails_closed():
    with pytest.raises(ValueError, match="Unsupported"):
        get_underlying("GOLD")


def test_unknown_series_is_rejected():
    assert not is_expiry_series_allowed("BANKNIFTY", "WEEKLY")
