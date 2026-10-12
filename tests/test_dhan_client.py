from __future__ import annotations

import unittest

from api.dhan_client import build_rolling_options_payload


class DhanPayloadTests(unittest.TestCase):
    def test_builds_documented_nifty_weekly_request(self):
        payload = build_rolling_options_payload(
            from_date="2026-10-06",
            to_date="2026-10-07",
            expiry_flag="WEEK",
            expiry_code=1,
            strike="ATM",
            option_type="CALL",
        )
        self.assertEqual(payload["exchangeSegment"], "NSE_FNO")
        self.assertEqual(payload["securityId"], 13)
        self.assertEqual(payload["instrument"], "OPTIDX")
        self.assertEqual(payload["drvOptionType"], "CALL")
        self.assertEqual(payload["expiryCode"], 1)
        self.assertIn("oi", payload["requiredData"])
        self.assertIn("strike", payload["requiredData"])

    def test_accepts_far_expiry_code_3(self):
        payload = build_rolling_options_payload(
            from_date="2026-10-06", to_date="2026-10-07", expiry_code=3
        )
        self.assertEqual(payload["expiryCode"], 3)

    def test_rejects_expiry_code_0(self):
        with self.assertRaisesRegex(ValueError, "1, 2, or 3"):
            build_rolling_options_payload(
                from_date="2026-10-06", to_date="2026-10-07", expiry_code=0
            )

    def test_rejects_more_than_30_days(self):
        with self.assertRaisesRegex(ValueError, "30 calendar days"):
            build_rolling_options_payload(
                from_date="2026-01-01", to_date="2026-02-01"
            )

    def test_rejects_bad_strike(self):
        with self.assertRaisesRegex(ValueError, "ATM"):
            build_rolling_options_payload(
                from_date="2026-10-06", to_date="2026-10-07", strike="ATM+11"
            )

    def test_rejects_bad_option_type(self):
        with self.assertRaisesRegex(ValueError, "CALL or PUT"):
            build_rolling_options_payload(
                from_date="2026-10-06", to_date="2026-10-07", option_type="CE"
            )


class FyersExpiredContractParserTests(unittest.TestCase):
    def test_numeric_expiry_is_five_digits(self):
        from scripts.validate_fyers_expired_history import extract_contracts

        response = {"data": {"contracts": {"options": [
            {"symbol": "NSE:NIFTY2691518150CE"},
            {"symbol": "NSE:NIFTY2691518150PE"},
        ]}}}
        contracts = extract_contracts(response)
        self.assertEqual([(c["strike"], c["side"]) for c in contracts],
                         [(18150.0, "CE"), (18150.0, "PE")])


class FyersExpiredHistoryQualityTests(unittest.TestCase):
    def test_numeric_quality_detects_duplicates_and_named_fields(self):
        from scripts.validate_fyers_expired_history import _numeric_quality

        candles = [
            [1000, 100, 110, 90, 105, 1000, 500, 0.5, 0.01],
            [1300, 105, 112, 100, 108, 1200, 520, 0.55, 0.02],
            [1300, 108, 113, 101, 109, 900, 0, 0.60, 0.0],
        ]
        result = _numeric_quality(
            candles,
            ["timestamp", "open", "high", "low", "close", "volume", "oi", "delta", "gamma"],
        )
        self.assertEqual(result["duplicate_timestamps"], 1)
        self.assertEqual(result["invalid_rows"], 0)
        self.assertEqual(result["field_stats"]["oi"]["zero_values"], 1)
        self.assertEqual(result["field_stats"]["delta"]["present_values"], 3)

    def test_numeric_quality_does_not_invent_fields_without_columns(self):
        from scripts.validate_fyers_expired_history import _numeric_quality

        result = _numeric_quality([[1000, 1, 2, 0, 1]], [])
        self.assertEqual(result["columns"], [])
        self.assertEqual(result["field_stats"], {})


if __name__ == "__main__":
    unittest.main()
