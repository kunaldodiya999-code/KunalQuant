from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from backtest.option_trade_lifecycle import OptionTradeDirection
from paper_trading.buyer_lifecycle import BuyerLifecycleConfig, BuyerOptionTradeLifecycle
from paper_trading.engine import PaperStrategyId, PaperTradingEngine
from paper_trading.recorder import PaperTradeRecorder
from paper_trading.session import PaperSession


class _QuoteCache:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = 0

    def get_quote(self, *_args, **_kwargs):
        self.calls += 1
        if self.error:
            raise self.error
        return self.result


def _session(tmp_path, quote_cache):
    session = object.__new__(PaperSession)
    session.engine = PaperTradingEngine(
        recorder=PaperTradeRecorder(tmp_path),
        lifecycle=BuyerOptionTradeLifecycle(
            BuyerLifecycleConfig(allocation=15_000, lot_size=25, stop_loss_pct=0.2)
        ),
    )
    session.quote_cache = quote_cache
    session.control_service = None
    session.alerts = []
    session._watchdog_stop = None
    session._watchdog_thread = None
    session.feed = type("Feed", (), {"close": lambda self: None})()
    session.engine.open_position(
        strategy_id=PaperStrategyId.STRATEGY_A,
        direction=OptionTradeDirection.LONG,
        symbol="NSE:NIFTYCE",
        entry_price=100,
        timestamp=1_792_600_000,
    )
    return session


def test_forced_exit_missing_quote_keeps_position_open_and_alerts(tmp_path):
    session = _session(tmp_path, _QuoteCache(error=LookupError("stale quote")))
    now = datetime(2026, 10, 21, 15, 11, tzinfo=ZoneInfo("Asia/Kolkata"))

    session.check_forced_exits(now)

    assert session.engine.open_trade(PaperStrategyId.STRATEGY_A) is not None
    assert len(session.engine.trades(PaperStrategyId.STRATEGY_A)[0].exits) == 0
    assert any("FORCED EXIT PENDING" in alert for alert in session.alerts)
    assert session.quote_cache.calls == 1


def test_forced_exit_retries_and_closes_when_fresh_quote_returns(tmp_path):
    cache = _QuoteCache(error=LookupError("stale quote"))
    session = _session(tmp_path, cache)
    now = datetime(2026, 10, 21, 15, 11, tzinfo=ZoneInfo("Asia/Kolkata"))

    session.check_forced_exits(now)
    assert session.engine.open_trade(PaperStrategyId.STRATEGY_A) is not None

    cache.error = None
    cache.result = {"lp": 95.0}
    session.check_forced_exits(now)

    assert session.engine.open_trade(PaperStrategyId.STRATEGY_A) is None
    trade = session.engine.trades(PaperStrategyId.STRATEGY_A)[0]
    assert trade.closed
    assert len(trade.exits) == 1
    assert trade.exits[0].price == 95.0
    assert any("FORCED EXIT COMPLETED" in alert for alert in session.alerts)


def test_forced_exit_does_not_run_before_configured_time(tmp_path):
    cache = _QuoteCache(result={"lp": 95.0})
    session = _session(tmp_path, cache)
    now = datetime(2026, 10, 21, 15, 9, tzinfo=ZoneInfo("Asia/Kolkata"))

    session.check_forced_exits(now)

    assert session.engine.open_trade(PaperStrategyId.STRATEGY_A) is not None
    assert cache.calls == 0
