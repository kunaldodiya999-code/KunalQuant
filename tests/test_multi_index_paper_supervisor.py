import pytest

from paper_trading.instrument_universe import list_enabled_underlyings
from paper_trading.multi_index_supervisor import (
    IndexSessionSpec,
    MultiIndexPaperSupervisor,
)


@pytest.mark.parametrize(
    "key,symbol,lot_size",
    [
        ("NIFTY50", "NSE:NIFTY50-INDEX", 65),
        ("SENSEX", "BSE:SENSEX-INDEX", 20),
        ("BANKNIFTY", "NSE:NIFTYBANK-INDEX", 30),
    ],
)
def test_index_session_spec_requires_known_index_and_explicit_metadata(key, symbol, lot_size):
    spec = IndexSessionSpec(key, symbol, lot_size)
    assert spec.underlying_key == key
    assert spec.underlying_symbol == symbol
    assert spec.lot_size == lot_size


def test_index_session_spec_rejects_unknown_instrument_and_missing_metadata():
    with pytest.raises(ValueError, match="Unsupported"):
        IndexSessionSpec("GOLD", "MCX:GOLD", 1)
    with pytest.raises(ValueError, match="symbol"):
        IndexSessionSpec("NIFTY50", " ", 65)
    with pytest.raises(ValueError, match="lot size"):
        IndexSessionSpec("NIFTY50", "NSE:NIFTY50-INDEX", 0)


def test_supervisor_rejects_duplicate_index_sessions():
    class DummyClient:
        pass

    with pytest.raises(ValueError, match="Duplicate"):
        MultiIndexPaperSupervisor.build(
            client=DummyClient(),
            specs=(
                IndexSessionSpec("NIFTY50", "NSE:NIFTY50-INDEX", 65),
                IndexSessionSpec("NIFTY50", "NSE:NIFTY50-INDEX", 65),
            ),
        )


def test_supervisor_closes_already_started_sessions_if_next_start_fails():
    class FakeSession:
        def __init__(self, fail=False):
            self.fail = fail
            self.started = False
            self.closed = False

        def start(self):
            self.started = True
            if self.fail:
                raise RuntimeError("socket failed")

        def close(self):
            self.closed = True

    first = FakeSession()
    second = FakeSession(fail=True)
    supervisor = MultiIndexPaperSupervisor(
        {"NIFTY50": first, "SENSEX": second}
    )
    with pytest.raises(RuntimeError, match="socket failed"):
        supervisor.start()
    assert first.started and first.closed
    assert second.started and second.closed
