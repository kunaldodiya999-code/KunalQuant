from __future__ import annotations

import argparse
import json
import math
import sqlite3
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

from config.settings import DATABASE_PATH


class OptionAnalyticsEngine:
    """
    Kunal Quant - Option IV & Greeks Engine V1.

    Calculates derived option analytics from stored historical
    candles without modifying the raw candles table.

    Model:
        Black-76 using futures/forward price.

    Outputs:
        - implied volatility
        - delta
        - gamma
        - theta
        - vega
        - rho
        - DTE
        - moneyness

    The model does not fabricate missing option prices.

    V1 assumptions:
        - Futures price is used as forward.
        - Discount factor defaults to 1.0.
        - Risk-free rate defaults to 0.0.
        - Expiry time = 15:30 IST on expiry date.

    These assumptions are explicitly versioned so they can be
    upgraded later to historical interest-rate / dividend inputs.
    """

    TIMEZONE = ZoneInfo(
        "Asia/Kolkata"
    )

    OPTION_TYPES = (
        "CE",
        "PE",
    )

    OPTION_SOURCE = "FYERS_FNO_HISTORY"

    SPOT_SYMBOL = "NSE:NIFTY50-INDEX"

    FUTURES_OPTION_TYPE = "XX"

    CALCULATION_VERSION = (
        "black76_iv_greeks_v1"
    )

    DEFAULT_RISK_FREE_RATE = 0.0

    DEFAULT_DISCOUNT_FACTOR = 1.0

    IV_MIN = 0.0001

    IV_MAX = 5.0

    IV_TOLERANCE = 1e-8

    IV_MAX_ITERATIONS = 100

    # =========================================================
    # INITIALIZATION
    # =========================================================

    def __init__(
        self,
        database_path: Path | str = DATABASE_PATH,
        risk_free_rate: float = DEFAULT_RISK_FREE_RATE,
        discount_factor: float = DEFAULT_DISCOUNT_FACTOR,
    ) -> None:

        self.database_path = Path(
            database_path
        )

        self.database_path.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        self.risk_free_rate = float(
            risk_free_rate
        )

        self.discount_factor = float(
            discount_factor
        )

        if self.discount_factor <= 0:

            raise ValueError(
                "discount_factor must be greater "
                "than zero."
            )

    # =========================================================
    # DATABASE
    # =========================================================

    def _connect(self) -> sqlite3.Connection:

        connection = sqlite3.connect(
            self.database_path
        )

        connection.row_factory = sqlite3.Row

        connection.execute(
            "PRAGMA foreign_keys = ON"
        )

        return connection

    # =========================================================
    # NORMAL DISTRIBUTION
    # =========================================================

    @staticmethod
    def normal_pdf(
        x: float,
    ) -> float:

        return (
            math.exp(
                -0.5 * x * x
            )
            / math.sqrt(
                2.0 * math.pi
            )
        )

    @staticmethod
    def normal_cdf(
        x: float,
    ) -> float:

        return (
            0.5
            * (
                1.0
                + math.erf(
                    x
                    / math.sqrt(2.0)
                )
            )
        )

    # =========================================================
    # BLACK-76 PRICE
    # =========================================================

    def black76_price(
        self,
        forward_price: float,
        strike: float,
        time_to_expiry: float,
        volatility: float,
        option_type: str,
        discount_factor: float | None = None,
    ) -> float | None:

        if (
            forward_price <= 0
            or strike <= 0
            or time_to_expiry <= 0
            or volatility <= 0
        ):

            return None

        option_type = (
            option_type.upper()
        )

        if option_type not in self.OPTION_TYPES:

            raise ValueError(
                "option_type must be CE or PE."
            )

        df = (
            self.discount_factor
            if discount_factor is None
            else float(discount_factor)
        )

        sqrt_t = math.sqrt(
            time_to_expiry
        )

        d1 = (
            math.log(
                forward_price
                / strike
            )
            + 0.5
            * volatility
            * volatility
            * time_to_expiry
        ) / (
            volatility
            * sqrt_t
        )

        d2 = (
            d1
            - volatility
            * sqrt_t
        )

        nd1 = self.normal_cdf(
            d1
        )

        nd2 = self.normal_cdf(
            d2
        )

        if option_type == "CE":

            price = df * (
                forward_price
                * nd1
                - strike
                * nd2
            )

        else:

            price = df * (
                strike
                * self.normal_cdf(-d2)
                - forward_price
                * self.normal_cdf(-d1)
            )

        return max(
            float(price),
            0.0
        )

    # =========================================================
    # IMPLIED VOLATILITY
    # =========================================================

    def implied_volatility(
        self,
        option_price: float,
        forward_price: float,
        strike: float,
        time_to_expiry: float,
        option_type: str,
        discount_factor: float | None = None,
    ) -> float | None:

        if (
            option_price <= 0
            or forward_price <= 0
            or strike <= 0
            or time_to_expiry <= 0
        ):

            return None

        option_type = (
            option_type.upper()
        )

        df = (
            self.discount_factor
            if discount_factor is None
            else float(discount_factor)
        )

        # -----------------------------------------------------
        # No-arbitrage intrinsic bounds for Black-76.
        # -----------------------------------------------------

        if option_type == "CE":

            intrinsic = (
                df
                * max(
                    forward_price
                    - strike,
                    0.0
                )
            )

            upper_bound = (
                df
                * forward_price
            )

        elif option_type == "PE":

            intrinsic = (
                df
                * max(
                    strike
                    - forward_price,
                    0.0
                )
            )

            upper_bound = (
                df
                * strike
            )

        else:

            raise ValueError(
                "option_type must be CE or PE."
            )

        # A tiny tolerance allows for broker rounding.
        if option_price < intrinsic - 1e-8:

            return None

        if option_price > upper_bound + 1e-8:

            return None

        # -----------------------------------------------------
        # Bisection solver.
        # -----------------------------------------------------

        low = self.IV_MIN

        high = self.IV_MAX

        low_price = self.black76_price(
            forward_price=forward_price,
            strike=strike,
            time_to_expiry=time_to_expiry,
            volatility=low,
            option_type=option_type,
            discount_factor=df,
        )

        high_price = self.black76_price(
            forward_price=forward_price,
            strike=strike,
            time_to_expiry=time_to_expiry,
            volatility=high,
            option_type=option_type,
            discount_factor=df,
        )

        if (
            low_price is None
            or high_price is None
        ):

            return None

        # Option value must fall inside the numerical
        # price range generated by our volatility bracket.
        if option_price < low_price - 1e-8:

            return None

        if option_price > high_price + 1e-8:

            return None

        for _ in range(
            self.IV_MAX_ITERATIONS
        ):

            mid = (
                low
                + high
            ) / 2.0

            mid_price = (
                self.black76_price(
                    forward_price=forward_price,
                    strike=strike,
                    time_to_expiry=time_to_expiry,
                    volatility=mid,
                    option_type=option_type,
                    discount_factor=df,
                )
            )

            if mid_price is None:

                return None

            difference = (
                mid_price
                - option_price
            )

            if abs(
                difference
            ) <= self.IV_TOLERANCE:

                return mid

            if mid_price < option_price:

                low = mid

            else:

                high = mid

        return (
            low
            + high
        ) / 2.0

    # =========================================================
    # GREEKS
    # =========================================================

    def calculate_greeks(
        self,
        forward_price: float,
        strike: float,
        time_to_expiry: float,
        volatility: float,
        option_type: str,
        discount_factor: float | None = None,
    ) -> dict | None:

        if (
            forward_price <= 0
            or strike <= 0
            or time_to_expiry <= 0
            or volatility <= 0
        ):

            return None

        option_type = (
            option_type.upper()
        )

        if option_type not in self.OPTION_TYPES:

            raise ValueError(
                "option_type must be CE or PE."
            )

        df = (
            self.discount_factor
            if discount_factor is None
            else float(discount_factor)
        )

        sqrt_t = math.sqrt(
            time_to_expiry
        )

        d1 = (
            math.log(
                forward_price
                / strike
            )
            + 0.5
            * volatility
            * volatility
            * time_to_expiry
        ) / (
            volatility
            * sqrt_t
        )

        d2 = (
            d1
            - volatility
            * sqrt_t
        )

        pdf_d1 = self.normal_pdf(
            d1
        )

        cdf_d1 = self.normal_cdf(
            d1
        )

        cdf_d2 = self.normal_cdf(
            d2
        )

        # -----------------------------------------------------
        # Black-76 Greeks.
        #
        # Delta here is delta with respect to the forward.
        # Gamma is with respect to the forward.
        # -----------------------------------------------------

        if option_type == "CE":

            delta = (
                df
                * cdf_d1
            )

        else:

            delta = (
                df
                * (
                    cdf_d1
                    - 1.0
                )
            )

        gamma = (
            df
            * pdf_d1
            / (
                forward_price
                * volatility
                * sqrt_t
            )
        )

        vega = (
            df
            * forward_price
            * pdf_d1
            * sqrt_t
            / 100.0
        )

        # Theta is returned per calendar day.
        theta_per_year = (
            -(
                df
                * forward_price
                * pdf_d1
                * volatility
            )
            / (
                2.0
                * sqrt_t
            )
        )

        theta_per_day = (
            theta_per_year
            / 365.0
        )

        rho = 0.0

        return {
            "delta": delta,
            "gamma": gamma,
            "theta": theta_per_day,
            "vega": vega,
            "rho": rho,
        }

    # =========================================================
    # EXPIRY TIMESTAMP
    # =========================================================

    @classmethod
    def expiry_timestamp(
        cls,
        expiry_date: str,
    ) -> int:

        expiry_datetime = datetime.combine(
            datetime.strptime(
                expiry_date,
                "%Y-%m-%d",
            ).date(),
            time(
                15,
                30,
            ),
            tzinfo=cls.TIMEZONE,
        )

        return int(
            expiry_datetime.timestamp()
        )

    # =========================================================
    # TIME TO EXPIRY
    # =========================================================

    @classmethod
    def time_to_expiry(
        cls,
        timestamp: int,
        expiry_date: str,
    ) -> float:

        expiry_timestamp = (
            cls.expiry_timestamp(
                expiry_date
            )
        )

        seconds_remaining = (
            expiry_timestamp
            - int(timestamp)
        )

        if seconds_remaining <= 0:

            return 0.0

        return (
            seconds_remaining
            / (
                365.0
                * 24.0
                * 60.0
                * 60.0
            )
        )

    # =========================================================
    # OPTION MONEINESS
    # =========================================================

    @staticmethod
    def calculate_moneyness(
        forward_price: float,
        strike: float,
    ) -> float | None:

        if (
            forward_price <= 0
            or strike <= 0
        ):

            return None

        return (
            forward_price
            / strike
        )

    # =========================================================
    # FUTURES LOOKUP
    # =========================================================

    def find_futures_symbol(
        self,
        expiry_date: str,
    ) -> str | None:

        with self._connect() as connection:

            row = connection.execute(
                """
                SELECT symbol
                FROM instruments
                WHERE broker = 'FYERS'
                  AND underlying = 'NIFTY'
                  AND expiry_date = ?
                  AND instrument_type = '11'
                  AND option_type = 'XX'
                ORDER BY symbol
                LIMIT 1
                """,
                (
                    expiry_date,
                ),
            ).fetchone()

        if row is None:

            # Some databases may contain instrument_type
            # as an integer value rather than text.
            with self._connect() as connection:

                row = connection.execute(
                    """
                    SELECT symbol
                    FROM instruments
                    WHERE broker = 'FYERS'
                      AND underlying = 'NIFTY'
                      AND expiry_date = ?
                      AND instrument_type = 11
                      AND option_type = 'XX'
                    ORDER BY symbol
                    LIMIT 1
                    """,
                    (
                        expiry_date,
                    ),
                ).fetchone()

        if row is None:

            return None

        return str(
            row["symbol"]
        )

    # =========================================================
    # SERIES
    # =========================================================

    def get_candle_series(
        self,
        symbol: str,
        resolution: str,
        source: str,
        start_timestamp: int,
        end_timestamp: int,
    ) -> dict[int, dict]:

        with self._connect() as connection:

            rows = connection.execute(
                """
                SELECT
                    timestamp,
                    close
                FROM candles
                WHERE instrument_id = (
                    SELECT id
                    FROM instruments
                    WHERE broker = 'FYERS'
                      AND symbol = ?
                    LIMIT 1
                )
                  AND resolution = ?
                  AND source = ?
                  AND timestamp BETWEEN ?
                                      AND ?
                ORDER BY timestamp
                """,
                (
                    symbol,
                    resolution,
                    source,
                    start_timestamp,
                    end_timestamp,
                ),
            ).fetchall()

        result = {}

        for row in rows:

            if row["close"] is None:

                continue

            result[
                int(row["timestamp"])
            ] = {
                "close": float(
                    row["close"]
                )
            }

        return result

    # =========================================================
    # OPTION CONTRACTS
    # =========================================================

    def find_option_contract(
        self,
        symbol: str,
    ) -> dict | None:

        with self._connect() as connection:

            row = connection.execute(
                """
                SELECT
                    id,
                    symbol,
                    expiry_date,
                    strike,
                    option_type
                FROM instruments
                WHERE broker = 'FYERS'
                  AND symbol = ?
                  AND option_type IN ('CE', 'PE')
                LIMIT 1
                """,
                (
                    symbol,
                ),
            ).fetchone()

        if row is None:

            return None

        return dict(row)

    # =========================================================
    # STORE ANALYTICS
    # =========================================================

    def store_analytics(
        self,
        rows: list[dict],
    ) -> int:

        if not rows:

            return 0

        sql = """
        INSERT OR REPLACE INTO option_analytics (
            instrument_id,
            timestamp,
            resolution,
            underlying_price,
            forward_price,
            expiry_date,
            strike,
            option_type,
            dte,
            moneyness,
            implied_volatility,
            delta,
            gamma,
            theta,
            vega,
            rho,
            iv_source,
            greek_source,
            calculation_version
        )
        VALUES (
            ?,
            ?,
            ?,
            ?,
            ?,
            ?,
            ?,
            ?,
            ?,
            ?,
            ?,
            ?,
            ?,
            ?,
            ?,
            ?,
            ?,
            ?,
            ?
        )
        """

        records = []

        for row in rows:

            records.append(
                (
                    row["instrument_id"],
                    row["timestamp"],
                    row["resolution"],
                    row["underlying_price"],
                    row["forward_price"],
                    row["expiry_date"],
                    row["strike"],
                    row["option_type"],
                    row["dte"],
                    row["moneyness"],
                    row["implied_volatility"],
                    row["delta"],
                    row["gamma"],
                    row["theta"],
                    row["vega"],
                    row["rho"],
                    row["iv_source"],
                    row["greek_source"],
                    row["calculation_version"],
                )
            )

        with self._connect() as connection:

            connection.executemany(
                sql,
                records
            )

            connection.commit()

        return len(records)

    # =========================================================
    # BUILD ONE EXPIRY
    # =========================================================

    def build_expiry(
        self,
        expiry_date: str,
        range_from: str,
        range_to: str,
        resolution: str = "1",
        option_type: str | None = None,
        strike_min: float | None = None,
        strike_max: float | None = None,
        max_symbols: int | None = None,
    ) -> dict:

        start_dt = datetime.strptime(
            range_from,
            "%Y-%m-%d",
        )

        end_dt = datetime.strptime(
            range_to,
            "%Y-%m-%d",
        )

        if start_dt > end_dt:

            raise ValueError(
                "range_from cannot be after range_to."
            )

        start_timestamp = int(
            datetime.combine(
                start_dt.date(),
                time(
                    0,
                    0,
                ),
                tzinfo=self.TIMEZONE,
            ).timestamp()
        )

        end_timestamp = int(
            datetime.combine(
                end_dt.date(),
                time(
                    23,
                    59,
                    59,
                ),
                tzinfo=self.TIMEZONE,
            ).timestamp()
        )

        futures_symbol = (
            self.find_futures_symbol(
                expiry_date
            )
        )

        if futures_symbol is None:

            raise ValueError(
                "No NIFTY futures contract found "
                f"for expiry {expiry_date}."
            )

        spot = self.get_candle_series(
            symbol=self.SPOT_SYMBOL,
            resolution=resolution,
            source="FYERS_HISTORY",
            start_timestamp=start_timestamp,
            end_timestamp=end_timestamp,
        )

        futures = self.get_candle_series(
            symbol=futures_symbol,
            resolution=resolution,
            source="FYERS_FNO_HISTORY",
            start_timestamp=start_timestamp,
            end_timestamp=end_timestamp,
        )

        if not spot:

            raise ValueError(
                "No NIFTY spot data found."
            )

        if not futures:

            raise ValueError(
                "No NIFTY futures data found."
            )

        query = """
        SELECT
            id,
            symbol,
            expiry_date,
            strike,
            option_type
        FROM instruments
        WHERE broker = 'FYERS'
          AND underlying = 'NIFTY'
          AND expiry_date = ?
          AND option_type IN ('CE', 'PE')
        """

        parameters: list = [
            expiry_date
        ]

        if option_type is not None:

            option_type = option_type.upper()

            if option_type not in self.OPTION_TYPES:

                raise ValueError(
                    "option_type must be CE or PE."
                )

            query += """
              AND option_type = ?
            """

            parameters.append(
                option_type
            )

        if strike_min is not None:

            query += """
              AND strike >= ?
            """

            parameters.append(
                strike_min
            )

        if strike_max is not None:

            query += """
              AND strike <= ?
            """

            parameters.append(
                strike_max
            )

        query += """
        ORDER BY strike, option_type, symbol
        """

        with self._connect() as connection:

            contracts = [
                dict(row)
                for row in connection.execute(
                    query,
                    parameters,
                ).fetchall()
            ]

        if max_symbols is not None:

            if max_symbols <= 0:

                raise ValueError(
                    "max_symbols must be positive."
                )

            contracts = contracts[
                :max_symbols
            ]

        print(
            "\n" + "=" * 75
        )

        print(
            "KUNAL QUANT - OPTION IV / GREEKS V1"
        )

        print(
            "=" * 75
        )

        print(
            f"Expiry           : {expiry_date}"
        )

        print(
            f"Futures          : {futures_symbol}"
        )

        print(
            f"Contracts        : {len(contracts)}"
        )

        print(
            f"Range            : "
            f"{range_from} -> {range_to}"
        )

        print(
            f"Risk-free rate   : "
            f"{self.risk_free_rate:.6f}"
        )

        print(
            f"Discount factor  : "
            f"{self.discount_factor:.6f}"
        )

        analytics_rows = []

        processed_contracts = 0

        option_candles = 0

        valid_iv_count = 0

        invalid_iv_count = 0

        for contract in contracts:

            symbol = contract[
                "symbol"
            ]

            instrument_id = int(
                contract["id"]
            )

            option_rows = self.get_candle_series(
                symbol=symbol,
                resolution=resolution,
                source=self.OPTION_SOURCE,
                start_timestamp=start_timestamp,
                end_timestamp=end_timestamp,
            )

            if not option_rows:

                continue

            processed_contracts += 1

            for timestamp, option_candle in (
                option_rows.items()
            ):

                option_price = float(
                    option_candle["close"]
                )

                # Prefer futures as the forward.
                # Fall back to spot only when futures
                # is unavailable at this timestamp.
                future_row = futures.get(
                    timestamp
                )

                spot_row = spot.get(
                    timestamp
                )

                forward_price = None

                if future_row is not None:

                    forward_price = float(
                        future_row["close"]
                    )

                elif spot_row is not None:

                    forward_price = float(
                        spot_row["close"]
                    )

                if forward_price is None:

                    continue

                spot_price = (
                    float(
                        spot_row["close"]
                    )
                    if spot_row is not None
                    else None
                )

                time_to_expiry = (
                    self.time_to_expiry(
                        timestamp=timestamp,
                        expiry_date=expiry_date,
                    )
                )

                option_iv = (
                    self.implied_volatility(
                        option_price=option_price,
                        forward_price=forward_price,
                        strike=float(
                            contract["strike"]
                        ),
                        time_to_expiry=(
                            time_to_expiry
                        ),
                        option_type=contract[
                            "option_type"
                        ],
                    )
                )

                dte = (
                    time_to_expiry
                    * 365.0
                )

                moneyness = (
                    self.calculate_moneyness(
                        forward_price=forward_price,
                        strike=float(
                            contract["strike"]
                        ),
                    )
                )

                delta = None
                gamma = None
                theta = None
                vega = None
                rho = None

                if option_iv is not None:

                    greeks = (
                        self.calculate_greeks(
                            forward_price=forward_price,
                            strike=float(
                                contract["strike"]
                            ),
                            time_to_expiry=(
                                time_to_expiry
                            ),
                            volatility=(
                                option_iv
                            ),
                            option_type=contract[
                                "option_type"
                            ],
                        )
                    )

                    if greeks is not None:

                        delta = greeks[
                            "delta"
                        ]

                        gamma = greeks[
                            "gamma"
                        ]

                        theta = greeks[
                            "theta"
                        ]

                        vega = greeks[
                            "vega"
                        ]

                        rho = greeks[
                            "rho"
                        ]

                    valid_iv_count += 1

                else:

                    invalid_iv_count += 1

                analytics_rows.append(
                    {
                        "instrument_id": instrument_id,
                        "timestamp": timestamp,
                        "resolution": resolution,
                        "underlying_price": spot_price,
                        "forward_price": forward_price,
                        "expiry_date": expiry_date,
                        "strike": float(
                            contract["strike"]
                        ),
                        "option_type": contract[
                            "option_type"
                        ],
                        "dte": dte,
                        "moneyness": moneyness,
                        "implied_volatility": option_iv,
                        "delta": delta,
                        "gamma": gamma,
                        "theta": theta,
                        "vega": vega,
                        "rho": rho,
                        "iv_source": (
                            "BLACK76_MID"
                            if option_iv is not None
                            else "UNAVAILABLE"
                        ),
                        "greek_source": (
                            "BLACK76"
                            if option_iv is not None
                            else "UNAVAILABLE"
                        ),
                        "calculation_version": (
                            self.CALCULATION_VERSION
                        ),
                    }
                )

                option_candles += 1

        stored = (
            self.store_analytics(
                analytics_rows
            )
        )

        return {
            "underlying": "NIFTY",
            "expiry_date": expiry_date,
            "futures_symbol": futures_symbol,
            "resolution": resolution,
            "contracts_requested": len(
                contracts
            ),
            "contracts_with_data": (
                processed_contracts
            ),
            "option_candles_processed": (
                option_candles
            ),
            "valid_iv_rows": (
                valid_iv_count
            ),
            "invalid_iv_rows": (
                invalid_iv_count
            ),
            "analytics_rows_stored": (
                stored
            ),
            "calculation_version": (
                self.CALCULATION_VERSION
            ),
            "risk_free_rate": (
                self.risk_free_rate
            ),
            "discount_factor": (
                self.discount_factor
            ),
        }

    # =========================================================
    # SAMPLE
    # =========================================================

    def run_sample(self) -> dict:

        return self.build_expiry(
            expiry_date="2024-11-28",
            range_from="2024-11-27",
            range_to="2024-11-28",
            resolution="1",
            strike_min=23700,
            strike_max=24100,
        )


