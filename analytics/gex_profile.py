from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any

from config.settings import DATABASE_PATH


class GEXProfileEngine:
    """
    Kunal Quant - GEX Profile Engine V1.

    Read-only analytical layer built on top of the validated
    gex_snapshots table.

    It does NOT recalculate GEX.

    It aggregates already calculated GEX snapshots into a
    strike-level profile and a latest-market summary.
    """

    UNDERLYING = "NIFTY"
    RESOLUTION = "1"

    GEX_CONVENTION = (
        "CALL_POSITIVE_PUT_NEGATIVE"
    )

    CALCULATION_VERSION = (
        "gex_v1_black76_ltp"
    )

    def __init__(
        self,
        database_path: Path | str = DATABASE_PATH,
    ) -> None:

        self.database_path = Path(
            database_path
        )

    # =========================================================
    # DATABASE
    # =========================================================

    def _connect(self) -> sqlite3.Connection:

        connection = sqlite3.connect(
            self.database_path
        )

        connection.row_factory = sqlite3.Row

        return connection

    # =========================================================
    # LOAD LATEST TIMESTAMP
    # =========================================================

    def get_latest_timestamp(
        self,
        expiry_date: str,
    ) -> int | None:

        with self._connect() as connection:

            row = connection.execute(
                """
                SELECT MAX(timestamp) AS latest_timestamp
                FROM gex_snapshots
                WHERE underlying = ?
                  AND expiry_date = ?
                  AND resolution = ?
                  AND gex_convention = ?
                  AND calculation_version = ?
                """,
                (
                    self.UNDERLYING,
                    expiry_date,
                    self.RESOLUTION,
                    self.GEX_CONVENTION,
                    self.CALCULATION_VERSION,
                ),
            ).fetchone()

        if row is None:
            return None

        if row["latest_timestamp"] is None:
            return None

        return int(
            row["latest_timestamp"]
        )

    # =========================================================
    # STRIKE PROFILE
    # =========================================================

    def get_latest_profile(
        self,
        expiry_date: str,
        top_n: int = 10,
    ) -> dict:

        latest_timestamp = (
            self.get_latest_timestamp(
                expiry_date
            )
        )

        if latest_timestamp is None:

            raise ValueError(
                "No GEX snapshots found for "
                f"expiry {expiry_date}."
            )

        with self._connect() as connection:

            rows = connection.execute(
                """
                SELECT
                    timestamp,
                    strike,
                    spot_price,
                    call_oi,
                    put_oi,
                    call_gamma,
                    put_gamma,
                    call_gex,
                    put_gex,
                    gross_gex,
                    net_gex
                FROM gex_snapshots
                WHERE underlying = ?
                  AND expiry_date = ?
                  AND resolution = ?
                  AND gex_convention = ?
                  AND calculation_version = ?
                  AND timestamp = ?
                ORDER BY strike
                """,
                (
                    self.UNDERLYING,
                    expiry_date,
                    self.RESOLUTION,
                    self.GEX_CONVENTION,
                    self.CALCULATION_VERSION,
                    latest_timestamp,
                ),
            ).fetchall()

        profile = [
            dict(row)
            for row in rows
        ]

        # -----------------------------------------------------
        # ATM / SPOT-CENTERED INFORMATION
        # -----------------------------------------------------

        if profile:
            spot_price = float(
                profile[0]["spot_price"]
            )

            atm_row = min(
                profile,
                key=lambda row: abs(
                    float(row["strike"])
                    - spot_price
                ),
            )

            atm_strike = float(
                atm_row["strike"]
            )

            atm_distance = (
                spot_price
                - atm_strike
            )

        else:
            spot_price = None
            atm_strike = None
            atm_distance = None

        positive = sorted(
            [
                row
                for row in profile
                if float(row["net_gex"]) > 0
            ],
            key=lambda row: float(
                row["net_gex"]
            ),
            reverse=True,
        )

        negative = sorted(
            [
                row
                for row in profile
                if float(row["net_gex"]) < 0
            ],
            key=lambda row: float(
                row["net_gex"]
            ),
        )

        return {
            "expiry_date": expiry_date,
            "timestamp": latest_timestamp,
            "strike_count": len(profile),
            "spot_price": spot_price,
            "atm_strike": atm_strike,
            "atm_distance_points": atm_distance,
            "profile": profile,
            "top_positive_net_gex": [
                {
                    "strike": row["strike"],
                    "net_gex": row["net_gex"],
                }
                for row in positive[:top_n]
            ],
            "top_negative_net_gex": [
                {
                    "strike": row["strike"],
                    "net_gex": row["net_gex"],
                }
                for row in negative[:top_n]
            ],
        }

    # =========================================================
    # LATEST SUMMARY
    # =========================================================

    def get_latest_summary(
        self,
        expiry_date: str,
    ) -> dict:

        latest_timestamp = (
            self.get_latest_timestamp(
                expiry_date
            )
        )

        if latest_timestamp is None:

            raise ValueError(
                "No GEX snapshots found for "
                f"expiry {expiry_date}."
            )

        with self._connect() as connection:

            row = connection.execute(
                """
                SELECT
                    COUNT(*) AS strike_count,

                    SUM(call_gex)
                        AS total_call_gex,

                    SUM(put_gex)
                        AS total_put_gex,

                    SUM(gross_gex)
                        AS total_gross_gex,

                    SUM(net_gex)
                        AS total_net_gex,

                    AVG(spot_price)
                        AS average_spot

                FROM gex_snapshots
                WHERE underlying = ?
                  AND expiry_date = ?
                  AND resolution = ?
                  AND gex_convention = ?
                  AND calculation_version = ?
                  AND timestamp = ?
                """,
                (
                    self.UNDERLYING,
                    expiry_date,
                    self.RESOLUTION,
                    self.GEX_CONVENTION,
                    self.CALCULATION_VERSION,
                    latest_timestamp,
                ),
            ).fetchone()

            max_positive = connection.execute(
                """
                SELECT
                    strike,
                    net_gex
                FROM gex_snapshots
                WHERE underlying = ?
                  AND expiry_date = ?
                  AND resolution = ?
                  AND gex_convention = ?
                  AND calculation_version = ?
                  AND timestamp = ?
                ORDER BY net_gex DESC
                LIMIT 1
                """,
                (
                    self.UNDERLYING,
                    expiry_date,
                    self.RESOLUTION,
                    self.GEX_CONVENTION,
                    self.CALCULATION_VERSION,
                    latest_timestamp,
                ),
            ).fetchone()

            max_negative = connection.execute(
                """
                SELECT
                    strike,
                    net_gex
                FROM gex_snapshots
                WHERE underlying = ?
                  AND expiry_date = ?
                  AND resolution = ?
                  AND gex_convention = ?
                  AND calculation_version = ?
                  AND timestamp = ?
                ORDER BY net_gex ASC
                LIMIT 1
                """,
                (
                    self.UNDERLYING,
                    expiry_date,
                    self.RESOLUTION,
                    self.GEX_CONVENTION,
                    self.CALCULATION_VERSION,
                    latest_timestamp,
                ),
            ).fetchone()

        return {
            "timestamp": latest_timestamp,
            "strike_count": int(
                row["strike_count"] or 0
            ),
            "average_spot": (
                float(row["average_spot"])
                if row["average_spot"] is not None
                else None
            ),
            "total_call_gex": float(
                row["total_call_gex"] or 0.0
            ),
            "total_put_gex": float(
                row["total_put_gex"] or 0.0
            ),
            "total_gross_gex": float(
                row["total_gross_gex"] or 0.0
            ),
            "total_net_gex": float(
                row["total_net_gex"] or 0.0
            ),
            "highest_positive_strike": (
                float(max_positive["strike"])
                if max_positive is not None
                else None
            ),
            "highest_positive_net_gex": (
                float(max_positive["net_gex"])
                if max_positive is not None
                else None
            ),
            "most_negative_strike": (
                float(max_negative["strike"])
                if max_negative is not None
                else None
            ),
            "most_negative_net_gex": (
                float(max_negative["net_gex"])
                if max_negative is not None
                else None
            ),
        }

    # =========================================================
    # FULL PROFILE
    # =========================================================

    def build_profile(
        self,
        expiry_date: str,
        top_n: int = 10,
    ) -> dict:

        profile = self.get_latest_profile(
            expiry_date=expiry_date,
            top_n=top_n,
        )

        summary = self.get_latest_summary(
            expiry_date=expiry_date
        )

        return {
            "underlying": self.UNDERLYING,
            "expiry_date": expiry_date,
            "resolution": self.RESOLUTION,
            "gex_convention": self.GEX_CONVENTION,
            "calculation_version": (
                self.CALCULATION_VERSION
            ),
            "spot_price": profile.get(
                "spot_price"
            ),
            "atm_strike": profile.get(
                "atm_strike"
            ),
            "atm_distance_points": profile.get(
                "atm_distance_points"
            ),
            "summary": summary,
            "profile": profile["profile"],
            "top_positive_net_gex": (
                profile["top_positive_net_gex"]
            ),
            "top_negative_net_gex": (
                profile["top_negative_net_gex"]
            ),
        }

    # =========================================================
    # SAMPLE
    # =========================================================

    def run_sample(self) -> dict:

        return self.build_profile(
            expiry_date="2024-11-28",
            top_n=5,
        )


# =============================================================
# CLI
# =============================================================

def main() -> None:

    parser = argparse.ArgumentParser(
        description=(
            "Kunal Quant - GEX Profile Engine V1"
        )
    )

    parser.add_argument(
        "--sample",
        action="store_true",
        help="Run the 2024-11-28 sample.",
    )

    parser.add_argument(
        "--expiry",
        type=str,
        default=None,
        help="Expiry date YYYY-MM-DD.",
    )

    parser.add_argument(
        "--top-n",
        type=int,
        default=10,
        help="Number of top positive/negative strikes.",
    )

    args = parser.parse_args()

    engine = GEXProfileEngine()

    if args.sample:

        result = engine.run_sample()

    else:

        if not args.expiry:

            raise SystemExit(
                "--expiry is required."
            )

        result = engine.build_profile(
            expiry_date=args.expiry,
            top_n=max(
                1,
                args.top_n,
            ),
        )

    print()
    print("=" * 75)
    print("KUNAL QUANT - GEX PROFILE ENGINE V1")
    print("=" * 75)

    print(
        json.dumps(
            result,
            indent=2,
            default=str,
        )
    )

    print()
    print("=" * 75)


if __name__ == "__main__":
    main()