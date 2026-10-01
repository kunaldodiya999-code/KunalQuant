from datetime import date
from types import SimpleNamespace

from scripts.audit_opening_breakout_v2_risk_decomposition import decompose_trade


def test_decomposition_separates_strategy_from_execution_and_costs():
    trade = SimpleNamespace(
        quantity=75,
        option_signal_price=100.0,
        entry=SimpleNamespace(price=101.0),
        stop_price=81.0,
        target_price=141.0,
        exit=SimpleNamespace(price=79.0, reason="STOP_LOSS"),
        gross_pnl=-1650.0,
        event=SimpleNamespace(direction="LONG", trigger_timestamp=1741000000),
    )

    row = decompose_trade(trade, entry_buffer=1.0, exit_buffer=2.0, intended_risk=2000.0)

    assert row["theoretical_strategy_pnl"] == -1575.0
    assert row["entry_execution_impact"] == -75.0
    assert row["exit_execution_impact"] == -150.0
    assert row["execution_adjusted_from_signal"] == -1800.0
    assert row["gross_pnl"] == -1650.0
    assert row["strategy_risk"] == 1500.0
    assert row["intended_risk"] == 2000.0
    assert row["realized_r"] == -1.1
