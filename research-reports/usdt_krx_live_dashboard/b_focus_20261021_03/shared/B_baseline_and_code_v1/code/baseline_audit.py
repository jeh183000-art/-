# /// script
# requires-python = "==3.12.0"
# dependencies = ["numpy==2.2.6"]
# ///
# Run: python -B code/bootstrap.py baseline_audit.py
import hashlib
import json
from pathlib import Path
import numpy as np
from audit import replay
from validation2 import verify_book
from runner import ROOT, load, table, write_json


def main():
    out=ROOT/'baseline_audit';assert not out.exists();out.mkdir()
    source=ROOT/'baseline/B_original'
    origin=ROOT.parent/'lump17_sweep_20261021_01/batches/batch_0001/candidates/L17-01-013'
    inventory=[]
    for path in sorted(source.iterdir()):
        if path.is_file():
            digest=hashlib.sha256(path.read_bytes()).hexdigest()
            assert digest==hashlib.sha256((origin/path.name).read_bytes()).hexdigest()
            inventory.append(dict(file=path.name,bytes=path.stat().st_size,sha256=digest))
    table(out/'original_B_inventory.csv',inventory)
    v,frame,codes=load();raw=np.load(source/'numeric_result.npz');book=np.load(source/'full_account_ledger.npz')['ledger']
    t,e,r,o=raw['trades'],raw['events'],raw['residual'],raw['orders']
    legacy=replay(v,t,e,book,o,2.);independent=verify_book(v,t,e,r,book,o,2.)
    score=sum(float(x[13])/(float(x[5])*170000)*100 for x in t)
    assert len(t)==39 and not r[0]
    assert abs(score-14.95131907100779)<1e-9
    assert abs(float(np.sum(t[:,13]))-36755589.35493902)<.01
    assert abs(float(np.nanmax(book[:,:,8]))-9350000)<.01
    assert legacy[3]==0 and len(o)==39 and np.all(o[:,4]==17)
    marks=book.reshape(-1,11);marks=marks[np.isfinite(marks[:,5])]
    assert np.all(np.diff(marks[:,8])>=0)
    sm=np.column_stack((v[5],v[6],np.where(v[13],v[15],v[6])))
    fm=np.column_stack((v[7],v[8],np.where(v[13],v[14],v[8])))
    exit_cost=sm*170000*.0005+10200+fm*170000*.000003157+(sm+fm)*170000*.0002
    hypothetical_net=book[:,:,6]-exit_cost
    cycle_rows=[];horizons=[]
    for trade in t:
        i,j,cid=int(trade[1]),int(trade[3]),int(trade[17]);sign=int(trade[4])
        active=np.isfinite(book[i:j,:,5])&(book[i:j,:,7]==sign)
        values=hypothetical_net[i:j][active];coordinates=np.argwhere(active)
        nonnegative=np.flatnonzero(values>=0)
        first_profit=float(v[0][i+coordinates[nonnegative[0],0]]-v[0][i]) if len(nonnegative) else None
        row=dict(cycle_id=cid,direction=sign,entry_kst=str(frame.iloc[i]['timestamp_kst']),exit_kst=str(frame.iloc[j]['timestamp_kst']),
            hold_minutes=float(trade[14]),net=float(trade[13]),return_pct=float(trade[13]/(trade[5]*170000)*100),
            maximum_paid_cost_loss_krw=max(0.,-float(np.nanmin(book[i:j,:,6]))),
            maximum_hypothetical_exit_loss_krw=max(0.,-float(np.min(values))),
            maximum_hypothetical_exit_loss_pct=max(0.,-float(np.min(values)))/(trade[5]*170000)*100,
            negative_observation_fraction=float(np.mean(values<0)),first_nonnegative_observation_minutes=first_profit)
        cycle_rows.append(row)
        for h in (60,240,1440,4320,10080,20160):
            ix=int(np.searchsorted(v[0],v[0][i]+h));status='OBSERVED_EXACT_MINUTE'
            net=None
            if ix>=j:status='ALREADY_CLOSED_OR_AT_EXIT'
            elif ix>=len(v[0]) or v[0][ix]!=v[0][i]+h:status='MISSING_OBSERVATION_NO_INTERPOLATION'
            else:net=float(hypothetical_net[ix,1])
            horizons.append(dict(cycle_id=cid,horizon_minutes=h,status=status,observed_liquidation_net=net,
                completed_cycle_net=float(trade[13]),diagnostic_only_not_time_exit_backtest=True))
    table(out/'B_cycle_holding_diagnostics.csv',cycle_rows)
    table(out/'B_observed_horizon_marks.csv',horizons)
    horizon_summary=[]
    for h in (60,240,1440,4320,10080,20160):
        selected=[x for x in horizons if x['horizon_minutes']==h]
        observed=[x for x in selected if x['status']=='OBSERVED_EXACT_MINUTE']
        horizon_summary.append(dict(horizon_minutes=h,observed_still_open=len(observed),negative_marks=sum(x['observed_liquidation_net']<0 for x in observed),
            already_closed=sum(x['status']=='ALREADY_CLOSED_OR_AT_EXIT' for x in selected),missing=sum(x['status']=='MISSING_OBSERVATION_NO_INTERPOLATION' for x in selected)))
    table(out/'B_horizon_summary.csv',horizon_summary)
    record=dict(status='PASS',candidate_id='L17-01-013',market_simulation_repeated=False,cycles=39,score_pct=score,
        net=float(np.sum(t[:,13])),mdd=float(np.nanmax(book[:,:,8])),legacy_max_error=float(legacy[0]),vector=independent,
        longest_hold_minutes=max(x['hold_minutes'] for x in cycle_rows),mean_hold_minutes=float(np.mean(t[:,14])),
        median_hold_minutes=float(np.median(t[:,14])),over_1day=sum(x['hold_minutes']>=1440 for x in cycle_rows),
        over_7days=sum(x['hold_minutes']>=10080 for x in cycle_rows),
        all_cycles_observed_negative_before_completion=all(x['negative_observation_fraction']>0 for x in cycle_rows),
        horizons=horizon_summary,win_rate_pct=100.,new_strategy_runs=0,
        interpretation='Profit-target completion and unrestricted holding select recovered exits; observed interim losses and long holding do not establish future recovery. Horizon marks are diagnostics, not counterfactual baseline reruns.')
    write_json(out/'validation.json',record);print(json.dumps(record),flush=True)


if __name__=='__main__':main()
