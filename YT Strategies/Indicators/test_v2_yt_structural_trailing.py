import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RESEARCH_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(RESEARCH_DIR))

from backtest.opening_breakout_v2_fill_engine import HistoricalBar
from execution.opening_breakout_v2_execution import V2ExecutionPolicy
from v2_yt_structural_trailing import StructuralTrailConfig, simulate_structural_exit


def policy():
    return V2ExecutionPolicy(
        entry_buffer_points=1,
        exit_buffer_points=2,
        max_slippage_points=2,
        fill_timeout_seconds=60,
    )


def test_long_structural_stop_ratchets_and_exits():
    bars = [
        HistoricalBar(2, 101, 103, 100, 102),
        HistoricalBar(3, 102, 104, 101, 103),
        HistoricalBar(4, 103, 108, 102, 107),
        HistoricalBar(5, 107, 109, 105, 108),
        HistoricalBar(6, 108, 109, 104, 105),
        HistoricalBar(7, 105, 105, 99, 100),
    ]
    result = simulate_structural_exit(
        bars,
        entry_timestamp=1,
        direction="LONG",
        stop_price=80,
        target_price=140,
        policy=policy(),
        force_exit_timestamp=None,
        config=StructuralTrailConfig(
            atr_period=2,
            swing_atr_mult=1.0,
            stop_atr_buffer=0,
        ),
        entry_price=100,
    )
    assert result.exit.filled
    assert result.exit.reason == "STOP_LOSS"
    assert result.final_stop > 80
    assert result.updates == tuple(sorted(result.updates))


def test_target_is_unchanged_before_trail_update():
    bars = [HistoricalBar(2, 101, 130, 100, 125)]
    result = simulate_structural_exit(
        bars,
        entry_timestamp=1,
        direction="LONG",
        stop_price=80,
        target_price=120,
        policy=policy(),
        force_exit_timestamp=None,
        config=StructuralTrailConfig(),
        entry_price=100,
    )
    assert result.exit.reason == "TARGET"
