# KTMI -> Dhan Pine Option Signal Lab

Status: EXPERIMENTAL

This folder contains an isolated Pine research layer for validating KTMI
Universal and testing configurable option-entry conditions.

## Default entry model

CALL / long option:
- Long Speed crosses UP through +0.50 = enabled
- Momentum Speed crosses UP through +0.50 = disabled

PUT / long option:
- Short Speed crosses UP through +0.50 = enabled
- Momentum Speed crosses DOWN through -0.50 = disabled

Each condition has its own ON/OFF switch.

Each side has a combination selector:
- ANY: any enabled condition can trigger the side.
- ALL: all enabled conditions must cross on the same candle.

All four trigger zones are independently adjustable:
- Long Speed trigger
- Short Speed trigger
- Momentum LONG trigger
- Momentum PUT trigger

This is deliberately a research parameter layer. The locked Python
KTMI Universal and existing Strategy A/B definitions are not modified.

## Important strategy interpretation

"BUY CALL" and "BUY PUT" mean buying the corresponding option as a long
position. The PUT condition is not a short option position.

The crossing events are:
- Long Speed: upward crossing
- Momentum LONG: upward crossing
- Short Speed: upward crossing
- Momentum PUT: downward crossing

## Optimization

The four trigger values are intended to become optimizer dimensions. Examples:

- Long Speed: 0.30 to 0.80
- Short Speed: 0.30 to 0.80
- Momentum LONG: 0.30 to 0.80
- Momentum PUT: -0.80 to -0.30

The exact ranges are research choices and are not yet approved production
parameters.

The optimizer should test:
1. individual condition ON/OFF combinations,
2. trigger-zone combinations,
3. ANY versus ALL,
4. then OOS stability and parameter perturbation.

Do not select a configuration only because it produces the highest in-sample
P&L.

## Execution boundary

This Pine script intentionally produces signals and alerts only.

It does not dynamically select:
- expiry,
- strike,
- option security ID,
- lot quantity,
- liquidity constraints,
- fill behavior,
- broker-state reconciliation,
- option-specific SL/target.

Proposed path:

NIFTY chart
  -> KTMI Pine calculation
  -> BUY_CALL / BUY_PUT alert
  -> Dhan/KunalQuant execution adapter
  -> dynamic option contract resolution
  -> CE/PE order

## Parity validation required

Do not treat this Pine translation as production-equivalent yet.

1. Paste ktmi_universal_dhan_signal.pine into the Dhan/TradingView Pine editor.
2. Keep all calculation defaults unchanged.
3. First test with:
   - CALL Long Speed ON
   - CALL Momentum OFF
   - PUT Short Speed ON
   - PUT Momentum OFF
   - CALL combination ANY
   - PUT combination ANY
   - all four trigger zones at the requested defaults.
4. Compare Long Speed, Long Signal, Short Speed and Short Signal with Python.
5. Then enable the Momentum conditions and validate the additional events.

The repository already contains tests/ktmi_pine_parity_test.py for
TradingView/Python numerical parity.

No locked KTMI production code is modified by this prototype.
