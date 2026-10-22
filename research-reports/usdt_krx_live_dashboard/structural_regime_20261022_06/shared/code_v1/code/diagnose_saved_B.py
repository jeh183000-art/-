# /// script
# requires-python = "==3.12.0"
# dependencies = ["numpy==2.2.6"]
# ///
# Read saved B ledgers and approved inputs; never rerun a strategy.
from __future__ import annotations
import json
import numpy as np
from runner import ROOT,load,table,write_json
from signals import crossing

def main() -> None:
    out=ROOT/"diagnosis";out.mkdir()
    v,frame,codes=load()
    raw=np.load(ROOT/"baseline/B_original/numeric_result.npz")
    trades=raw["trades"]
    book=np.load(ROOT/"baseline/B_original/full_account_ledger.npz")["ledger"]
    held=book[:,1,7]!=0
    rows=[]
    for t in trades:
        i,j=int(t[1]),int(t[3])
        ss=float(t[9]);ff=float(t[10])
        rows.append(dict(cycle_id=int(t[17]),direction=int(t[4]),entry=str(frame.iloc[i]["timestamp_kst"]),
            exit=str(frame.iloc[j]["timestamp_kst"]),hold_minutes=float(t[14]),spot_gross=ss,future_gross=ff,
            gross=ss+ff,fees=float(t[11]),slippage=float(t[12]),net=float(t[13]),
            costs_to_gross_pct=float((t[11]+t[12])/(ss+ff)*100) if ss+ff else None,
            score_pct=float(t[13]/(t[5]*170000)*100)))
    table(out/"saved_B_cost_holding.csv",rows)
    signals=[]
    for width in (.3,.5,.7,1.,1.5,2.):
        signs=crossing(v[4]+width,v[4]-width,False)
        signs[~v[12]|v[9].astype(bool)]=0
        signals.append(dict(threshold=width,flat_signals=int(np.sum((signs!=0)&~held)),
            held_signals=int(np.sum((signs!=0)&held)),
            caveat="Signals are observations, not independent opportunities; no counterfactual strategy rerun."))
    table(out/"flat_and_blocked_signals.csv",signals)
    driver=[]
    for horizon in (5,30,60,240):
        for i in range(horizon,len(v[0])):
            if v[3][i]!=v[3][i-horizon] or v[0][i]-v[0][i-horizon]!=horizon:continue
            ds=100*np.log(v[6][i]/v[6][i-horizon]);df=100*np.log(v[8][i]/v[8][i-horizon])
            if abs(ds-df)<.1:continue
            driver.append(dict(row=i,horizon=horizon,spot_log_change_pp=ds,future_log_change_pp=df,
                log_gap_change_pp=ds-df,driver="spot" if abs(ds)>abs(df) else "future",
                sign=int(np.sign(ds-df)),B_held=bool(held[i])))
    table(out/"gap_driver_observations.csv.gz",driver)
    gross=sum(r["gross"] for r in rows);cost=sum(r["fees"]+r["slippage"] for r in rows)
    positive=sorted((r["score_pct"] for r in rows if r["score_pct"]>0),reverse=True)
    record=dict(status="PASS",strategy_runs=0,cycles=len(rows),gross=gross,fees=sum(r["fees"] for r in rows),
        slippage=sum(r["slippage"] for r in rows),net=sum(r["net"] for r in rows),
        mean_gross_per_cycle=gross/len(rows),mean_cost_per_cycle=cost/len(rows),cost_to_gross_pct=cost/gross*100,
        mean_hold_minutes=float(np.mean(trades[:,14])),max_hold_minutes=float(np.max(trades[:,14])),
        median_hold_minutes=float(np.median(trades[:,14])),hold_over_7d=int(np.sum(trades[:,14]>=10080)),
        observed_held_fraction=float(np.mean(held)),calendar_completed_hold_days=float(np.sum(trades[:,14])/1440),
        top3_score_share_pct=sum(positive[:3])/sum(positive)*100,
        top5_score_share_pct=sum(positive[:5])/sum(positive)*100,
        source_split="Spot/future realized PnL separately; log-gap driver is attribution, not causal identification.",
        delay_limit="No tick orderbook: exact latency loss cannot be isolated; all fees/slips from actual saved cycle ledger.",
        identical_paths="Hard threshold exits may dominate alternate profit rules; sampled sequential returns are discrete, so multiple parameter sets select identical bars.")
    assert abs(record["net"]-41295918.91188297)<.01
    write_json(out/"summary.json",record)
    print(json.dumps(record))

if __name__=="__main__":main()
