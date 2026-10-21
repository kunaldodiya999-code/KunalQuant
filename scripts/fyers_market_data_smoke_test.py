"""Safely smoke-test FYERS WebSocket market data without placing orders.

Run during market hours after refreshing the local FYERS access token:
    python scripts/fyers_market_data_smoke_test.py --seconds 60

This script only creates a market-data socket and subscribes symbols. It does
not call order, funds, positions, or trade APIs. It prints compact payload
samples and quote freshness diagnostics, never the access token.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import threading
import time
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from api.fyers_client import FyersClient
from market_data.fyers_quote_cache import FyersQuoteCache


DEFAULT_SYMBOLS = ("NSE:NIFTY50-INDEX", "NSE:NIFTYBANK-INDEX")


def _safe_value(value: Any, limit: int = 180) -> str:
    """Return compact diagnostic text without dumping arbitrarily large data."""
    try:
        rendered = json.dumps(value, default=str, sort_keys=True)
    except (TypeError, ValueError):
        rendered = repr(value)
    return rendered[:limit]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=int, default=60, help="Capture duration (default: 60 seconds).")
    parser.add_argument(
        "--symbols",
        nargs="+",
        default=list(DEFAULT_SYMBOLS),
        help="FYERS symbols to subscribe; defaults to NIFTY 50 and NIFTY BANK indices.",
    )
    args = parser.parse_args()
    if not 5 <= args.seconds <= 600:
        parser.error("--seconds must be between 5 and 600.")
    symbols = tuple(dict.fromkeys(s.strip() for s in args.symbols if s.strip()))
    if not symbols:
        parser.error("Provide at least one non-empty symbol.")

    client = FyersClient()
    cache = FyersQuoteCache()
    stop_event = threading.Event()
    lock = threading.Lock()
    quote_counts: dict[str, int] = {}
    status_counts: dict[str, int] = {}
    payload_shapes: dict[str, tuple[str, ...]] = {}
    errors: list[str] = []
    socket_holder: dict[str, Any] = {}
    connected = threading.Event()

    def on_message(message: Any) -> None:
        # FYERS sends control/status frames (cn, ful, sub, etc.) through the
        # same callback as market data. Quote frame type can vary by feed
        # (the live index callback observed type="if"), so identify quotes by
        # their actual symbol and ltp fields rather than a single type value.
        is_quote = (
            isinstance(message, dict)
            and isinstance(message.get("symbol"), str)
            and message.get("ltp") is not None
        )
        if not is_quote:
            kind = str(message.get("type", "<missing-type>"))
            with lock:
                status_counts[kind] = status_counts.get(kind, 0) + 1
                count = status_counts[kind]
            if count <= 3:
                print(f"STATUS type={kind!r} payload={_safe_value(message)}")
            return

        symbol = message.get("symbol") if isinstance(message, dict) else None
        label = symbol if isinstance(symbol, str) else "<non-dict-or-no-symbol>"
        accepted = cache.update(message)
        with lock:
            quote_counts[label] = quote_counts.get(label, 0) + 1
            if isinstance(message, dict):
                payload_shapes[label] = tuple(sorted(str(k) for k in message.keys()))
            count = quote_counts[label]
        if count <= 3:
            print(
                f"TICK sample={count} symbol={label!r} "
                f"keys={payload_shapes.get(label, ())} "
                f"quote_cache_accepted={accepted} "
                f"sample={_safe_value(message)}"
            )

    def on_error(error: Any, *_args: Any, **_kwargs: Any) -> None:
        error_text = str(error)
        with lock:
            errors.append(error_text)
        print(f"SOCKET_ERROR {error_text[:500]}")

    def on_close(*args_: Any, **kwargs_: Any) -> None:
        print(f"SOCKET_CLOSED args={_safe_value(args_)} kwargs={_safe_value(kwargs_)}")
        stop_event.set()

    def on_connect(*_args: Any, **_kwargs: Any) -> None:
        try:
            socket = socket_holder.get("socket")
            if socket is None:
                raise RuntimeError("Connect callback fired before socket was stored.")
            socket.subscribe(symbols=list(symbols), data_type="SymbolUpdate")
            connected.set()
            print(f"CONNECTED subscribed={symbols}")
        except Exception as exc:
            on_error(exc)

    print("KUNAL QUANT — FYERS MARKET-DATA-ONLY SMOKE TEST")
    print(f"symbols={symbols}")
    print(f"duration_seconds={args.seconds}")
    print("order_api_calls=NONE")

    socket = client.create_data_socket(
        on_message=on_message,
        on_error=on_error,
        on_close=on_close,
        on_connect=on_connect,
        reconnect=True,
        lite_mode=False,
    )
    socket_holder["socket"] = socket
    started_at = time.monotonic()
    try:
        socket.connect()
        if not connected.wait(timeout=15):
            print("WARNING: no successful connect/subscription callback within 15 seconds.")
        deadline = started_at + args.seconds
        while not stop_event.is_set() and time.monotonic() < deadline:
            time.sleep(0.2)
    except KeyboardInterrupt:
        print("Interrupted by user.")
    except Exception as exc:
        on_error(exc)
    finally:
        close = getattr(socket, "close", None)
        if callable(close):
            try:
                close()
            except Exception as exc:
                on_error(f"Socket close failed: {exc}")
        time.sleep(0.5)

    print("\nSUMMARY")
    print(f"connected_callback_received={connected.is_set()}")
    print(f"elapsed_seconds={time.monotonic() - started_at:.1f}")
    print(f"market_messages_by_symbol={dict(quote_counts)}")
    print(f"status_messages_by_type={dict(status_counts)}")
    print(f"quote_cache_symbols={cache.symbols()}")
    print(f"quote_cache_rejected_market_messages={cache.rejected_messages}")
    print(f"socket_errors={len(errors)}")
    fresh_quotes = 0
    for symbol in cache.symbols():
        snapshot = cache.snapshot(symbol)
        if snapshot is None:
            continue
        try:
            quote = cache.get_quote(
                symbol,
                decision_timestamp=int(time.time()),
                max_exchange_age_seconds=10,
                max_receive_age_seconds=10,
            )
            freshness = "FRESH_WITHIN_10S"
            price = quote["lp"]
            fresh_quotes += 1
        except (LookupError, ValueError, KeyError, TypeError) as exc:
            freshness = f"NOT_FRESH: {exc}"
            price = snapshot.last_price
        print(
            f"quote symbol={symbol!r} price={price} "
            f"exchange_timestamp={snapshot.exchange_timestamp} "
            f"received_at={snapshot.received_at:.3f} freshness={freshness}"
        )

    if not connected.is_set() or not quote_counts:
        print("RESULT=INCOMPLETE — inspect token, market hours, symbol names, and SDK logs.")
        return 1
    if cache.rejected_messages:
        print("RESULT=DATA_RECEIVED_WITH_INVALID_MARKET_TICKS — inspect quote payloads/timestamps.")
        return 2
    if fresh_quotes != len(cache.symbols()):
        print("RESULT=CONNECTED_BUT_QUOTES_NOT_FRESH — do not use this feed for paper entries until investigated.")
        return 3
    print("RESULT=DATA_RECEIVED_AND_FRESH — still review timestamps before any paper session.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
