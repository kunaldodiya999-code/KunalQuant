# V2 Structural Trailing Experiment

## Phase 1 — fixed-quantity isolation

`run_v2_yt_structural_trailing_comparison.py` replays every closed baseline V2 trade with identical entry, quantity, initial stop, target, force-exit time, execution buffers and broker cost model. Only post-entry stop management changes.

This is intentionally not production integration. It answers whether the YT ATR structural trail improves exit economics when all other variables are held constant.

## Current candidate

- atr_period=5
- swing_atr_mult=2.5
- stop_atr_buffer=0.25

These are research defaults, not optimized parameters.

## Promotion gate

1. Run Phase 1 comparison.
2. Require improvement after costs, not only gross P&L.
3. Check drawdown and losing streak.
4. Perturb parameters.
5. Test out-of-sample.
6. Confirm with path-dependent sizing.
