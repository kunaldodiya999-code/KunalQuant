"""Loopback-only HTTP controls for the active paper-trading session.

This server is deliberately bound to 127.0.0.1 and has no broker/order endpoints.
It serves the settings UI, persists validated settings, reports paper state, and
allows explicit manual-stop updates on an open simulated position.
"""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading
from typing import Any, Callable

from paper_trading.settings import PaperTradingSettings

_DEFAULT_SETTINGS_PATH = Path("data/paper_trading/settings.json")


class PaperControlService:
    def __init__(
        self,
        *,
        session: Any,
        settings_path: str | Path = _DEFAULT_SETTINGS_PATH,
        host: str = "127.0.0.1",
        port: int = 8765,
    ) -> None:
        if host not in {"127.0.0.1", "localhost"}:
            raise ValueError("Paper controls must bind to loopback only.")
        self.session = session
        self.settings_path = Path(settings_path)
        self.host = host
        self.port = int(port)
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._lock = threading.RLock()

    def start(self) -> None:
        with self._lock:
            if self._server is not None:
                return
            service = self

            class Handler(BaseHTTPRequestHandler):
                def _json(self, status: int, payload: Any) -> None:
                    body = json.dumps(payload, default=str).encode("utf-8")
                    self.send_response(status)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    self.wfile.write(body)

                def _body(self) -> dict[str, Any]:
                    length = int(self.headers.get("Content-Length", "0"))
                    if length < 1 or length > 64_000:
                        raise ValueError("Request body must be between 1 and 64000 bytes.")
                    value = json.loads(self.rfile.read(length))
                    if not isinstance(value, dict):
                        raise ValueError("Request body must be a JSON object.")
                    return value

                def do_GET(self) -> None:  # noqa: N802
                    if self.path in {"/", "/settings"}:
                        page = (Path(__file__).with_name("settings_ui.html")).read_bytes()
                        self.send_response(200)
                        self.send_header("Content-Type", "text/html; charset=utf-8")
                        self.send_header("Content-Length", str(len(page)))
                        self.send_header("Cache-Control", "no-store")
                        self.end_headers()
                        self.wfile.write(page)
                        return
                    if self.path == "/api/settings":
                        try:
                            settings = PaperTradingSettings.load(service.settings_path)
                            self._json(200, settings.__dict__)
                        except (ValueError, OSError, json.JSONDecodeError) as exc:
                            self._json(400, {"error": str(exc)})
                        return
                    if self.path == "/api/status":
                        self._json(200, service.status())
                        return
                    self._json(404, {"error": "Not found"})

                def do_POST(self) -> None:  # noqa: N802
                    try:
                        payload = self._body()
                        if self.path == "/api/settings":
                            settings = PaperTradingSettings(**payload)
                            settings.save(service.settings_path)
                            service.apply_settings(settings)
                            self._json(200, {"saved": True, "settings": settings.__dict__})
                            return
                        if self.path == "/api/manual-stop":
                            strategy = payload.get("strategy_id")
                            stop = payload.get("stop_loss")
                            settings = PaperTradingSettings.load(service.settings_path)
                            if not settings.trailing_stop_enabled:
                                raise ValueError("Manual trailing-stop controls are disabled in settings.")
                            trade = service.session.engine.update_manual_stop(
                                strategy_id=strategy,
                                stop_loss=float(stop),
                                allow_loosen=settings.manual_tsl_can_loosen,
                            )
                            self._json(200, {
                                "updated": True,
                                "strategy_id": trade.strategy_id.value,
                                "symbol": trade.position.symbol,
                                "entry_price": trade.position.entry_price,
                                "stop_loss": trade.position.stop_loss,
                            })
                            return
                    except (ValueError, TypeError, KeyError, OSError, json.JSONDecodeError) as exc:
                        self._json(400, {"error": str(exc)})
                        return
                    self._json(404, {"error": "Not found"})

                def log_message(self, _format: str, *_args: Any) -> None:
                    return

            self._server = ThreadingHTTPServer((self.host, self.port), Handler)
            self._server.daemon_threads = True
            self._thread = threading.Thread(
                target=self._server.serve_forever,
                name="kunal-paper-controls",
                daemon=True,
            )
            self._thread.start()

    def stop(self) -> None:
        with self._lock:
            server, thread = self._server, self._thread
            self._server = None
            self._thread = None
        if server is not None:
            server.shutdown()
            server.server_close()
        if thread is not None:
            thread.join(timeout=2)

    def status(self) -> dict[str, Any]:
        engine = self.session.engine
        trades = []
        for trade in engine.all_trades():
            trades.append({
                "strategy_id": trade.strategy_id.value,
                "symbol": trade.position.symbol,
                "direction": getattr(trade.position.direction, "value", trade.position.direction),
                "entry_timestamp": trade.entry_timestamp,
                "entry_price": trade.position.entry_price,
                "stop_loss": trade.position.stop_loss,
                "target": trade.position.target,
                "remaining_quantity": trade.position.remaining_quantity,
                "remaining_lots": trade.position.remaining_lots,
                "closed": trade.closed,
                "gross_pnl": trade.gross_pnl,
            })
        return {
            "mode": "paper_only",
            "feed": self.session.feed.status().__dict__,
            "available_cash": engine.available_cash(),
            "alerts": list(self.session.alerts),
            "trades": trades,
        }

    def apply_settings(self, settings: PaperTradingSettings) -> None:
        """Apply risk settings to future entries; open positions keep their stop."""
        engine = self.session.engine
        lifecycle = engine.lifecycle
        cfg = getattr(lifecycle, "config", None)
        if cfg is not None:
            from dataclasses import replace
            lifecycle.config = replace(
                cfg,
                allocation=settings.allocation_amount,
                stop_loss_pct=settings.stop_loss_pct / 100.0,
                target_rr=settings.partial_trigger_r,
                partial_exit_fraction=settings.partial_exit_pct / 100.0,
                target_enabled=settings.partial_exit_enabled,
                partial_exit_enabled=settings.partial_exit_enabled,
                single_lot_partial_mode=settings.single_lot_partial_mode,
            )
        engine.starting_capital = settings.starting_capital
        engine.allocation_pct = settings.allocation_pct
        self.session.coordinator.entry_cutoff = __import__("datetime").time.fromisoformat(settings.entry_cutoff)
        # Forced-exit timing and daily-loss cutoff are not hot-applied until
        # their watchdog enforcement is active; do not imply otherwise.


__all__ = ["PaperControlService"]
