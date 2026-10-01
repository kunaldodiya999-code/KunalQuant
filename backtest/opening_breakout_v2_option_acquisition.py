"""V2-specific historical NIFTY option acquisition planning.

This module derives the exact option contracts required by the existing
Opening Breakout V2 signal pipeline. It does not modify Resolver V2,
strategy logic, execution logic, or portfolio accounting.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Callable, Sequence
from zoneinfo import ZoneInfo

from backtest.historical_nifty_expiry import historical_nifty_expiry
from backtest.opening_breakout_v2_multi_session import group_candles_by_session
from backtest.opening_breakout_v2_signal_engine import SignalSeries, scan_series
from research.opening_breakout_1m_v2 import Candle, IndicatorSnapshot, V2Config
from strategies.option_contract_resolver import OptionContractResolver

IST = ZoneInfo("Asia/Kolkata")
IndicatorProvider = Callable[[int, Candle], IndicatorSnapshot]


@dataclass(frozen=True)
class RequiredOptionContract:
    expiry: date
    strike: int
    option_type: str
    first_signal_date: date
    last_signal_date: date
    signal_count: int


def _underlying_price_at(
    candles: Sequence[Candle],
    timestamp: int,
) -> float:
    candidates = [c for c in candles if c.timestamp <= timestamp]
    if not candidates:
        raise LookupError(
            f"no underlying candle at or before signal timestamp {timestamp}"
        )
    return float(max(candidates, key=lambda c: c.timestamp).close)


def build_required_option_contracts(
    *,
    candles: Sequence[Candle],
    config: V2Config,
    resolver: OptionContractResolver,
    indicator_provider: IndicatorProvider,
) -> tuple[RequiredOptionContract, ...]:
    """Build the exact unique option contracts required by V2 signals."""

    grouped = group_candles_by_session(candles)
    session_dates = tuple(day for day, _ in grouped)
    requirements: dict[tuple[date, int, str], RequiredOptionContract] = {}

    for _, session_candles in grouped:
        if len(session_candles) < 2:
            continue

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

        for event in events:
            signal_date = datetime.fromtimestamp(
                event.trigger_timestamp,
                tz=IST,
            ).date()

            underlying_price = _underlying_price_at(
                session_candles,
                event.trigger_timestamp,
            )
            strike = resolver.calculate_atm_strike(underlying_price)
            option_type = "CE" if event.direction == "LONG" else "PE"
            expiry = historical_nifty_expiry(
                signal_date,
                session_dates,
            )

            key = (expiry, strike, option_type)
            previous = requirements.get(key)

            if previous is None:
                requirements[key] = RequiredOptionContract(
                    expiry=expiry,
                    strike=strike,
                    option_type=option_type,
                    first_signal_date=signal_date,
                    last_signal_date=signal_date,
                    signal_count=1,
                )
            else:
                requirements[key] = RequiredOptionContract(
                    expiry=expiry,
                    strike=strike,
                    option_type=option_type,
                    first_signal_date=min(
                        previous.first_signal_date,
                        signal_date,
                    ),
                    last_signal_date=max(
                        previous.last_signal_date,
                        signal_date,
                    ),
                    signal_count=previous.signal_count + 1,
                )

    return tuple(
        sorted(
            requirements.values(),
            key=lambda item: (
                item.expiry,
                item.strike,
                item.option_type,
            ),
        )
    )


def parse_expired_option_symbols(response: object) -> tuple[str, ...]:
    """Extract FYERS NIFTY option symbols from expired-contract responses."""

    if not isinstance(response, dict):
        return ()

    data = response.get("data", {})
    if not isinstance(data, dict):
        return ()

    candidates: list[object] = []

    symbols = data.get("symbols", [])
    if isinstance(symbols, list):
        candidates.extend(symbols)

    contracts = data.get("contracts", {})
    if isinstance(contracts, dict):
        options = contracts.get("options", [])
        if isinstance(options, list):
            candidates.extend(options)

    return tuple(
        sorted(
            {
                value
                for value in candidates
                if isinstance(value, str)
                and value.startswith("NSE:NIFTY")
                and value.endswith(("CE", "PE"))
            }
        )
    )


def strike_from_option_symbol(symbol: str) -> int | None:
    """Extract the strike from a FYERS NIFTY option symbol."""
    if not symbol.startswith("NSE:NIFTY") or not symbol.endswith(("CE", "PE")):
        return None

    body = symbol[len("NSE:NIFTY"):-2]
    digits = ""
    for char in reversed(body):
        if char.isdigit():
            digits = char + digits
        else:
            break

    if not digits:
        return None
    return int(digits)


def option_type_from_symbol(symbol: str) -> str | None:
    if symbol.endswith("CE"):
        return "CE"
    if symbol.endswith("PE"):
        return "PE"
    return None


def match_required_contract(
    requirement: RequiredOptionContract,
    symbols: Sequence[str],
) -> str | None:
    """Match one required strike/type against a FYERS expiry response."""
    for symbol in symbols:
        if option_type_from_symbol(symbol) != requirement.option_type:
            continue
        if strike_from_option_symbol(symbol) != requirement.strike:
            continue
        return symbol
    return None


__all__ = [
    "RequiredOptionContract",
    "build_required_option_contracts",
    "match_required_contract",
    "option_type_from_symbol",
    "parse_expired_option_symbols",
    "strike_from_option_symbol",
]
