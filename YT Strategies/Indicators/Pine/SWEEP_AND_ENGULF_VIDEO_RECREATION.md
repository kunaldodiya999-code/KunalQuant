# Sweep & Engulf — Video Recreation

This Pine indicator is a **standalone TradingView visual recreation** of the
indicator developed during the supplied LuxAlgo/Quant video.

It is deliberately separate from KunalQuant production code.

## Source-derived behavior

### Bullish

The video describes:

1. Current candle takes out the previous candle low.
2. Current candle then closes above the previous candle high.
3. A bullish signal is plotted.

### Bearish

1. Current candle takes out the previous candle high.
2. Current candle then closes below the previous candle low.
3. A bearish signal is plotted.

No candle coloring is used.

## Settings reproduced from the video

### Signal Filters

- Previous Candle Direction
  - Any
  - Same Direction

### EMA Trend Filter

- Use & Show EMA Trend Filter
- EMA Length, default 200

When enabled:
- bullish signals only above EMA
- bearish signals only below EMA
- EMA is shown and turns green/red according to price location

### Risk Management

- ATR Length, default 14
- ATR Multiplier, default 2.0
- Risk/Reward Ratio, default 2.0
- Stop Loss Method
  - ATR
  - Candle High/Low
- Initial Box Projection, default 6 bars

### Trade management

The video adds one-active-trade behavior:

- after a signal, no new signal is accepted while the trade is active
- TP and SL boxes appear
- boxes initially project 6 bars
- boxes extend until TP or SL is reached
- wick touching TP/SL is treated as an exit
- after exit, a new signal can occur

## Important source ambiguity

The video does not clearly specify how to resolve a candle that touches both
TP and SL on the same bar. This recreation uses **SL first** as the conservative
deterministic rule.

The video also discusses a TradingView strategy conversion. This file remains
an indicator so it can be visually inspected first. No KunalQuant backtest or
execution logic is connected.

## Validation sequence

1. Add to TradingView.
2. Test NIFTY 1m, 3m and 5m.
3. Compare signals visually with the source video concept.
4. Test the Previous Candle Direction filter.
5. Test EMA filter on/off.
6. Test ATR vs Candle High/Low stops.
7. Inspect whether the one-trade-at-a-time box behavior matches what you want.

Only after you approve the visual behavior should we consider a separate
strategy/backtest version.
