from paper_trading.buyer_lifecycle import BuyerLifecycleConfig, BuyerOptionTradeLifecycle
from paper_trading.engine import PaperStrategyId, PaperTradingEngine


def test_cash_basis_accounts_for_open_positions():
    lifecycle = BuyerOptionTradeLifecycle(BuyerLifecycleConfig(allocation=20000, lot_size=25))
    engine = PaperTradingEngine(lifecycle=lifecycle, starting_capital=100000, allocation_pct=20)
    trade = engine.open_position(strategy_id=PaperStrategyId.STRATEGY_A, direction="LONG", symbol="CE", entry_price=100, timestamp=100)
    assert trade is not None
    assert engine.available_cash() == 80000
