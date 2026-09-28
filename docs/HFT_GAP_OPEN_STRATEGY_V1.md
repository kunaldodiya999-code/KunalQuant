# HFT Gap-Open Strategy V1

Status: **Experimental / research-only**  
Default: **DISABLED**

## Rules

1. Calculate the NIFTY opening gap versus the previous NIFTY close.
2. Gap up >= 50 points activates CALLs; gap down <= -50 activates PUTs.
3. Current weekly NIFTY expiry only.
4. Approved ladder: ATM, ATM+50, ATM+100, ATM+150, ATM+200, ATM+250.
5. After the first complete 10-second option candle, require **Open == Low**.
6. The next 10-second candle must break the setup candle high.
7. Enter with an aggressive configurable limit order, not a market order.
8. Initial SL uses the setup candle low when risk is within the cap; otherwise
   risk is capped at the configurable default of 20 points from entry.
9. Position sizing defaults to ₹10,000 capital per lot and 4 lots. Both are
   configurable. Actual historical lot size comes from instrument metadata.
10. Optional targets remain 2R, 3R and 4R.
11. Manual point-based trailing is independently configurable. Example:
    entry ₹100, current ₹125, 10-point buffer => trailing stop ₹115.
12. HFT strategy remains disabled by default.

## Execution model

A limit order is not assumed filled merely because a signal occurs. The
backtest must verify that future market data actually traded through the
requested limit. Execution/slippage assumptions remain configurable.

## Isolation

Do not modify locked KTMI, Strategy A/B, Option Trade Management V1, Option
Contract Resolver V2, lifecycle, accounting, or analytics modules.
