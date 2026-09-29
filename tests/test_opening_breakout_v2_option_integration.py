from dataclasses import dataclass

from backtest.opening_breakout_v2_option_integration import run_opening_breakout_trade
from backtest.opening_breakout_v2_signal_engine import OpeningBreakoutEvent
from execution.opening_breakout_v2_execution import V2ExecutionPolicy
from research.opening_breakout_1m_v2 import Candle, V2Config


@dataclass(frozen=True)
class Contract:
    instrument_id: int = 101
    symbol: str = "NSE:NIFTY26SEP25000CE"
    underlying: str = "NIFTY"
    expiry_date: object = None
    strike: int = 25000
    option_type: str = "CE"


class FakeResolver:
    def resolve(self, *, underlying_price, entry_date, direction):
        assert underlying_price == 25010
        assert direction == "LONG"
        return Contract()


def test_integration_reaches_resolver_before_data_access():
    event = OpeningBreakoutEvent(
        symbol="candidate",
        option_type="CE",
        strike=25000,
        lot_size=65,
        direction="LONG",
        instrument="CALL",
        setup_timestamp=100,
        trigger_timestamp=120,
        breakout_price=101.0,
        trigger_reasons=("CANDLE_HIGH",),
    )
    underlying = [Candle(100, 25000, 25015, 24990, 25010)]
    called = []

    def loader(instrument_id, start, end):
        called.append((instrument_id, start, end))
        return [
            Candle(100, 100, 102, 99, 101),
            Candle(120, 102, 103, 101, 102),
            Candle(121, 103, 105, 102, 104),
            Candle(122, 104, 125, 103, 124),
        ]

    # The current Resolver V2 interface intentionally does not expose lot size.
    # This test asserts the integration boundary without inventing metadata.
    try:
        run_opening_breakout_trade(
            event=event,
            underlying_candles=underlying,
            resolver=FakeResolver(),
            option_loader=loader,
            config=V2Config(custom_sl_points=2.0, tp_mode="CUSTOM_POINTS", custom_tp_points=4.0),
            execution_policy=V2ExecutionPolicy(entry_buffer_points=1.0),
            capital=100000,
        )
    except NotImplementedError as exc:
        assert "lot size" in str(exc)
    else:
        raise AssertionError("lot-size metadata must not be invented")

    assert called and called[0][0] == 101