# =============================================================
# CLI
# =============================================================

def main() -> None:

    parser = argparse.ArgumentParser(
        description=(
            "Kunal Quant - "
            "Option IV & Greeks Engine"
        )
    )

    parser.add_argument(
        "--sample",
        action="store_true",
        help="Run controlled 2024-11-28 sample.",
    )

    parser.add_argument(
        "--expiry",
        type=str,
        default=None,
        help="Option expiry YYYY-MM-DD.",
    )

    parser.add_argument(
        "--from",
        dest="range_from",
        type=str,
        default=None,
        help="Historical start date.",
    )

    parser.add_argument(
        "--to",
        dest="range_to",
        type=str,
        default=None,
        help="Historical end date.",
    )

    parser.add_argument(
        "--resolution",
        type=str,
        default="1",
        help="Candle resolution.",
    )

    parser.add_argument(
        "--option-type",
        type=str,
        default=None,
        choices=["CE", "PE"],
        help="Only calculate CE or PE.",
    )

    parser.add_argument(
        "--strike-min",
        type=float,
        default=None,
        help="Minimum strike.",
    )

    parser.add_argument(
        "--strike-max",
        type=float,
        default=None,
        help="Maximum strike.",
    )

    parser.add_argument(
        "--max-symbols",
        type=int,
        default=None,
        help="Limit contracts for a controlled run.",
    )

    parser.add_argument(
        "--risk-free-rate",
        type=float,
        default=0.0,
        help=(
            "Annual risk-free rate as decimal. "
            "Default: 0.0"
        ),
    )

    parser.add_argument(
        "--discount-factor",
        type=float,
        default=1.0,
        help=(
            "Discount factor. "
            "Default: 1.0"
        ),
    )

    args = parser.parse_args()

    engine = OptionAnalyticsEngine(
        risk_free_rate=args.risk_free_rate,
        discount_factor=args.discount_factor,
    )

    if args.sample:

        result = engine.run_sample()

    else:

        if not args.expiry:

            raise SystemExit(
                "--expiry is required."
            )

        if not args.range_from:

            raise SystemExit(
                "--from is required."
            )

        if not args.range_to:

            raise SystemExit(
                "--to is required."
            )

        result = engine.build_expiry(
            expiry_date=args.expiry,
            range_from=args.range_from,
            range_to=args.range_to,
            resolution=args.resolution,
            option_type=args.option_type,
            strike_min=args.strike_min,
            strike_max=args.strike_max,
            max_symbols=args.max_symbols,
        )

    print(
        "\n" + "=" * 75
    )

    print(
        "OPTION IV / GREEKS RESULT"
    )

    print(
        "=" * 75
    )

    print(
        json.dumps(
            result,
            indent=2,
            default=str,
        )
    )

    print(
        "\n" + "=" * 75
    )


if __name__ == "__main__":
    main()