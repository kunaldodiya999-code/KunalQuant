# Paper Buyer Safety Review — 2026-10-21

Scope: `feature/paper-buyer-engine-port`. This review covers the current paper-trading integration only. It does not authorize live execution, and it does not modify the locked historical lifecycle in `backtest/option_trade_lifecycle.py`.

## Fixed in this review

- **Single-lot target never closed the trade:** when a position had one lot, the partial-target calculation returned zero lots to exit. The target handler now closes the full remaining position at the target price. Regression coverage was added in `tests/test_paper_buyer_lifecycle.py`.
- Existing conservative rule remains: if a completed candle touches both stop and target, stop loss is processed first.\n- Buyer-only partial exits now use the configured fraction with whole-lot rounding, and the one-lot close-all/skip policy is explicit.\n- The paper coordinator rejects new entries at/after the configured 15:00 IST cutoff.\n- Optional engine cash accounting uses starting capital + realized exit P&L − entry cost of open remaining quantities, then caps new entries to the configured percentage of available cash. This is enabled by the session composition root.\n- Manual stop updates and a forced-exit engine operation are available; forced exit requires a valid positive quote supplied by its caller.

## Open blockers before relying on a full-session paper run

### P0 — No forced end-of-day liquidation
The session attempts a forced exit at/after 15:10 IST only when a tick for that open option arrives. Missing/stale quote data leaves the trade open and records an in-memory alert. There is still no independent watchdog, durable alert, or guarantee that an exit is attempted if ticks stop arriving. Do not call this operationally complete.

### P0 — Open trade state is not restored after restart
The pending-entry orchestrator persists processed signal keys, but the engine's active positions, partial exits, last processed candle timestamps, and realized P&L are in-memory state. Restarting the process can lose an open paper position while the journal still contains its ENTRY. Add durable state recovery and reconciliation against the append-only trade-event journal before unattended runs.

### P1 — Stop fills assume the stop price even across gaps
The lifecycle receives high/low/close but not candle open. If an option candle opens below the stop, the simulated exit is still recorded at the stop level. This may overstate performance. Use a conservative gap-aware fill rule (e.g. opening price when it gaps through the stop) and test it before interpreting paper P&L.

### P1 — Risk/session controls are incomplete
The no-new-entry cutoff and cash allocation are now enforced in the configured session path. Daily loss cutoff is intentionally disabled per user instruction and has no active stop mechanism; enabling it in the UI is not yet enforced by the engine. The forced exit remains tick-driven rather than independent.

### P1 — Partial-exit configuration is misleading
The configured partial-exit fraction now determines whole-lot exit quantity (rounding up while retaining at least one lot), and a regression test covers the 50% case. The UI stores settings locally and exports JSON; it is not a live control surface for an already-running session.

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
