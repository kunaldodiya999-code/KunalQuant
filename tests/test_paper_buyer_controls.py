from backtest.option_trade_lifecycle import OptionExitReason, OptionTradeDirection
from paper_trading.buyer_lifecycle import BuyerLifecycleConfig, BuyerOptionTradeLifecycle


def _position(mode="close_all", fraction=.5, allocation=20_000):
    lifecycle = BuyerOptionTradeLifecycle(BuyerLifecycleConfig(
        allocation=allocation, lot_size=25, stop_loss_pct=.30, target_rr=2,
        partial_exit_fraction=fraction, single_lot_partial_mode=mode,
    ))
    position = lifecycle.create_position(
        strategy_id="A", direction=OptionTradeDirection.LONG,
        symbol="NSE:NIFTYCE", entry_price=100,
    )
    return lifecycle, position


def test_approved_30_percent_stop_and_2r_trigger():
    _, position = _position()
    assert position.stop_loss == 70
    assert position.target == 160


def test_partial_exit_fraction_is_applied_to_lots():
    lifecycle, position = _position(fraction=.5)
    assert position.lots == 8
    exits = lifecycle.process_candle(
        position=position, timestamp=200, option_high=161, option_low=100,
        option_close=158, underlying_close=None, kama_value=None,
    )
    assert len(exits) == 1
    assert exits[0].reason == OptionExitReason.TARGET_3R
    assert exits[0].lots == 4
    assert exits[0].remaining_lots == 4
    assert position.partial_exit_done is True
    assert position.closed is False


def test_one_lot_policy_can_close_all_or_skip():
    lifecycle, position = _position(allocation=2_500, mode="close_all")
    assert position.lots == 1
    exits = lifecycle.process_candle(
        position=position, timestamp=200, option_high=161, option_low=100,
        option_close=158, underlying_close=None, kama_value=None,
    )
    assert len(exits) == 1 and exits[0].lots == 1 and position.closed

    lifecycle, position = _position(allocation=2_500, mode="skip")
    exits = lifecycle.process_candle(
        position=position, timestamp=200, option_high=161, option_low=100,
        option_close=158, underlying_close=None, kama_value=None,
    )
    assert exits == []
    assert position.closed is False


def test_partial_exit_can_be_disabled_without_disabling_stop_loss():
    lifecycle = BuyerOptionTradeLifecycle(BuyerLifecycleConfig(
        allocation=20_000, lot_size=25, stop_loss_pct=.30, target_rr=2,
        partial_exit_enabled=False,
    ))
    position = lifecycle.create_position(
        strategy_id="A", direction=OptionTradeDirection.LONG,
        symbol="NSE:NIFTYCE", entry_price=100,
    )
    target_events = lifecycle.process_candle(
        position=position, timestamp=200, option_high=161, option_low=100,
        option_close=158, underlying_close=None, kama_value=None,
    )
    assert target_events == []
    stop_events = lifecycle.process_candle(
        position=position, timestamp=260, option_high=100, option_low=69,
        option_close=72, underlying_close=None, kama_value=None,
    )
    assert len(stop_events) == 1
    assert stop_events[0].reason == OptionExitReason.STOP_LOSS
