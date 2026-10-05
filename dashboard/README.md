# KunalQuant Control Dashboard

## Status

Interactive historical control terminal over the existing Opening Breakout V2 engine.

## Run locally

From the repository root:

```powershell
pip install -r dashboard/requirements.txt
streamlit run dashboard/app.py
```

The browser will open the KunalQuant Control Terminal.

## Current scope

- Real stored FYERS NIFTY 1-minute historical data.
- Existing Opening Breakout V2 signal engine.
- Existing option resolver and historical option loader.
- Existing execution/fill policy.
- Existing broker-cost model.
- Existing portfolio accounting.
- Interactive performance and risk metrics.
- Monthly P&L breakdown.
- Exit-reason analysis.
- Drawdown curve.
- Broker-cost component breakdown.
- Actual stop-risk and realized-R analytics.
- Trade-level investigation filters.
- Rejection/data-quality summary.

## Definitions shown by the dashboard

- **Gross P&L:** existing trade gross result before broker costs.
- **Net P&L:** gross P&L minus the existing broker cost model.
- **Strategy Risk:** absolute entry-to-initial-stop distance multiplied by the actual quantity.
- **Intended Risk:** configured risk/trade budget supplied to the backtest.
- **Realized R:** gross P&L divided by actual strategy stop risk.
- **Net R:** net P&L divided by actual strategy stop risk.
- **Entry Impact:** entry fill price minus the option signal price, multiplied by quantity.

These are analytics only; they do not modify the trading engine.

## Safety

The dashboard is a UI/analytics layer only. It does not change locked strategy definitions, option selection, execution, risk, lifecycle, or accounting behavior.

Paper and Live modes remain deliberately disabled.
