# KunalQuant Control Dashboard

## Status
Phase 1 dashboard shell + real Opening Breakout V2 historical engine integration.

## Run locally

From the repository root:

```powershell
pip install streamlit pandas
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
- Interactive metrics, equity curve, and trade log.

Paper and Live controls are deliberately disabled in this milestone.

## Safety

The dashboard is a UI layer only. It does not change the locked strategy, execution, cost, or lifecycle modules.
