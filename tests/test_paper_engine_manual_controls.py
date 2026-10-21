import pytest

from backtest.option_trade_lifecycle import OptionExitReason
from paper_trading.engine import PaperStrategyId, PaperTradingEngine


def _engine_with_position():
    engine = PaperTradingEngine()
    trade = engine.open_position(
        strategy_id=PaperStrategyId.STRATEGY_A, direction="LONG",
        symbol="NSE:NIFTYCE", entry_price=100, timestamp=100,
    )
    assert trade is not None
    return engine, trade


def test_manual_stop_can_tighten_or_loosen_when_allowed():
    engine, trade = _engine_with_position()
    engine.update_manual_stop(strategy_id=PaperStrategyId.STRATEGY_A, stop_loss=85)
    assert trade.position.stop_loss == 85
    engine.update_manual_stop(
        strategy_id=PaperStrategyId.STRATEGY_A, stop_loss=65, allow_loosen=True
    )
    assert trade.position.stop_loss == 65
    with pytest.raises(ValueError, match="Loosening"):
        engine.update_manual_stop(
            strategy_id=PaperStrategyId.STRATEGY_A, stop_loss=60, allow_loosen=False
        )


def test_manual_stop_rejects_entry_or_higher_and_invalid_values():
    engine, _ = _engine_with_position()
    for value in (0, -1, 100, 101, float("nan")):
        with pytest.raises(ValueError):
            engine.update_manual_stop(
                strategy_id=PaperStrategyId.STRATEGY_A, stop_loss=value
            )


def test_forced_exit_requires_valid_positive_price_and_closes_paper_only():
    engine, trade = _engine_with_position()
    with pytest.raises(ValueError):
        engine.force_exit_position(
            strategy_id=PaperStrategyId.STRATEGY_A, timestamp=200,
            fresh_option_price=0,
        )
    event = engine.force_exit_position(
        strategy_id=PaperStrategyId.STRATEGY_A, timestamp=200,
        fresh_option_price=110,
    )
    assert event.reason == OptionExitReason.END_OF_DATA
    assert event.price == 110
    assert event.pnl == 10 * trade.position.quantity
    assert trade.closed
    assert engine.open_trade(PaperStrategyId.STRATEGY_A) is None
