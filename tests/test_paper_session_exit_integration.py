import csv

from backtest.option_trade_lifecycle import OptionExitReason, OptionTradeDirection
from market_data.resampling import Candle
from paper_trading.buyer_lifecycle import BuyerLifecycleConfig, BuyerOptionTradeLifecycle
from paper_trading.engine import PaperStrategyId, PaperTradingEngine
from paper_trading.recorder import PaperTradeRecorder
from paper_trading.session import process_completed_option_candle


def test_completed_option_candles_drive_buyer_stop_once_and_skip_entry_bucket(tmp_path):
    recorder = PaperTradeRecorder(tmp_path)
    engine = PaperTradingEngine(
        recorder=recorder,
        lifecycle=BuyerOptionTradeLifecycle(
            BuyerLifecycleConfig(allocation=15000, lot_size=25, stop_loss_pct=0.20)
        ),
    )
    trade = engine.open_position(
        strategy_id=PaperStrategyId.STRATEGY_A,
        direction=OptionTradeDirection.LONG,
        symbol="NSE:NIFTY2610025000CE",
        entry_price=100.0,
        timestamp=10_000,
    )
    assert trade is not None

    # This candle began before the entry timestamp; its low cannot stop the trade.
    pre_entry_bucket = Candle(
        timestamp=9_960, open=100, high=102, low=79, close=81,
        volume=None, open_interest=None,
    )
    process_completed_option_candle(
        engine, symbol=trade.position.symbol, candle=pre_entry_bucket
    )
    assert not trade.closed
    assert trade.exits == []

    # A later completed candle touches the stop and closes the bought premium.
    stop_candle = Candle(
        timestamp=10_020, open=100, high=101, low=79, close=82,
        volume=None, open_interest=None,
    )
    process_completed_option_candle(
        engine, symbol=trade.position.symbol, candle=stop_candle
    )
    assert trade.closed
    assert len(trade.exits) == 1
    assert trade.exits[0].reason == OptionExitReason.STOP_LOSS

    # A repeated candle after closure must not append a duplicate exit event.
    process_completed_option_candle(
        engine, symbol=trade.position.symbol, candle=stop_candle
    )
    with recorder.trades_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert [row["event_type"] for row in rows] == ["ENTRY", "EXIT"]
