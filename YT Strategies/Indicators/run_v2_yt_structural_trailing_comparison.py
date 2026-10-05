"""Compare locked V2 exits with YT ATR structural trailing on the same filled trades.

Phase 1 intentionally holds entry, quantity, initial stop and target constant.
This isolates the exit-management effect before allowing altered equity to affect
future position sizing.
"""
from __future__ import annotations
import argparse, sqlite3, sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

PROJECT_ROOT=Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path: sys.path.insert(0,str(PROJECT_ROOT))
RESEARCH_DIR=Path(__file__).resolve().parent
if str(RESEARCH_DIR) not in sys.path: sys.path.insert(0,str(RESEARCH_DIR))

from backtest.broker_cost_model import calculate_options_trade_costs, fyers_options_profile
from backtest.fyers_option_candles import FyersOptionCandleLoader
from backtest.opening_breakout_v2_fill_engine import HistoricalBar
from backtest.opening_breakout_v2_multi_session import run_multi_session_backtest
from config.settings import DATABASE_PATH
from execution.opening_breakout_v2_execution import V2ExecutionPolicy
from research.opening_breakout_1m_v2 import Candle, IndicatorSnapshot, V2Config
from strategies.option_contract_resolver import OptionContractResolver
from v2_yt_structural_trailing import StructuralTrailConfig, simulate_structural_exit

IST=ZoneInfo("Asia/Kolkata")

def epoch(v): return int(datetime.fromisoformat(v).replace(tzinfo=IST).timestamp())
def load_nifty(a,b):
    with sqlite3.connect(DATABASE_PATH) as c:
        rows=c.execute("""SELECT c.timestamp,c.open,c.high,c.low,c.close FROM candles c JOIN instruments i ON i.id=c.instrument_id WHERE i.broker='FYERS' AND i.symbol='NSE:NIFTY50-INDEX' AND c.resolution='1' AND c.timestamp BETWEEN ? AND ? ORDER BY c.timestamp""",(a,b)).fetchall()
    return [Candle(int(t),float(o),float(h),float(l),float(cl)) for t,o,h,l,cl in rows]
def empty_provider(timestamp,candle): return IndicatorSnapshot()

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--from",dest="start",required=True); p.add_argument("--to",dest="end",required=True)
    p.add_argument("--atr-period",type=int,default=5); p.add_argument("--swing-atr",type=float,default=2.5); p.add_argument("--stop-buffer",type=float,default=.25)
    a=p.parse_args()
    candles=load_nifty(epoch(a.start),epoch(a.end))
    config=V2Config(trade_instrument="CALL",market_bias="NEUTRAL",selected_timeframes=("1M",),selected_triggers=("CANDLE_HIGH",),filter_open_high=False,filter_open_low=False,custom_sl_points=20.0,tp_mode="RR_RATIO",rr_multiplier=2.0,risk_per_trade_value=2000.0,capital_allocation_percent=100.0)
    policy=V2ExecutionPolicy(entry_buffer_points=1.0,max_slippage_points=2.0,fill_timeout_seconds=60)
    result=run_multi_session_backtest(candles=candles,config=config,resolver=OptionContractResolver(DATABASE_PATH),option_loader=FyersOptionCandleLoader(DATABASE_PATH),execution_policy=policy,capital=100000.0,indicator_provider=empty_provider)
    loader=FyersOptionCandleLoader(DATABASE_PATH)
    trail=StructuralTrailConfig(a.atr_period,a.swing_atr,a.stop_buffer)
    gross_delta=0.; cost_delta=0.; alt_net=0.; baseline_net=0.; changed=0; alt_wins=0; alt_losses=0; alt_stops=0; alt_targets=0; alt_force=0
    rows=[]
    for trade in result.trades:
        if trade.status!="CLOSED": continue
        force_ts=int(datetime.fromtimestamp(trade.event.trigger_timestamp,tz=IST).replace(hour=15,minute=15,second=0,microsecond=0).timestamp())
        raw=loader(trade.contract.instrument_id,trade.entry.timestamp or trade.event.trigger_timestamp,force_ts)
        bars=[HistoricalBar(int(x.timestamp),float(x.open),float(x.high),float(x.low),float(x.close)) for x in raw]
        alt=simulate_structural_exit(bars,entry_timestamp=trade.entry.timestamp,direction=trade.event.direction,stop_price=trade.stop_price,target_price=trade.target_price,policy=policy,force_exit_timestamp=force_ts,config=trail,entry_price=trade.entry.price)
        if not alt.exit.filled: continue
        mult=1.0 if trade.event.direction=="LONG" else -1.0
        alt_gross=(alt.exit.price-trade.entry.price)*trade.quantity*mult
        base_cost=calculate_options_trade_costs(entry_price=trade.entry.price,exit_price=trade.exit.price,quantity=trade.quantity,profile=fyers_options_profile(datetime.fromtimestamp(trade.event.trigger_timestamp,tz=IST).date()),gross_pnl=trade.gross_pnl)
        alt_cost=calculate_options_trade_costs(entry_price=trade.entry.price,exit_price=alt.exit.price,quantity=trade.quantity,profile=fyers_options_profile(datetime.fromtimestamp(trade.event.trigger_timestamp,tz=IST).date()),gross_pnl=alt_gross)
        dg=alt_gross-trade.gross_pnl; dc=alt_cost.total_cost-base_cost.total_cost
        gross_delta+=dg; cost_delta+=dc; alt_net+=alt_cost.net_pnl; baseline_net+=base_cost.net_pnl
        changed += alt.exit.timestamp!=trade.exit.timestamp or abs(alt.exit.price-trade.exit.price)>1e-9 or alt.exit.reason!=trade.exit.reason
        if alt_cost.net_pnl>0: alt_wins+=1
        elif alt_cost.net_pnl<0: alt_losses+=1
        if alt.exit.reason=="STOP_LOSS": alt_stops+=1
        elif alt.exit.reason=="TARGET": alt_targets+=1
        elif alt.exit.reason=="FORCE_EXIT": alt_force+=1
        rows.append((trade.contract.symbol,trade.event.trigger_timestamp,trade.exit.reason,alt.exit.reason,trade.gross_pnl,alt_gross,dg,len(alt.updates)))
    print("="*100); print("KUNAL QUANT — V2 BASELINE vs YT ATR STRUCTURAL TRAILING (FIXED-QUANTITY PHASE 1)"); print("="*100)
    print(f"Baseline closed trades : {len(rows)}")
    print(f"Trades changed         : {changed}")
    print(f"Baseline net P&L       : {baseline_net:.2f}")
    print(f"Trailing net P&L       : {alt_net:.2f}")
    print(f"Net P&L delta          : {alt_net-baseline_net:.2f}")
    print(f"Gross P&L delta        : {gross_delta:.2f}")
    print(f"Cost delta             : {cost_delta:.2f}")
    print(f"Trailing wins/losses   : {alt_wins} / {alt_losses}")
    print(f"Trailing exits         : STOP={alt_stops} TARGET={alt_targets} FORCE={alt_force}")
    print("="*100)
    print("Top trade-level improvements:")
    for r in sorted(rows,key=lambda x:x[6],reverse=True)[:10]: print(f"{r[0]} base={r[2]} trail={r[3]} gross_delta={r[6]:.2f} updates={r[7]}")

if __name__=="__main__": main()
