# KTMI Universal LITE — performance variant

This is an **isolated performance variant** of the locked/reference KTMI
Universal V1 FINAL.

## Why

TradingView reports the reference script as a heavy script and can approach the
20-second runtime limit, especially on mobile.

The reference implementation's `getMA()` calculates **SMA + EMA + WMA + RMA +
HMA on every call**, then selects one result. It also calculates ROC, TRIX and
MACD paths even when only one calculation method is selected. The three modules
therefore perform substantially more work than necessary.

## Optimization

The LITE version:

1. Calculates only the selected moving-average type.
2. Calculates only the selected ROC/TRIX/MACD path.
3. Skips disabled momentum modules.
4. Keeps the same chart symbol/timeframe model.
5. Keeps the same display multiplier, short inversion, trigger conditions,
   confluence conditions, fills, plots and alerts.
6. Keeps the momentum table limited to a last-bar update.

## Reference safety

- `KTMI_Universal_V1_FINAL.pine` is not modified.
- Locked KTMI V6 is not modified.
- This file is research/performance work only.

## Validation requirement

Before replacing the current chart script, compare LITE against the reference
on the same symbol/timeframe and settings. We should compare:
- Momentum Speed
- Momentum Signal
- Long Speed/Signal
- Short Speed/Signal
- all trigger arrows
- confluence
- alerts

If parity is confirmed, LITE can become the preferred TradingView chart version
without changing the underlying KTMI calculation definition.
