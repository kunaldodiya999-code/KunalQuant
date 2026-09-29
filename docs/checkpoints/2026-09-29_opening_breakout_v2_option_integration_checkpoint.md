# Opening Breakout V2 — Real Option Integration Boundary

## Status
In progress / experimental.

## Added
- `backtest/opening_breakout_v2_option_integration.py`
- `tests/test_opening_breakout_v2_option_integration.py`

## Architecture
The bridge connects:
1. Opening Breakout V2 signal event
2. existing Option Contract Resolver V2
3. existing stored FYERS option candles
4. historical marketable-limit fill engine
5. V2 stop/target/risk helpers

## Important blocker intentionally preserved
Resolver V2 returns instrument identity but does not expose lot size. The bridge therefore raises explicitly rather than inventing a lot size.

This is deliberate: the integration must obtain lot size from canonical instrument metadata before calculating quantity.

## Next step
Inspect the existing instrument metadata schema/reader and add a read-only lot-size adapter. Do not modify Resolver V2.
