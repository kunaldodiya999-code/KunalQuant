from __future__ import annotations

import unittest

from api.dhan_client import build_rolling_options_payload


class DhanPayloadTests(unittest.TestCase):
    def test_builds_documented_nifty_weekly_request(self):
        payload = build_rolling_options_payload(
            from_date="2026-10-06",
            to_date="2026-10-07",
            expiry_flag="WEEK",
            expiry_code=0,
            strike="ATM",
            option_type="CALL",
        )
        self.assertEqual(payload["exchangeSegment"], "NSE_FNO")
        self.assertEqual(payload["securityId"], 13)
        self.assertEqual(payload["instrument"], "OPTIDX")
        self.assertEqual(payload["drvOptionType"], "CALL")
        self.assertIn("oi", payload["requiredData"])
        self.assertIn("strike", payload["requiredData"])

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


if __name__ == "__main__":
    unittest.main()
