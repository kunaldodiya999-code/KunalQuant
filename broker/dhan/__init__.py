"""DhanHQ broker integration boundary for KunalQuant.

This package is intentionally broker-specific and does not change the
broker-neutral backtest/strategy layers.
"""

from .client import DhanClient
from .config import DhanClientConfig

__all__ = ["DhanClient", "DhanClientConfig"]
