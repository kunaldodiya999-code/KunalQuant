# KunalQuant — DhanHQ Integration

## Status

**Phase 1 — foundation only**

Implemented:
- DhanHQ Python SDK boundary
- environment-based credentials
- read-only account checks
- read-only option-chain access
- explicit live-order safety gate

Not implemented yet:
- Dhan historical-data adapter
- live market-feed adapter
- Dhan option-contract resolver
- Paper Execution adapter
- live execution adapter
- Dhan Cloud deployment packaging
- automatic order placement

## Architecture

KunalQuant remains the source of truth:

    Strategy
       |
       v
    Broker-neutral signal / order intent
       |
       +--> Historical adapter
       +--> Paper adapter
       +--> Dhan adapter

The existing FYERS path is not removed. Dhan is an additional broker
integration.

## Local credentials

Set these environment variables locally. Never commit them:

    DHAN_CLIENT_ID
    DHAN_ACCESS_TOKEN

Optional safety switch:

    DHAN_ENABLE_LIVE_ORDERS=false

The default is false. This phase is read-only.

## First connection test

From the KunalQuant root:

    python scripts/check_dhan_connection.py

A successful check retrieves the Dhan fund-limit response. This does not
place an order.

## Dhan Cloud

Dhan Cloud can run Python strategies and provides Dhan API access. We will
use Cloud as a future execution runtime, not as a replacement for the
KunalQuant research/backtest source of truth.

## Next integration stages

1. Validate authentication and read-only connectivity.
2. Pull Dhan option-chain and instrument metadata.
3. Add Dhan historical/live market-data adapters.
4. Build a Dhan-specific option resolver without changing the existing
   resolver.
5. Add Paper Execution using broker-neutral intents.
6. Validate KTMI signal parity.
7. Add live execution behind explicit safety controls.
