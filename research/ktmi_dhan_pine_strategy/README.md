# KTMI -> Dhan Pine Strategy Prototype

Status: EXPERIMENTAL

This folder contains a Pine translation prototype for validating the locked
KunalQuant KTMI Universal calculation and the existing KTMI Strategy A trigger.

## Signal definition

Strategy A:

- Long Speed crosses UP through +0.50 -> BUY_CALL
- Short Speed crosses UP through +0.50 -> BUY_PUT

This matches the existing KunalQuant trigger definition in
strategies/ktmi_trigger_strategy.py.

The KTMI calculation translation is based on
indicators/ktmi/universal.py and indicators/ktmi/config.py.

## Execution boundary

This Pine script intentionally produces signals and alerts only.

A Pine strategy order is associated with the chart/instrument being tested. It
does not by itself perform the dynamic option contract resolution we need:
nearest expiry, strike selection, option security ID, lot sizing, fill handling,
broker-state reconciliation, and option-specific risk management.

Proposed production path:

NIFTY chart
  -> KTMI Pine calculation
  -> BUY_CALL / BUY_PUT alert
  -> Dhan/KunalQuant execution adapter
  -> dynamic option contract resolution
  -> CE/PE order

Dhan's Option Chain API provides option contracts plus LTP, bid/ask, OI,
Greeks and related market data. The execution layer should own contract
selection.

## Parity validation required

Do not treat this Pine translation as production-equivalent yet.

1. Paste ktmi_universal_dhan_signal.pine into the Dhan/TradingView Pine editor.
2. Run it on the same symbol/timeframe used by the existing KTMI reference.
3. Export or otherwise capture the plotted Long Speed, Long Signal, Short Speed
   and Short Signal values.
4. Compare those values against the Python KTMI engine.
5. Compare every BUY_CALL / BUY_PUT bar against the Python
   KTMITriggerStrategy output.

The repository already contains tests/ktmi_pine_parity_test.py for
TradingView/Python numerical parity.

No locked KTMI production code is modified by this prototype.
