# Paper Buyer Safety Review — 2026-10-21

Scope: `feature/paper-buyer-engine-port`. This review covers the current paper-trading integration only. It does not authorize live execution, and it does not modify the locked historical lifecycle in `backtest/option_trade_lifecycle.py`.

## Fixed in this review

- **Single-lot target never closed the trade:** when a position had one lot, the partial-target calculation returned zero lots to exit. The target handler now closes the full remaining position at the target price. Regression coverage was added in `tests/test_paper_buyer_lifecycle.py`.
- Existing conservative rule remains: if a completed candle touches both stop and target, stop loss is processed first.

## Open blockers before relying on a full-session paper run

### P0 — No forced end-of-day liquidation
The session currently advances exits only when option candles arrive. There is no independent 15:10 IST liquidation watchdog and no guaranteed close when ticks stop arriving. A paper trade can therefore remain open across session end or a feed outage. Implement an independent session clock, explicit forced-exit reason, last-valid-price policy, and stale-price rejection before calling the session operationally complete.

### P0 — Open trade state is not restored after restart
The pending-entry orchestrator persists processed signal keys, but the engine's active positions, partial exits, last processed candle timestamps, and realized P&L are in-memory state. Restarting the process can lose an open paper position while the journal still contains its ENTRY. Add durable state recovery and reconciliation against the append-only trade-event journal before unattended runs.

### P1 — Stop fills assume the stop price even across gaps
The lifecycle receives high/low/close but not candle open. If an option candle opens below the stop, the simulated exit is still recorded at the stop level. This may overstate performance. Use a conservative gap-aware fill rule (e.g. opening price when it gaps through the stop) and test it before interpreting paper P&L.

### P1 — Risk/session controls are incomplete
The session config has allocation, stop percentage, and target multiple, but the reviewed path does not enforce a portfolio/day loss limit or a hard no-new-entry cutoff and forced exit. These need explicit session-level enforcement and tests rather than relying on the strategy signal window alone.

### P1 — Partial-exit configuration is misleading
`BuyerLifecycleConfig.partial_exit_fraction` is validated but the target logic currently exits a fixed lot split rather than using that configured fraction. Either implement and test the configured fraction with valid whole-lot rounding, or remove/rename the option so configuration cannot imply behavior that is not applied.

### P1 — Broker data contract remains unverified
The feed adapter has fake-socket tests, but the actual installed FYERS SDK callback payloads, subscription behavior, reconnect lifecycle, and real option quote timestamp semantics have not been verified against a live market-data-only session. Verify these with no order API enabled.

### P1 — Contract metadata must be validated at run time
The lot size is deliberately supplied by the caller, but the default resolver strike step and selected expiry/lot metadata must be checked against current exchange contract specifications. Do not treat defaults as verified current contract data.

## Release gate for paper-only operation

Before an unattended paper session, require:
1. A dedicated session clock that blocks new entries at the configured cutoff and attempts forced exits independently of ticks.
2. Restart recovery and reconciliation tests covering open positions, partial exits, duplicate signals, and repeated candle delivery.
3. Gap-through-stop and stale/missing quote tests.
4. Verified current lot size, strike step, expiry, and actual FYERS callback payloads.
5. A fresh full test run on this branch and a market-data-only smoke test.

**Status:** paper-only integration; not ready for unattended full-session validation until the P0 items above are closed. No live orders are supported by this branch.
