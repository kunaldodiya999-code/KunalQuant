from datetime import date

from backtest.broker_cost_model import (
    calculate_options_trade_costs,
    fyers_options_profile,
)


def test_pre_2026_stt_regime():
    assert fyers_options_profile(date(2025, 10, 15)).stt_sell_rate == 0.0010


def test_april_2026_stt_regime():
    assert fyers_options_profile(date(2026, 4, 1)).stt_sell_rate == 0.0015


def test_options_cost_breakdown():
    result = calculate_options_trade_costs(
        entry_price=173.25,
        exit_price=151.25,
        quantity=65,
        profile=fyers_options_profile(date(2025, 10, 15)),
        gross_pnl=-1430.0,
    )

    assert result.buy_turnover == 11261.25
    assert result.sell_turnover == 9831.25
    assert result.brokerage == 40.0
    assert result.stt == 98.3125
    assert result.total_cost > result.brokerage
    assert result.net_pnl < -1430.0
