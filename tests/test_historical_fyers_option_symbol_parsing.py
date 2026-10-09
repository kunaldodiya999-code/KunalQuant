from instruments.instrument_manager import InstrumentManager


def test_historical_unpadded_month_symbol():
    record = InstrumentManager._build_expired_instrument(
        symbol="NSE:NIFTY2110710600CE",
        underlying="NIFTY",
        expiry_date="2021-01-07",
    )
    assert record["option_type"] == "CE"
    assert record["strike"] == 10600.0
    assert record["expiry_date"] == "2021-01-07"


def test_historical_unpadded_month_put():
    record = InstrumentManager._build_expired_instrument(
        symbol="NSE:NIFTY2110720000PE",
        underlying="NIFTY",
        expiry_date="2021-01-07",
    )
    assert record["option_type"] == "PE"
    assert record["strike"] == 20000.0
