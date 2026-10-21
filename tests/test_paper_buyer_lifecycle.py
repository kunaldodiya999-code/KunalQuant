import unittest

from backtest.option_trade_lifecycle import OptionExitReason, OptionTradeDirection
from paper_trading.buyer_lifecycle import BuyerLifecycleConfig, BuyerOptionTradeLifecycle


class BuyerOptionTradeLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.lifecycle = BuyerOptionTradeLifecycle(
            BuyerLifecycleConfig(allocation=15000, lot_size=25, stop_loss_pct=.20, target_rr=3)
        )

    def test_short_signal_is_bought_pe_with_long_premium_stop_target_and_pnl(self):
        p = self.lifecycle.create_position(
            strategy_id="KTMI_LONG_SHORT_SPEED", direction=OptionTradeDirection.SHORT,
            symbol="NSE:NIFTY2610025000PE", entry_price=100,
        )
        self.assertEqual(p.stop_loss, 80)
        self.assertEqual(p.target, 160)
        self.assertEqual(p.quantity, 150)
        exits = self.lifecycle.process_candle(
            position=p, timestamp=200, option_high=105, option_low=79,
            option_close=82, underlying_close=25000, kama_value=25100,
        )
        self.assertEqual(exits[0].reason, OptionExitReason.STOP_LOSS)
        self.assertEqual(exits[0].pnl, -3000)

    def test_target_partially_exits_bought_ce_and_leaves_lot(self):
        p = self.lifecycle.create_position(
            strategy_id="A", direction=OptionTradeDirection.LONG,
            symbol="NSE:NIFTY2610025000CE", entry_price=100,
        )
        exits = self.lifecycle.process_candle(
            position=p, timestamp=200, option_high=161, option_low=99,
            option_close=158, underlying_close=25000, kama_value=24900,
        )
        self.assertEqual(exits[0].reason, OptionExitReason.TARGET_3R)
        self.assertEqual(exits[0].price, 160)
        self.assertEqual(p.remaining_lots, 3)
        self.assertFalse(p.closed)

    def test_kama_exit_uses_underlying_direction_but_premium_pnl(self):
        p = self.lifecycle.create_position(
            strategy_id="B", direction=OptionTradeDirection.SHORT,
            symbol="NSE:NIFTY2610025000PE", entry_price=100,
        )
        exits = self.lifecycle.process_candle(
            position=p, timestamp=200, option_high=110, option_low=101,
            option_close=108, underlying_close=25200, kama_value=25100,
        )
        self.assertEqual(exits[0].reason, OptionExitReason.KAMA_EXIT)
        self.assertEqual(exits[0].pnl, 8 * p.quantity)

    def test_stop_wins_when_stop_and_target_both_touched(self):
        p = self.lifecycle.create_position(
            strategy_id="A", direction=OptionTradeDirection.LONG,
            symbol="NSE:NIFTY2610025000CE", entry_price=100,
        )
        exits = self.lifecycle.process_candle(
            position=p, timestamp=200, option_high=170, option_low=79,
            option_close=120, underlying_close=25000, kama_value=24900,
        )
        self.assertEqual(len(exits), 1)
        self.assertEqual(exits[0].reason, OptionExitReason.STOP_LOSS)

    def test_rejects_unaffordable_lot_and_bad_prices(self):
        with self.assertRaises(ValueError):
            self.lifecycle.create_position(
                strategy_id="A", direction=OptionTradeDirection.LONG,
                symbol="CE", entry_price=1000,
            )
        with self.assertRaises(ValueError):
            self.lifecycle.create_position(
                strategy_id="A", direction=OptionTradeDirection.LONG,
                symbol="CE", entry_price=float("nan"),
            )


if __name__ == "__main__":
    unittest.main()


def test_single_lot_position_closes_fully_when_target_is_hit():
    lifecycle = BuyerOptionTradeLifecycle(
        BuyerLifecycleConfig(
            allocation=12_500, lot_size=25, stop_loss_pct=0.20, target_rr=3
        )
    )
    position = lifecycle.create_position(
        strategy_id="A",
        direction=OptionTradeDirection.LONG,
        symbol="NSE:NIFTY2610025000CE",
        entry_price=500,
    )
    assert position.lots == 1
    assert position.target == 800

    exits = lifecycle.process_candle(
        position=position,
        timestamp=300,
        option_high=805,
        option_low=501,
        option_close=790,
        underlying_close=None,
        kama_value=None,
    )

    assert len(exits) == 1
    assert exits[0].reason == OptionExitReason.TARGET_3R
    assert exits[0].price == 800
    assert exits[0].quantity == 25
    assert exits[0].lots == 1
    assert exits[0].remaining_quantity == 0
    assert position.closed
    assert position.gross_pnl == 7_500


def test_gap_through_stop_fills_at_open_not_unreachable_stop():
    lifecycle = BuyerOptionTradeLifecycle(
        BuyerLifecycleConfig(
            allocation=15_000, lot_size=25, stop_loss_pct=0.20, target_rr=2
        )
    )
    position = lifecycle.create_position(
        strategy_id="A",
        direction=OptionTradeDirection.LONG,
        symbol="NSE:NIFTY2610025000CE",
        entry_price=100,
    )
    exits = lifecycle.process_candle_with_open(
        position=position,
        timestamp=400,
        option_open=70,
        option_high=75,
        option_low=65,
        option_close=68,
        underlying_close=None,
        kama_value=None,
    )
    assert len(exits) == 1
    assert exits[0].reason == OptionExitReason.STOP_LOSS
    assert exits[0].price == 70
    assert exits[0].pnl == (70 - 100) * position.quantity


def test_intrabar_stop_touch_without_gap_keeps_stop_price_fill():
    lifecycle = BuyerOptionTradeLifecycle(
        BuyerLifecycleConfig(
            allocation=15_000, lot_size=25, stop_loss_pct=0.20, target_rr=2
        )
    )
    position = lifecycle.create_position(
        strategy_id="A",
        direction=OptionTradeDirection.LONG,
        symbol="NSE:NIFTY2610025000CE",
        entry_price=100,
    )
    exits = lifecycle.process_candle_with_open(
        position=position,
        timestamp=500,
        option_open=95,
        option_high=98,
        option_low=75,
        option_close=82,
        underlying_close=None,
        kama_value=None,
    )
    assert len(exits) == 1
    assert exits[0].price == 80
