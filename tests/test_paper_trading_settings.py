import json
import pytest

from paper_trading.settings import PaperTradingSettings


def test_default_paper_settings_match_approved_controls():
    s = PaperTradingSettings()
    assert s.starting_capital == 100_000
    assert s.allocation_pct == 20
    assert s.allocation_amount == 20_000
    assert s.stop_loss_pct == 30
    assert s.partial_exit_enabled is True
    assert s.partial_trigger_r == 2
    assert s.partial_exit_pct == 50
    assert s.single_lot_partial_mode == "close_all"
    assert s.trailing_stop_enabled is True
    assert s.manual_tsl_can_loosen is True
    assert s.forced_exit_enabled is True
    assert s.entry_cutoff == "15:00"
    assert s.forced_exit_time == "15:10"
    assert s.stale_exit_policy == "wait"
    assert s.available_capital_mode == "cash"
    assert s.daily_loss_cutoff_enabled is False
    assert s.settings_apply_to == "new_trades"


@pytest.mark.parametrize("kwargs", [
    {"starting_capital": 0},
    {"allocation_pct": 15},
    {"allocation_pct": 110},
    {"stop_loss_pct": 100},
    {"partial_trigger_r": 0},
    {"partial_exit_pct": 100},
    {"entry_cutoff": "15:10", "forced_exit_time": "15:00"},
    {"stale_exit_policy": "estimate"},
    {"available_capital_mode": "equity"},
])
def test_rejects_invalid_settings(kwargs):
    with pytest.raises(ValueError):
        PaperTradingSettings(**kwargs)


def test_settings_round_trip_and_create_defaults(tmp_path):
    path = tmp_path / "nested" / "settings.json"
    defaults = PaperTradingSettings.load(path)
    assert defaults == PaperTradingSettings()
    changed = PaperTradingSettings(allocation_pct=40)
    changed.save(path)
    assert PaperTradingSettings.load(path) == changed
    assert json.loads(path.read_text(encoding="utf-8"))["allocation_pct"] == 40
