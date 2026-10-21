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

### P0 — Durable restart recovery implemented; runtime verification required
A versioned atomic `paper_state.json` snapshot now stores all trades, open/closed state, remaining quantity/lots, partial-exit history, current stop (including manual adjustments), realized P&L, and the last processed timestamp. The durable engine restores this snapshot before the session starts its feed and checks trade identities and exit-event counts/P&L against the append-only CSV journal. Missing snapshots with an existing trade journal, malformed snapshots, duplicate identities, and detected journal conflicts fail closed rather than starting an empty engine. Snapshot persistence follows entry, every processed candle (including candles without exits), manual stop changes, and forced exits. Focused restart/corruption tests were added; run them and the full suite in the target environment before treating this blocker as closed. Crash windows between journal and snapshot writes intentionally require manual reconciliation rather than guessed recovery.

### P0 — Watchdog/control integration needs runtime verification
The independent watchdog and local HTTP API have been added but have not yet been executed by a test run in this development step. Verify watchdog timing, repeated retries, close-vs-candle concurrency, server lifecycle, and browser/API behavior. A fresh quote is mandatory; the system must never fabricate a fill.

### P1 — Paper gap-aware stop fills
The buyer-only paper lifecycle receives candle open through the session integration. When an option candle opens below the stop, the simulated fill uses the worse opening premium; an intrabar stop touch without a gap still fills at the configured stop. Regression tests have been added; rerun them with the full suite in the target environment.

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
3. Run the new gap-through-stop regression tests and test stale/missing quote scenarios.
4. Verify current contract metadata and actual FYERS callback payloads.
5. Complete a market-data-only smoke test and inspect logs/alerts.

**Status:** paper-only integration, not approved for unattended full-session operation. No live orders are supported by this branch.
