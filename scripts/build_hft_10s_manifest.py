from __future__ import annotations
import argparse, csv, json, math, sqlite3
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from config.hft_data import HFT_STRIKE_OFFSETS, HFT_OPTION_TYPES, HFT_RESOLUTION
from config.settings import DATABASE_PATH, TIMEZONE

def connect():
    c=sqlite3.connect(DATABASE_PATH); c.row_factory=sqlite3.Row; return c
def atm(price): return int(math.floor(float(price)/50.0+0.5)*50)
def nearest_expiry(c, trade_date):
    r=c.execute("""SELECT expiry_date FROM instruments WHERE broker='FYERS' AND underlying='NIFTY'
      AND instrument_type IN ('OPT','OPTION','OPTIONS') AND expiry_date >= ?
      ORDER BY expiry_date LIMIT 1""",(trade_date,)).fetchone()
    return r[0] if r else None
def option_symbol(c, expiry, strike, typ):
    r=c.execute("""SELECT symbol FROM instruments WHERE broker='FYERS' AND underlying='NIFTY'
      AND instrument_type IN ('OPT','OPTION','OPTIONS') AND expiry_date=? AND strike=? AND option_type=?
      ORDER BY id LIMIT 1""",(expiry,float(strike),typ)).fetchone()
    return r[0] if r else None
def future_symbol(c, trade_date):
    r=c.execute("""SELECT symbol,expiry_date FROM instruments WHERE broker='FYERS' AND underlying='NIFTY'
      AND instrument_type IN ('FUT','FUTURE','FUTURES') AND expiry_date >= ?
      ORDER BY expiry_date,id LIMIT 1""",(trade_date,)).fetchone()
    return dict(r) if r else None

def main():
    p=argparse.ArgumentParser(description="Build dynamic HFT 10s coverage manifest from canonical NIFTY 1m data.")
    p.add_argument("--from",dest="start",required=True); p.add_argument("--to",dest="end",required=True)
    p.add_argument("--output",default="data/reports/hft_10s_manifest.csv")
    p.add_argument("--json",default="data/reports/hft_10s_manifest_summary.json"); args=p.parse_args()
    c=connect(); tz=ZoneInfo(TIMEZONE)
    rows=c.execute("""SELECT timestamp,close FROM candles JOIN instruments i ON i.id=candles.instrument_id
      WHERE i.broker='FYERS' AND i.symbol='NSE:NIFTY50-INDEX' AND candles.resolution='1'
      AND timestamp BETWEEN strftime('%s',?) AND strftime('%s',?) ORDER BY timestamp""",
      (args.start+" 00:00:00",args.end+" 23:59:59")).fetchall()
    manifest=[]; missing=[]; option_keys=set(); future_keys=set(); index_days=set()
    for r in rows:
        dt=datetime.fromtimestamp(int(r["timestamp"]),timezone.utc).astimezone(tz)
        trade_date=dt.strftime("%Y-%m-%d"); index_days.add(trade_date)
        expiry=nearest_expiry(c,trade_date)
        if not expiry:
            missing.append({"timestamp":r["timestamp"],"reason":"NO_EXPIRY","trade_date":trade_date}); continue
        if trade_date not in {x["trade_date"] for x in manifest if x["kind"]=="INDEX"}:
            manifest.append({"kind":"INDEX","trade_date":trade_date,"timestamp":r["timestamp"],
                             "symbol":"NSE:NIFTY50-INDEX","expiry_date":""})
        a=atm(r["close"]); fut=future_symbol(c,trade_date)
        if fut and fut["symbol"] not in future_keys:
            future_keys.add(fut["symbol"]); manifest.append({"kind":"FUTURES","trade_date":trade_date,
                "timestamp":r["timestamp"],"symbol":fut["symbol"],"expiry_date":fut["expiry_date"]})
        elif not fut: missing.append({"timestamp":r["timestamp"],"reason":"NO_FUTURES","trade_date":trade_date})
        for off in HFT_STRIKE_OFFSETS:
            strike=a+off
            for typ in HFT_OPTION_TYPES:
                sym=option_symbol(c,expiry,strike,typ)
                if not sym:
                    missing.append({"timestamp":r["timestamp"],"reason":"NO_OPTION","trade_date":trade_date,
                        "expiry_date":expiry,"strike":strike,"option_type":typ}); continue
                key=(sym,trade_date)
                if key in option_keys: continue
                option_keys.add(key); manifest.append({"kind":"OPTION","trade_date":trade_date,
                    "timestamp":r["timestamp"],"symbol":sym,"expiry_date":expiry,"strike":strike,
                    "option_type":typ,"atm_strike":a,"offset":off})
    manifest.sort(key=lambda x:(x["trade_date"],x["kind"],x["symbol"]))
    out=Path(args.output); out.parent.mkdir(parents=True,exist_ok=True)
    fields=sorted({k for r in manifest for k in r})
    with out.open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(manifest)
    summary={"from":args.start,"to":args.end,"resolution":HFT_RESOLUTION,"nifty_1m_rows":len(rows),
      "nifty_index_days":len(index_days),"manifest_rows":len(manifest),
      "unique_option_contract_days":len(option_keys),"unique_option_symbols":len({r["symbol"] for r in manifest if r["kind"]=="OPTION"}),
      "unique_futures_symbols":len(future_keys),"missing_rows":len(missing),"missing_examples":missing[:100],
      "generated_at":datetime.now().isoformat()}
    Path(args.json).parent.mkdir(parents=True,exist_ok=True); Path(args.json).write_text(json.dumps(summary,indent=2),encoding="utf-8")
    print(json.dumps(summary,indent=2)); print(f"Manifest: {out}")
if __name__=="__main__": main()
