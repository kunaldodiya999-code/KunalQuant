import csv

import pytest

from paper_trading.buyer_lifecycle import BuyerLifecycleConfig, BuyerOptionTradeLifecycle
from paper_trading.durable_engine import DurablePaperTradingEngine, PaperStateRecoveryError
from paper_trading.engine import PaperStrategyId
from paper_trading.recorder import PaperTradeRecorder


def _engine(tmp_path):
    recorder = PaperTradeRecorder(tmp_path / "journal")
    engine = DurablePaperTradingEngine(
        lifecycle=BuyerOptionTradeLifecycle(
            BuyerLifecycleConfig(allocation=20_000, lot_size=25)
        ),
        starting_capital=100_000,
        allocation_pct=20,
        recorder=recorder,
        state_path=tmp_path / "paper_state.json",
    )
    return engine, recorder


def test_open_position_recovers_once_and_preserves_available_cash(tmp_path):
    engine, recorder = _engine(tmp_path)
    opened = engine.open_position(
        strategy_id=PaperStrategyId.STRATEGY_A,
        direction="LONG",
        symbol="NSE:NIFTY26CE",
        entry_price=100,
        timestamp=1_800_000_000,
    )
    assert opened is not None
    assert engine.available_cash() == pytest.approx(80_000)

    restarted = DurablePaperTradingEngine(
        lifecycle=BuyerOptionTradeLifecycle(
            BuyerLifecycleConfig(allocation=20_000, lot_size=25)
        ),
        starting_capital=100_000,
        allocation_pct=20,
        recorder=recorder,
        state_path=tmp_path / "paper_state.json",
    )
    restarted.restore_state()

    trades = restarted.all_trades()
    assert len(trades) == 1
    restored = restarted.open_trade(PaperStrategyId.STRATEGY_A)
    assert restored is not None
    assert restored.position.symbol == "NSE:NIFTY26CE"
    assert restored.position.entry_price == 100
    assert restored.position.stop_loss == opened.position.stop_loss
    assert restored.position.remaining_quantity == opened.position.remaining_quantity
    assert restored.position.remaining_lots == opened.position.remaining_lots
    assert restarted.available_cash() == pytest.approx(80_000)

    # Restoring is read-only: it must not append a duplicate ENTRY event.
    with recorder.trades_path.open(newline="", encoding="utf-8") as handle:
        events = list(csv.DictReader(handle))
    assert sum(1 for event in events if event["event_type"] == "ENTRY") == 1


def test_corrupt_snapshot_fails_closed(tmp_path):
    engine, _ = _engine(tmp_path)
    engine.open_position(
        strategy_id=PaperStrategyId.STRATEGY_A,
        direction="LONG",
        symbol="NSE:NIFTY26CE",
        entry_price=100,
        timestamp=1_800_000_000,
    )
    engine.state_path.write_text("{not-json", encoding="utf-8")

    restarted, _ = _engine(tmp_path)
    with pytest.raises(PaperStateRecoveryError, match="Could not safely restore"):
        restarted.restore_state()
    assert restarted.all_trades() == ()


def test_journal_without_snapshot_fails_closed(tmp_path):
    engine, _ = _engine(tmp_path)
    engine.open_position(
        strategy_id=PaperStrategyId.STRATEGY_A,
        direction="LONG",
        symbol="NSE:NIFTY26CE",
        entry_price=100,
        timestamp=1_800_000_000,
    )
    engine.state_path.unlink()

    restarted, _ = _engine(tmp_path)
    with pytest.raises(PaperStateRecoveryError, match="snapshot is missing"):
        restarted.restore_state()
    assert restarted.all_trades() == ()


def test_snapshot_capital_mismatch_fails_closed(tmp_path):
    engine, recorder = _engine(tmp_path)
    engine.open_position(
        strategy_id=PaperStrategyId.STRATEGY_A,
        direction="LONG",
        symbol="NSE:NIFTY26CE",
        entry_price=100,
        timestamp=1_800_000_000,
    )
    restarted = DurablePaperTradingEngine(
        lifecycle=BuyerOptionTradeLifecycle(
            BuyerLifecycleConfig(allocation=20_000, lot_size=25)
        ),
        starting_capital=120_000,
        allocation_pct=20,
        recorder=recorder,
        state_path=tmp_path / "paper_state.json",
    )
    with pytest.raises(PaperStateRecoveryError, match="capital/allocation"):
        restarted.restore_state()
