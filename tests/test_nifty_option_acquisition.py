from datetime import date
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.acquire_nifty_option_candles import build_range


def test_build_range_90_days():
    assert build_range("2021-01-07", 90) == ("2020-10-09", "2021-01-07")


def test_build_range_handles_leap_year():
    assert build_range("2024-03-01", 1) == ("2024-02-29", "2024-03-01")


def test_build_range_rejects_negative_days():
    try:
        build_range("2021-01-07", -1)
    except ValueError:
        return
    raise AssertionError("negative days_before must fail")
