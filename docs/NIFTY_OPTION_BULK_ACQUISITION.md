# NIFTY Option Bulk Acquisition

Controlled acquisition layer for empty historical NIFTY option contracts.

## Design

This script reuses `downloader.historical.HistoricalDownloader`. It does not
replace or modify the downloader.

Default run:

```powershell
python scripts/acquire_nifty_option_candles.py
```

Defaults:
- 5 contracts/run
- 90 calendar days ending at expiry
- 1.2s pause between contracts
- 1-minute expired F&O data
- checkpoint CSV after every contract

Run a larger controlled batch explicitly:

```powershell
python scripts/acquire_nifty_option_candles.py --limit 10
```

Run all remaining contracts only after rate-limit approval:

```powershell
python scripts/acquire_nifty_option_candles.py --limit 0
```

## Important

The 90-day window is an acquisition phase, not a claim that every contract's
full historical life is 90 days. Returned first/last timestamps must be audited
before the dataset is declared complete.

No forward-fill, synthetic prices, or repair of missing market candles is
performed.
