"""Validated, persisted settings for buyer-only paper trading.

This module is additive. It never configures broker order submission.
Settings changes apply to new trades; open positions retain their recorded entry
and stop unless the operator explicitly adjusts their manual trailing stop.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import time
from math import isfinite
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class PaperTradingSettings:
    starting_capital: float = 100_000.0
    allocation_pct: int = 20
    stop_loss_pct: float = 30.0
    partial_exit_enabled: bool = True
    partial_trigger_r: float = 2.0
    partial_exit_pct: float = 50.0
    single_lot_partial_mode: str = "close_all"
    trailing_stop_enabled: bool = True
    trailing_stop_mode: str = "manual"
    manual_tsl_can_loosen: bool = True
    forced_exit_enabled: bool = True
    entry_cutoff: str = "15:00"
    forced_exit_time: str = "15:10"
    stale_exit_policy: str = "wait"
    available_capital_mode: str = "cash"
    daily_loss_cutoff_enabled: bool = False
    daily_loss_limit: float | None = None
    settings_apply_to: str = "new_trades"

    def __post_init__(self) -> None:
        if not isfinite(self.starting_capital) or self.starting_capital <= 0:
            raise ValueError("starting_capital must be finite and positive")
        if not 10 <= self.allocation_pct <= 100 or self.allocation_pct % 10:
            raise ValueError("allocation_pct must be from 10 to 100 in 10% steps")
        if not 0 < self.stop_loss_pct < 100:
            raise ValueError("stop_loss_pct must be between 0 and 100")
        if not 0 < self.partial_trigger_r:
            raise ValueError("partial_trigger_r must be positive")
        if not 0 < self.partial_exit_pct < 100:
            raise ValueError("partial_exit_pct must be between 0 and 100")
        choices = {
            "single_lot_partial_mode": {"close_all", "skip", "require_two_lots"},
            "trailing_stop_mode": {"manual"},
            "stale_exit_policy": {"wait"},
            "available_capital_mode": {"cash"},
            "settings_apply_to": {"new_trades"},
        }
        for field_name, allowed in choices.items():
            if getattr(self, field_name) not in allowed:
                raise ValueError(f"Invalid {field_name}: {getattr(self, field_name)!r}")
        for field_name in ("entry_cutoff", "forced_exit_time"):
            try:
                time.fromisoformat(getattr(self, field_name))
            except ValueError as exc:
                raise ValueError(f"{field_name} must be HH:MM") from exc
        if self.entry_cutoff >= self.forced_exit_time:
            raise ValueError("entry_cutoff must be earlier than forced_exit_time")
        if self.daily_loss_cutoff_enabled and (
            self.daily_loss_limit is None or not isfinite(self.daily_loss_limit)
            or self.daily_loss_limit <= 0
        ):
            raise ValueError("daily_loss_limit must be positive when cutoff is enabled")
        if not self.daily_loss_cutoff_enabled and self.daily_loss_limit is not None and (
            not isfinite(self.daily_loss_limit) or self.daily_loss_limit <= 0
        ):
            raise ValueError("daily_loss_limit must be positive when provided")

    @property
    def allocation_amount(self) -> float:
        return self.starting_capital * self.allocation_pct / 100.0

    @classmethod
    def load(cls, path: str | Path) -> "PaperTradingSettings":
        settings_path = Path(path)
        if not settings_path.exists():
            settings = cls()
            settings.save(settings_path)
            return settings
        with settings_path.open("r", encoding="utf-8") as handle:
            payload: Any = json.load(handle)
        if not isinstance(payload, dict):
            raise ValueError("Paper settings file must contain a JSON object")
        return cls(**payload)

    def save(self, path: str | Path) -> None:
        settings_path = Path(path)
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = settings_path.with_suffix(settings_path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(asdict(self), indent=2) + "\n", encoding="utf-8"
        )
        temporary.replace(settings_path)


__all__ = ["PaperTradingSettings"]
