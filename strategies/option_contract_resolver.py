"""Resolve actual FYERS option contracts from the local instrument master.

The database's instrument rows are authoritative for symbols and expiries.
Bank Nifty is restricted to the latest listed expiry in each calendar month;
this avoids selecting weekly series if they are ever present in imported data.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from config.settings import DATABASE_PATH
from instrument_universe import get_underlying, ExpirySeries


@dataclass(frozen=True)
class ResolvedOptionContract:
    instrument_id: int
    symbol: str
    underlying: str
    expiry_date: date
    strike: int
    option_type: str


@dataclass(frozen=True)
class OptionResolverConfig:
    strike_step: int = 50


DEFAULT_OPTION_RESOLVER_CONFIG = OptionResolverConfig()


class OptionContractResolver:
    """Resolve ATM CE/PE contracts for one configured underlying."""

    def __init__(
        self,
        database_path: Path | str = DATABASE_PATH,
        config: OptionResolverConfig = DEFAULT_OPTION_RESOLVER_CONFIG,
        *,
        underlying_key: str = "NIFTY50",
    ) -> None:
        self.database_path = Path(database_path)
        self.config = config
        self.underlying_key = get_underlying(underlying_key).key

    @staticmethod
    def _db_underlying(spec) -> tuple[str, ...]:
        # Existing instrument ingestion commonly stores exchange-independent
        # canonical codes; aliases permit old/imported rows without guessing symbols.
        return spec.broker_underlying_candidates

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def calculate_atm_strike(self, underlying_price: float) -> int:
        if underlying_price <= 0:
            raise ValueError("Underlying price must be positive.")
        step = self.config.strike_step
        if step <= 0:
            raise ValueError("Strike step must be positive.")
        return int(round(underlying_price / step) * step)

    def _expiry_query(self, *, entry_date: date, option_type: str, underlying_key: str) -> date:
        spec = get_underlying(underlying_key)
        aliases = self._db_underlying(spec)
        placeholders = ",".join("?" for _ in aliases)
        with self._connect() as connection:
            rows = connection.execute(
                f"""SELECT DISTINCT expiry_date FROM instruments
                    WHERE broker = 'FYERS' AND exchange = ? AND underlying IN ({placeholders})
                      AND option_type = ? AND expiry_date >= ? AND is_active = 1
                    ORDER BY expiry_date""",
                (spec.exchange, *aliases, option_type, entry_date.isoformat()),
            ).fetchall()
        expiries = [date.fromisoformat(row["expiry_date"]) for row in rows if row["expiry_date"]]
        if spec.expiry_series is ExpirySeries.MONTHLY_ONLY:
            # In the imported contract master, choose the latest available
            # listed expiry per month. Actual holiday-adjusted dates are taken
            # from the master, never calculated from a weekday rule.
            by_month: dict[tuple[int, int], date] = {}
            for expiry in expiries:
                key = (expiry.year, expiry.month)
                if key not in by_month or expiry > by_month[key]:
                    by_month[key] = expiry
            expiries = sorted(by_month.values())
        if not expiries:
            raise LookupError(
                f"No eligible {spec.display_name} {option_type} expiry found on/after {entry_date}."
            )
        return expiries[0]

    def find_nearest_expiry(
        self, entry_date: date, option_type: str, *, underlying_key: str | None = None
    ) -> date:
        key = get_underlying(underlying_key or self.underlying_key).key
        option_type = option_type.upper()
        if option_type not in ("CE", "PE"):
            raise ValueError("option_type must be CE or PE.")
        return self._expiry_query(
            entry_date=entry_date, option_type=option_type, underlying_key=key
        )

    def resolve(
        self,
        *,
        underlying_price: float,
        entry_date: date,
        direction: str,
        underlying_key: str | None = None,
    ) -> ResolvedOptionContract:
        spec = get_underlying(underlying_key or self.underlying_key)
        direction = direction.upper()
        if direction == "LONG":
            option_type = "CE"
        elif direction == "SHORT":
            option_type = "PE"
        else:
            raise ValueError("direction must be LONG or SHORT.")
        expiry = self.find_nearest_expiry(entry_date, option_type, underlying_key=spec.key)
        aliases = self._db_underlying(spec)
        placeholders = ",".join("?" for _ in aliases)
        # Choose the nearest strike actually listed for this expiry/type. This
        # avoids hard-coding a strike step that differs by index or changes over time.
        with self._connect() as connection:
            rows = connection.execute(
                f"""SELECT id, symbol, underlying, expiry_date, strike, option_type
                    FROM instruments
                    WHERE broker = 'FYERS' AND exchange = ? AND underlying IN ({placeholders})
                      AND expiry_date = ? AND option_type = ? AND is_active = 1
                      AND strike IS NOT NULL
                    ORDER BY ABS(strike - ?), strike, symbol""",
                (spec.exchange, *aliases, expiry.isoformat(), option_type, float(underlying_price)),
            ).fetchall()
        if not rows:
            raise LookupError(
                f"No listed {spec.display_name} {expiry} {option_type} contracts found."
            )
        row = rows[0]
        return ResolvedOptionContract(
            instrument_id=int(row["id"]),
            symbol=str(row["symbol"]),
            underlying=str(row["underlying"]),
            expiry_date=date.fromisoformat(row["expiry_date"]),
            strike=int(row["strike"]),
            option_type=str(row["option_type"]),
        )
