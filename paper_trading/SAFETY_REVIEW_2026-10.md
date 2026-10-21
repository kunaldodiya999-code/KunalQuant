# Paper Buyer Safety Review — 2026-10-21

Scope: `feature/paper-buyer-engine-port`. This review covers the current paper-trading integration only. It does not authorize live execution and does not modify the locked historical lifecycle in `backtest/option_trade_lifecycle.py`.

## Implemented in this milestone

- Buyer-only partial exits use the configured fraction with whole-lot rounding and an explicit one-lot policy.
- The coordinator rejects new entries at/after the configured cutoff (default 15:00 IST).
- Cash allocation uses starting capital + realized exit P&L − entry cost of open remaining quantities and caps new entries to the configured percentage of available cash.
- Manual stop updates are available through the engine and local control API; the API respects the setting that controls whether loosening is allowed.
- A loopback-only HTTP control service serves the settings page, persists validated JSON settings, exposes paper-session status, and applies future-entry risk settings.
- The settings UI posts to the local API and can submit a manual stop update for a selected strategy.
- A dedicated watchdog thread checks open positions independently of option-tick callbacks after the configured forced-exit time. It closes only from a quote accepted by the quote cache's exchange-time and local-receipt freshness checks. Missing/stale quotes leave positions open and produce an in-memory alert.
- The single-lot target closes the full position when configured; stop-first handling remains conservative when one candle touches both stop and target.
- Historical V1 lifecycle remains unchanged.

## Open blockers before relying on a full-session paper run

### P0 — Restart recovery and reconciliation are incomplete
The engine's active positions, partial exits, last processed candle timestamps, and realized P&L remain in-memory state. Restarting can lose active state while the append-only journal still contains ENTRY/EXIT events. Implement durable state restoration and reconciliation before unattended runs.

### P0 — Watchdog/control integration needs runtime verification
The independent watchdog and local HTTP API have been added but have not yet been executed by a test run in this development step. Verify watchdog timing, repeated retries, close-vs-candle concurrency, server lifecycle, and browser/API behavior. A fresh quote is mandatory; the system must never fabricate a fill.

### P1 — Stop fills assume the stop price even across gaps
The lifecycle receives high/low/close but not candle open. If an option candle opens below the stop, the simulated exit may be recorded at the stop level, overstating performance. Add a conservative gap-aware fill rule and regression tests.

### P1 — Daily loss cutoff is not enforced
Daily loss cutoff remains disabled per user instruction. The UI validates and persists its configuration, but enabling it is not enforced by the engine. Do not enable it until enforcement and tests exist.

### P1 — Broker data contract remains unverified
Actual installed FYERS SDK callback payloads, subscription behavior, reconnect lifecycle, and real option quote timestamp semantics have not been verified against a market-data-only session. Validate without enabling any order API.

### P1 — Contract metadata must be validated at run time
Lot size is supplied by the caller. Verify current lot size, strike step, expiry and contract metadata against current exchange specifications rather than treating defaults as authoritative.

## Release gate for paper-only operation

Before unattended paper sessions:
1. Complete durable recovery and reconciliation for open positions, partial exits, duplicate signals and repeated candle delivery.
2. Run the focused and full test suites after the control API/watchdog changes.
3. Test gap-through-stop and stale/missing quote scenarios.
4. Verify current contract metadata and actual FYERS callback payloads.
5. Complete a market-data-only smoke test and inspect logs/alerts.

**Status:** paper-only integration, not approved for unattended full-session operation. No live orders are supported by this branch.
