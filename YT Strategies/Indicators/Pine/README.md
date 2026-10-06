# YT Research Visual Lab

Branch: `research/yt-pine-visual-lab`

## Purpose

This is a **TradingView visual research layer** for the YouTube/Claude research pack. It is intentionally isolated from KunalQuant production strategy code.

The main script is:

`YT_RESEARCH_VISUAL_LAB.pine`

It exposes independent ON/OFF controls for the research mechanisms so they can be placed on a NIFTY chart and visually inspected before any component is considered for SL/TSL or strategy use.

## Verification status

The existing Python research package was self-tested for determinism/causality, but that does **not** establish that every implementation reproduces the YouTube video exactly.

This Pine lab therefore uses four labels:

- **Video-supported** — behavior is explicitly supported by the supplied source material.
- **Python-derived** — translated from the research implementation.
- **Proxy** — Pine/OHLCV does not have enough information to reproduce the original data source exactly.
- **Experimental** — concept is intentionally approximate and must not be promoted without further validation.

## Important proxies

### Anchored / Cluster Volume Profile

The script uses VWAP/dispersion and rolling VWMA proxies. A true price-by-volume profile requires a finer volume distribution than standard OHLCV.

### CVD / Liquidity Delta

These modules use estimated candle-direction delta:

`volume * sign(close - open)`

This is **not true bid/ask delta**.

### GEX

GEX is exposed as a manual wall-level research proxy. True dealer GEX requires option-chain inputs (OI/volume/Greeks plus positioning assumptions). Do not treat the manual proxy as a verified GEX implementation.

### Machine Learning MA

The displayed adaptive MA is a research proxy, not a claim of parity with a trained ML model.

### Universal Signal Backtester

The event counter is only a visual research utility. It does not model option premiums, Greeks, lot size, broker costs, slippage, or execution.

## First modules to inspect for SL/TSL

1. Structural Leg Profiler
2. Smart Money Concepts / BOS
3. Order Block Strength
4. Peak Activity Range
5. Anchored Volume Profile proxy
6. Sweep & Engulf

Do not optimize them yet. First inspect chart behavior and identify which mechanisms are visually sensible.

## Next verification gate

For every candidate that looks useful:

1. Compare Pine event timing with the Python implementation.
2. Check whether the event is causal on the bar where it is displayed.
3. Test NIFTY 1m / 3m / 5m.
4. Only then connect the candidate to the KunalQuant backtest engine.
5. Keep every research component independently switchable ON/OFF.

No production trading logic is changed by this branch.
