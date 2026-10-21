import json
from urllib.request import Request, urlopen

from paper_trading.buyer_lifecycle import BuyerLifecycleConfig, BuyerOptionTradeLifecycle
from paper_trading.control_server import PaperControlService
from paper_trading.coordinator import PaperExecutionCoordinator
from paper_trading.engine import PaperStrategyId, PaperTradingEngine
from paper_trading.settings import PaperTradingSettings


class _Feed:
    def status(self):
        class Status:
            connected = False
            subscribed_symbols = ()
            messages_received = 0
            messages_rejected_by_quote_cache = 0
            last_error = None
        return Status()


class _Session:
    def __init__(self):
        self.engine = PaperTradingEngine(
            lifecycle=BuyerOptionTradeLifecycle(
                BuyerLifecycleConfig(allocation=20_000, lot_size=25)
            ),
            starting_capital=100_000,
            allocation_pct=20,
        )
        self.engine.open_position(
            strategy_id=PaperStrategyId.STRATEGY_A,
            direction="LONG",
            symbol="NSE:NIFTYCE",
            entry_price=100,
            timestamp=100,
        )
        self.coordinator = type("Coordinator", (), {"entry_cutoff": None})()
        self.feed = _Feed()
        self.alerts = []


def _request(url, method="GET", body=None):
    data = None if body is None else json.dumps(body).encode()
    request = Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=3) as response:
        return json.loads(response.read())


def test_control_api_loads_and_saves_validated_settings_and_status(tmp_path):
    session = _Session()
    service = PaperControlService(session=session, settings_path=tmp_path / "settings.json", port=0)
    service.start()
    try:
        port = service._server.server_address[1]
        base = f"http://127.0.0.1:{port}"
        initial = _request(base + "/api/settings")
        assert initial["starting_capital"] == 100_000
        changed = PaperTradingSettings(allocation_pct=30)
        saved = _request(base + "/api/settings", "POST", changed.__dict__)
        assert saved["saved"] is True
        assert session.engine.allocation_pct == 30
        assert session.engine.lifecycle.config.allocation == 30_000
        status = _request(base + "/api/status")
        assert status["mode"] == "paper_only"
        assert status["available_cash"] == 90_000
        assert len([t for t in status["trades"] if not t["closed"]]) == 1
    finally:
        service.stop()


def test_control_api_manual_stop_updates_only_open_paper_position(tmp_path):
    session = _Session()
    service = PaperControlService(session=session, settings_path=tmp_path / "settings.json", port=0)
    service.start()
    try:
        port = service._server.server_address[1]
        result = _request(
            f"http://127.0.0.1:{port}/api/manual-stop",
            "POST",
            {"strategy_id": "KTMI_LONG_SHORT_SPEED", "stop_loss": 75},
        )
        assert result["updated"] is True
        assert result["stop_loss"] == 75
        assert session.engine.open_trade(PaperStrategyId.STRATEGY_A).position.stop_loss == 75
    finally:
        service.stop()
