import unittest

from scripts.fyers_market_data_smoke_test import _normalize_symbols


class FyersMarketDataSmokeTestSymbolParsingTests(unittest.TestCase):
    def test_comma_separated_symbols_are_split(self):
        self.assertEqual(
            _normalize_symbols(
                ["NSE:NIFTY26OCT22700CE,NSE:NIFTY26OCT22700PE"]
            ),
            ("NSE:NIFTY26OCT22700CE", "NSE:NIFTY26OCT22700PE"),
        )

    def test_repeated_arguments_and_commas_are_supported(self):
        self.assertEqual(
            _normalize_symbols(
                [
                    "NSE:NIFTY50-INDEX",
                    "NSE:NIFTYBANK-INDEX,NSE:NIFTY50-INDEX",
                ]
            ),
            ("NSE:NIFTY50-INDEX", "NSE:NIFTYBANK-INDEX"),
        )

    def test_whitespace_and_empty_items_are_ignored(self):
        self.assertEqual(
            _normalize_symbols([" NSE:NIFTY50-INDEX, , NSE:NIFTYBANK-INDEX "]),
            ("NSE:NIFTY50-INDEX", "NSE:NIFTYBANK-INDEX"),
        )

    def test_empty_input_returns_no_symbols(self):
        self.assertEqual(_normalize_symbols([" ", ","]), ())


if __name__ == "__main__":
    unittest.main()
