import os
import time
from dotenv import load_dotenv
from fyers_apiv3.FyersWebsocket import data_ws


# ============================================================
# KUNAL QUANT
# FYERS DATA WEBSOCKET TEST
# ============================================================

load_dotenv()

APP_ID = os.getenv("FYERS_CLIENT_ID")

with open("fyers_access_token.txt", "r", encoding="utf-8") as file:
    ACCESS_TOKEN = file.read().strip()

if not APP_ID:
    raise RuntimeError("FYERS_CLIENT_ID missing from .env")

if not ACCESS_TOKEN:
    raise RuntimeError("FYERS access token missing")


FULL_ACCESS_TOKEN = f"{APP_ID}:{ACCESS_TOKEN}"

SYMBOLS = [
    "NSE:NIFTY50-INDEX",
    "NSE:NIFTY26SEPFUT",
]


def on_message(message):
    print("\nDATA RECEIVED:")
    print(message)


def on_error(message):
    print("\nWEBSOCKET ERROR:")
    print(message)


def on_close(message):
    print("\nWEBSOCKET CLOSED:")
    print(message)


def on_open():
    print("\nWEBSOCKET CONNECTED")

    data_type = "SymbolUpdate"

    print("Subscribing to:")
    for symbol in SYMBOLS:
        print("  ", symbol)

    fyers.subscribe(
        symbols=SYMBOLS,
        data_type=data_type
    )

    print("\nSubscription request sent.")
    print("Waiting for live data...")


fyers = data_ws.FyersDataSocket(
    access_token=FULL_ACCESS_TOKEN,
    log_path="",
    litemode=False,
    write_to_file=False,
    reconnect=True,
    on_connect=on_open,
    on_close=on_close,
    on_error=on_error,
    on_message=on_message
)


print("=" * 70)
print("KUNAL QUANT - FYERS WEBSOCKET TEST")
print("=" * 70)

print("\nConnecting...")

fyers.connect()

# Keep script alive for 30 seconds
time.sleep(30)

print("\n30-second test finished.")
print("Closing WebSocket...")

try:
    fyers.close_connection()
except Exception as error:
    print("Close message:", error)

print("\n" + "=" * 70)
print("WEBSOCKET TEST COMPLETE")
print("=" * 70)