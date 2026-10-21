import json

import pytest

from backtest.option_trade_lifecycle import OptionTradeDirection
from paper_trading.buyer_lifecycle import BuyerLifecycleConfig, BuyerOptionTradeLifecycle
from paper_trading.durable_engine import DurablePaperTradingEngine, PaperStateRecoveryError
from paper_trading.engine import PaperStrategyId
from paper_trading.recorder import PaperTradeRecorder


def _engine(tmp_path):
    recorder = PaperTradeRecorder(tmp_path)
    return DurablePaperTradingEngine(
        recorder=recorder,
        lifecycle=BuyerOptionTradeLifecycle(
            BuyerLifecycleConfig(
                allocation=15_000,
                lot_size=25,
                stop_loss_pct=0.20,
                target_rr=3,
            )
        ),
        starting_capital=100_000,
        allocation_pct=20,
    )


def test_restart_restores_open_trade_manual_stop_and_candle_watermark(tmp_path):
    engine = _engine(tmp_path)
    trade = engine.open_position(
        strategy_id=PaperStrategyId.STRATEGY_A,
        direction=OptionTradeDirection.LONG,
        symbol="NSE:NIFTYCE",
        entry_price=100,
        timestamp=100,
    )
    assert trade is not None
    engine.update_manual_stop(
        strategy_id=PaperStrategyId.STRATEGY_A,
        stop_loss=75,
        allow_loosen=True,
    )
    engine.process_option_candle(
        strategy_id=PaperStrategyId.STRATEGY_A,
        timestamp=120,
        option_open=95,
        option_high=99,
        option_low=90,
        option_close=94,
        underlying_close=None,
        kama_value=None,
    )

    restarted = _engine(tmp_path)
    restarted.restore_state()
    restored = restarted.open_trade(PaperStrategyId.STRATEGY_A)
    assert restored is not None
    assert restored.position.stop_loss == 75
    assert restored.last_processed_timestamp == 120
    assert restored.position.remaining_quantity == trade.position.remaining_quantity
    assert restarted.available_cash() == engine.available_cash()


def test_restart_restores_closed_trade_without_reopening_it(tmp_path):
    engine = _engine(tmp_path)
    engine.open_position(
        strategy_id=PaperStrategyId.STRATEGY_A,
        direction=OptionTradeDirection.LONG,
        symbol="NSE:NIFTYCE",
        entry_price=100,
        timestamp=100,
    )
    engine.force_exit_position(
        strategy_id=PaperStrategyId.STRATEGY_A,
        timestamp=200,
        fresh_option_price=110,
    )

    restarted = _engine(tmp_path)
    restarted.restore_state()
    assert restarted.open_trade(PaperStrategyId.STRATEGY_A) is None
    assert len(restarted.trades(PaperStrategyId.STRATEGY_A)) == 1
    assert restarted.trades(PaperStrategyId.STRATEGY_A)[0].closed
    assert restarted.available_cash() == engine.available_cash()


def test_corrupt_snapshot_fails_closed(tmp_path):
    engine = _engine(tmp_path)
    engine.open_position(
        strategy_id=PaperStrategyId.STRATEGY_A,
        direction=OptionTradeDirection.LONG,
        symbol="NSE:NIFTYCE",
        entry_price=100,
        timestamp=100,
    )
    (tmp_path / "paper_state.json").write_text("{broken", encoding="utf-8")

    restarted = _engine(tmp_path)
    with pytest.raises(PaperStateRecoveryError):
        restarted.restore_state()
    assert restarted.all_trades() == ()
