from scripts.acquire_required_nifty_options import (
    _extract_symbols,
    _option_type_from_symbol,
    _strike_from_symbol,
)

def test_extract_symbols_and_parse_contract():
    response = {
        "data": {
            "symbols": [
                "NSE:NIFTY2692223250CE",
                "NSE:NIFTY2692223250PE",
                "ignore-me",
            ]
        }
    }
    symbols = _extract_symbols(response)
    assert "NSE:NIFTY2692223250CE" in symbols
    assert "NSE:NIFTY2692223250PE" in symbols
    assert _strike_from_symbol("NSE:NIFTY2692223250CE") == 23250
    assert _option_type_from_symbol("NSE:NIFTY2692223250PE") == "PE"

def test_extract_symbols_ignores_non_option_values():
    assert _extract_symbols({"data": {"symbols": ["NSE:NIFTY50-INDEX", "x"]}}) == set()
