"""Explicit multi-index paper-session supervisor.

This is paper-only orchestration. Each underlying receives its own session,
CSV recovery journal, pending-entry journal, resolver and engine. Lot sizes and
FYERS index symbols must be supplied from current broker/exchange metadata;
the module intentionally does not guess them.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from api.fyers_client import FyersClient
from paper_trading.instrument_universe import get_underlying, list_enabled_underlyings
from paper_trading.session import PaperSession, PaperSessionConfig, build_paper_session


@dataclass(frozen=True)
class IndexSessionSpec:
    underlying_key: str
    underlying_symbol: str
    lot_size: int

    def __post_init__(self) -> None:
        get_underlying(self.underlying_key)
        if not self.underlying_symbol.strip():
            raise ValueError("A verified FYERS underlying symbol is required.")
        if self.lot_size < 1:
            raise ValueError("A verified current lot size is required.")


class MultiIndexPaperSupervisor:
    """Build/start/close isolated paper sessions for configured indices."""

    def __init__(self, sessions: Mapping[str, PaperSession]) -> None:
        if not sessions:
            raise ValueError("At least one paper session is required.")
        self.sessions = dict(sessions)
        self._started: list[str] = []

    @classmethod
    def build(
        cls,
        *,
        client: FyersClient,
        specs: tuple[IndexSessionSpec, ...],
        base_output_dir: str | Path = "data/paper_trading",
        database_path: str | Path | None = None,
        resolution_minutes: int = 3,
        socket_factory=None,
    ) -> "MultiIndexPaperSupervisor":
        seen: set[str] = set()
        sessions: dict[str, PaperSession] = {}
        base = Path(base_output_dir)
        for spec in specs:
            key = get_underlying(spec.underlying_key).key
            if key in seen:
                raise ValueError(f"Duplicate paper session configured for {key}.")
            seen.add(key)
            output_dir = base / key.lower()
            config = PaperSessionConfig(
                lot_size=spec.lot_size,
                underlying_symbol=spec.underlying_symbol,
                underlying_key=key,
                database_path=database_path,
                output_dir=output_dir,
                pending_journal_path=output_dir / "pending_entries.csv",
                resolution_minutes=resolution_minutes,
            )
            sessions[key] = build_paper_session(
                client=client,
                config=config,
                socket_factory=socket_factory,
            )
        # This supervisor supports a partial set while instruments are being
        # verified, but never silently substitutes one index for another.
        if not sessions:
            raise ValueError("No index paper sessions were configured.")
        return cls(sessions)

    def start(self) -> None:
        """Start configured paper feeds; close already-started feeds on failure."""
        try:
            for key, session in self.sessions.items():
                self._started.append(key)
                session.start()
        except Exception:
            self.close()
            raise

    def close(self) -> None:
        errors: list[Exception] = []
        for key in reversed(self._started):
            try:
                self.sessions[key].close()
            except Exception as exc:  # attempt to close every started session
                errors.append(exc)
        self._started.clear()
        if errors:
            raise RuntimeError(
                f"Failed to close {len(errors)} paper session(s)."
            ) from errors[0]


__all__ = ["IndexSessionSpec", "MultiIndexPaperSupervisor"]
