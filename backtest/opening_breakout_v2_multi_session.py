"""Multi-session real historical runner for Opening Breakout V2.

Research-only orchestration. Each trading date is scanned independently so the
first candle of one session can never become the setup candle for another.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Sequence
from zoneinfo import ZoneInfo

from backtest.fyers_option_candles import FyersOptionCandleLoader
from backtest.opening_breakout_v2_option_integration import (
    ResolvedOpeningBreakoutTrade,
    run_opening_breakout_trade,
)
from backtest.opening_breakout_v2_signal_engine import (
    OpeningBreakoutEvent,
    SignalSeries,
    scan_series,
)
from execution.opening_breakout_v2_execution import V2ExecutionPolicy
from research.opening_breakout_1m_v2 import Candle, IndicatorSnapshot, V2Config
from strategies.option_contract_resolver import OptionContractResolver

IST = ZoneInfo("Asia/Kolkata")
IndicatorProvider = Callable[[int, Candle], IndicatorSnapshot]


@dataclass(frozen=True)
class MultiSessionResult:
    sessions: int
    signals: int
    closed: int
    rejected: int
    gross_pnl: float
    trades: tuple[ResolvedOpeningBreakoutTrade, ...]


def session_date(timestamp: int):
    return datetime.fromtimestamp(timestamp, tz=IST).date()


def group_candles_by_session(
    candles: Sequence[Candle],
) -> tuple[tuple[object, tuple[Candle, ...]], ...]:
    grouped: dict[object, list[Candle]] = {}
    for candle in sorted(candles, key=lambda item: item.timestamp):
        grouped.setdefault(session_date(candle.timestamp), []).append(candle)
    return tuple((day, tuple(items)) for day, items in sorted(grouped.items()))


def run_multi_session_backtest(
    *,
    candles: Sequence[Candle],
    config: V2Config,
    resolver: OptionContractResolver,
    option_loader: FyersOptionCandleLoader,
    execution_policy: V2ExecutionPolicy,
    capital: float,
    indicator_provider: IndicatorProvider,
) -> MultiSessionResult:
    trades: list[ResolvedOpeningBreakoutTrade] = []
    sessions = 0
    signals = 0
    rejected = 0

    for _, session_candles in group_candles_by_session(candles):
        if len(session_candles) < 2:
            continue

        sessions += 1
        series = SignalSeries(
            symbol="NIFTY-V2-CANDIDATE",
            option_type="CE",
            strike=0,
            lot_size=1,
            candles=session_candles,
        )
        _, events = scan_series(
            series,
            config=config,
            indicator_provider=indicator_provider,
        )
        signals += len(events)

        for event in events:
            force_exit = int(
                datetime.fromtimestamp(event.trigger_timestamp, tz=IST)
                .replace(hour=15, minute=15, second=0, microsecond=0)
                .timestamp()
            )
            try:
                trade = run_opening_breakout_trade(
                    event=event,
                    underlying_candles=session_candles,
                    resolver=resolver,
                    option_loader=option_loader,
                    config=config,
                    execution_policy=execution_policy,
                    capital=capital,
                    force_exit_timestamp=force_exit,
                )
            except Exception:
                rejected += 1
                continue

            trades.append(trade)
            if trade.status != "CLOSED":
                rejected += 1

    closed = sum(1 for trade in trades if trade.status == "CLOSED")
    gross_pnl = sum(
        trade.gross_pnl for trade in trades if trade.status == "CLOSED"
    )
    return MultiSessionResult(
        sessions=sessions,
        signals=signals,
        closed=closed,
        rejected=rejected,
        gross_pnl=gross_pnl,
        trades=tuple(trades),
    )


__all__ = [
    "MultiSessionResult",
    "group_candles_by_session",
    "run_multi_session_backtest",
    "session_date",
]
