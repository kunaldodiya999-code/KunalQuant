"""Composition root for a buyer-only FYERS paper session.

Building a session does not connect to a socket or place broker orders.
Starting the feed is explicit. The current option lot size must be supplied
by the caller after checking the selected contract specification.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo
from typing import Any, Callable

from api.fyers_client import FyersClient
from market_data.fyers_quote_cache import FyersQuoteCache
from market_data.live_ticks import LiveMinuteBarBuilder
from market_data.resampling import Candle
from paper_trading.buyer_lifecycle import BuyerLifecycleConfig, BuyerOptionTradeLifecycle
from paper_trading.coordinator import PaperExecutionCoordinator
from paper_trading.engine import PaperEngineConfig, PaperStrategyId, PaperTradingEngine
from paper_trading.entry_adapter import PaperEntryAdapter, PaperEntryAdapterConfig
from paper_trading.fyers_feed import FyersPaperFeed
from paper_trading.market_data_pipeline import PaperMarketDataPipeline
from paper_trading.pending_entry_orchestrator import PendingEntryConfig, PendingEntryOrchestrator
from paper_trading.recorder import PaperTradeRecorder
from paper_trading.tsl_shadow_lab import OptionCandle, TslShadowLab
from paper_trading.settings import PaperTradingSettings
from strategies.option_contract_resolver import OptionContractResolver


def process_completed_option_candle(
    engine: PaperTradingEngine,
    *,
    symbol: str,
    candle: Candle,
) -> None:
    """Advance matching active paper trades from one completed option candle.

    Candle timestamps are bucket starts. A candle that started at or before
    the entry quote timestamp is excluded because part of its price range may
    predate the simulated entry. Repeated/out-of-order candles are ignored.
    KAMA exits remain disabled in this integration milestone.
    """
    for strategy_id in PaperStrategyId:
        trade = engine.open_trade(strategy_id)
        if trade is None or trade.position.symbol != symbol:
            continue
        if candle.timestamp <= trade.entry_timestamp:
            continue
        if (
            trade.last_processed_timestamp is not None
            and candle.timestamp <= trade.last_processed_timestamp
        ):
            continue

        engine.process_option_candle(
            strategy_id=strategy_id,
            timestamp=candle.timestamp,
            option_high=candle.high,
            option_low=candle.low,
            option_close=candle.close,
            underlying_close=None,
            kama_value=None,
        )


@dataclass(frozen=True)
class PaperSessionConfig:
    lot_size: int
    allocation: float = 20_000.0
    resolution_minutes: int = 3
    underlying_symbol: str = "NSE:NIFTY50-INDEX"
    database_path: str | Path | None = None
    output_dir: str | Path = "data/paper_trading"
    pending_journal_path: str | Path = "data/paper_trading/pending_entries.csv"
    pending_timeout_seconds: int = 8
    max_quote_age_seconds: int = 5
    max_receive_age_seconds: float = 5.0
    stop_loss_pct: float = 0.30
    target_rr: float = 2.0
    partial_exit_fraction: float = 0.50
    partial_exit_enabled: bool = True
    single_lot_partial_mode: str = "close_all"
    entry_cutoff: str = "15:00"
    forced_exit_enabled: bool = True
    forced_exit_time: str = "15:10"
    settings_path: str | Path | None = None
    target_enabled: bool = True

    def __post_init__(self) -> None:
        if self.lot_size < 1:
            raise ValueError("Supply the verified current contract lot size.")
        if self.allocation <= 0:
            raise ValueError("allocation must be positive.")
        if self.resolution_minutes not in (1, 3, 5):
            raise ValueError("resolution_minutes must be 1, 3, or 5.")


@dataclass
class PaperSession:
    feed: FyersPaperFeed
    quote_cache: FyersQuoteCache
    pipeline: PaperMarketDataPipeline
    resolver: OptionContractResolver
    engine: PaperTradingEngine
    coordinator: PaperExecutionCoordinator
    orchestrator: PendingEntryOrchestrator
    recorder: PaperTradeRecorder
    tsl_shadow: TslShadowLab
    alerts: list[str]

    def start(self) -> None:
        """Start market-data streaming only; no broker orders are submitted."""
        self.feed.start()

    def close(self) -> None:
        self.feed.close()


def build_paper_session(
    *,
    client: FyersClient,
    config: PaperSessionConfig,
    resolver: OptionContractResolver | None = None,
    engine_config: PaperEngineConfig | None = None,
    socket_factory: Callable[..., Any] | None = None,
) -> PaperSession:
    """Wire all paper entry components without connecting the market-data socket.

    When settings_path is supplied, validated saved settings override paper-risk
    defaults for this session build. The locked historical V1 lifecycle is not used
    or modified by these settings.
    """
    if config.settings_path is not None:
        saved = PaperTradingSettings.load(config.settings_path)
        config = replace(
            config,
            allocation=saved.allocation_amount,
            stop_loss_pct=saved.stop_loss_pct / 100.0,
            target_rr=saved.partial_trigger_r,
            partial_exit_fraction=saved.partial_exit_pct / 100.0,
            partial_exit_enabled=saved.partial_exit_enabled,
            single_lot_partial_mode=saved.single_lot_partial_mode,
            entry_cutoff=saved.entry_cutoff,
            forced_exit_enabled=saved.forced_exit_enabled,
            forced_exit_time=saved.forced_exit_time,
            target_enabled=saved.partial_exit_enabled,
        )
    recorder = PaperTradeRecorder(config.output_dir)
    quote_cache = FyersQuoteCache()
    if resolver is None:
        resolver = OptionContractResolver(
            database_path=config.database_path
        ) if config.database_path is not None else OptionContractResolver()

    pipeline = PaperMarketDataPipeline(
        resolution_minutes=config.resolution_minutes,
        paper_config=engine_config,
        recorder=recorder,
    )
    lifecycle = BuyerOptionTradeLifecycle(
        BuyerLifecycleConfig(
            allocation=config.allocation,
            lot_size=config.lot_size,
            stop_loss_pct=config.stop_loss_pct,
            target_rr=config.target_rr,
            partial_exit_fraction=config.partial_exit_fraction,
            target_enabled=config.target_enabled,
            partial_exit_enabled=config.partial_exit_enabled,
            single_lot_partial_mode=config.single_lot_partial_mode,
        )
    )
    engine = PaperTradingEngine(
        config=engine_config,
        recorder=recorder,
        lifecycle=lifecycle,
    )
    adapter = PaperEntryAdapter(
        resolver=resolver,
        config=PaperEntryAdapterConfig(
            max_quote_age_seconds=config.max_quote_age_seconds
        ),
    )
    coordinator = PaperExecutionCoordinator(
        adapter=adapter, engine=engine, entry_cutoff=config.entry_cutoff
    )

    # Late-bound callbacks resolve entry wiring and shadow exit tracking.
    holder: dict[str, PendingEntryOrchestrator] = {}
    session_alerts: list[str] = []
    market_tz = ZoneInfo("Asia/Kolkata")
    forced_exit_clock = time.fromisoformat(config.forced_exit_time)
    tsl_shadow = TslShadowLab(Path(config.output_dir) / "tsl_shadow")
    option_tick_builder = LiveMinuteBarBuilder()

    def on_signals(signals) -> None:
        orchestrator = holder.get("orchestrator")
        if orchestrator is not None:
            orchestrator.on_signals(signals)

    def on_tick(message) -> None:
        orchestrator = holder.get("orchestrator")
        if orchestrator is not None:
            orchestrator.on_tick(message)

        # Register each accepted paper entry with independent shadow candidates.
        for trade in engine.all_trades():
            # Historical closed records must not be enrolled as fresh shadow trades.
            # Entries are registered on the tick immediately after paper acceptance.
            if trade.closed:
                continue
            position = trade.position
            trade_id = f"{trade.strategy_id.value}:{trade.entry_timestamp}:{position.symbol}"
            tsl_shadow.register_trade(
                trade_id=trade_id,
                symbol=position.symbol,
                direction=getattr(position.direction, "value", position.direction),
                entry_timestamp=trade.entry_timestamp,
                entry_price=position.entry_price,
                quantity=position.quantity,
            )

        # At/after the forced-exit time, a fresh tick for an open option is the
        # only permitted fill source. Missing/stale quotes alert and remain open.
        if isinstance(message, dict):
            symbol = message.get("symbol")
            if isinstance(symbol, str) and symbol.strip() != config.underlying_symbol:
                option_symbol = symbol.strip()
                if config.forced_exit_enabled and datetime.now(market_tz).time() >= forced_exit_clock:
                    now_epoch = int(datetime.now(market_tz).timestamp())
                    try:
                        quote_price = float(message.get("lp", message.get("ltp", message.get("last_price"))))
                        quote_timestamp = int(message.get("exch_feed_time", message.get("last_traded_time", message.get("timestamp"))))
                        quote_age = now_epoch - quote_timestamp
                        valid_quote = quote_price > 0 and 0 <= quote_age <= config.max_quote_age_seconds
                    except (TypeError, ValueError):
                        valid_quote = False
                        quote_price = 0.0
                    for strategy_id in PaperStrategyId:
                        active = engine.open_trade(strategy_id)
                        if active is None or active.position.symbol != option_symbol:
                            continue
                        if valid_quote:
                            engine.force_exit_position(
                                strategy_id=strategy_id, timestamp=now_epoch,
                                fresh_option_price=quote_price,
                            )
                        else:
                            alert = f"FORCED EXIT PENDING: {option_symbol} has missing/stale quote at/after {config.forced_exit_time} IST; position remains open."
                            if not session_alerts or session_alerts[-1] != alert:
                                session_alerts.append(alert)
                for candle in option_tick_builder.on_message(message):
                    option_candle = OptionCandle(
                        timestamp=candle.timestamp, open=candle.open,
                        high=candle.high, low=candle.low, close=candle.close,
                    )

                    # Shadow candidates are observational only; they never
                    # control or close the active paper position.
                    tsl_shadow.on_candle(
                        symbol=option_symbol,
                        candle=option_candle,
                    )

                    # Advance active buyer-only positions independently
                    # from the observational TSL shadow candidates.
                    process_completed_option_candle(
                        engine, symbol=option_symbol, candle=candle
                    )

    feed = FyersPaperFeed(
        client=client,
        pipeline=pipeline,
        quote_cache=quote_cache,
        underlying_symbols=[config.underlying_symbol],
        on_signals=on_signals,
        on_tick=on_tick,
        socket_factory=socket_factory,
    )
    orchestrator = PendingEntryOrchestrator(
        resolver=resolver,
        quote_cache=quote_cache,
        coordinator=coordinator,
        subscribe_symbols=feed.subscribe_symbols,
        underlying_symbol=config.underlying_symbol,
        config=PendingEntryConfig(
            timeout_seconds=config.pending_timeout_seconds,
            max_quote_age_seconds=config.max_quote_age_seconds,
            max_receive_age_seconds=config.max_receive_age_seconds,
            journal_path=config.pending_journal_path,
        ),
    )
    holder["orchestrator"] = orchestrator

    return PaperSession(
        feed=feed,
        quote_cache=quote_cache,
        pipeline=pipeline,
        resolver=resolver,
        engine=engine,
        coordinator=coordinator,
        orchestrator=orchestrator,
        recorder=recorder,
        tsl_shadow=tsl_shadow,
        alerts=session_alerts,
    )


__all__ = ["PaperSession", "PaperSessionConfig", "build_paper_session", "process_completed_option_candle"]
