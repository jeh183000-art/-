# /// script
# requires-python = "==3.12.0"
# dependencies = ["numpy==2.2.6"]
# ///
# Final-only small CSV from complete saved ledgers; no simulation or new price generation.
from __future__ import annotations
import hashlib,json
import numpy as np
from runner import ROOT,load,LEDGER_FIELDS,table,write_json
out=ROOT/'publish_payloads/final_path_500_v2'
leaders=json.loads((out/'best_rules_and_results.json').read_text())
folders={p.parent.name:p.parent for p in (ROOT/'batches').glob('batch_*/candidates/*/result.json')}
ids=sorted({x['result']['candidate_id'] for x in leaders.values()})
folders['BF-09-027_CONTROL']=ROOT/'control_regression/CONTROL_B'
v,frame,codes=load()
summary=[]
for cid in ids+['BF-09-027_CONTROL']:
    path=folders[cid]/'full_account_ledger.npz'
    with np.load(path) as source:book=source['ledger']
    coordinates=np.argwhere(np.isfinite(book[:,:,5]))
    marks=book[np.isfinite(book[:,:,5])]
    peak=np.maximum.accumulate(np.maximum(30000000.,marks[:,5]))
    current=peak-marks[:,5];mdd=np.maximum.accumulate(current)
    np.testing.assert_allclose(mdd,marks[:,8],atol=.01,rtol=0)
    cash_changes=np.r_[True,np.any(np.diff(marks[:,:2],axis=0)!=0,axis=1)]
    chosen=set(np.flatnonzero(cash_changes).tolist())
    worst=int(np.argmax(current))
    chosen.update((0,len(marks)-1,worst,int(np.argmax(marks[:worst+1,5])),
        int(np.argmin(marks[:,6])),int(np.argmax(marks[:,10]))))
    held=np.flatnonzero(marks[:,7]!=0)
    if len(held):
        chosen.update((int(held[np.argmin(marks[held,9])]),int(held[np.argmin(marks[held,4])])))
    rows=[]
    for j in sorted(chosen):
        row,phase=map(int,coordinates[j])
        sm=v[5][row] if phase==0 else v[6][row] if phase==1 else v[15][row]
        fm=v[7][row] if phase==0 else v[8][row] if phase==1 else v[14][row]
        rows.append(dict(candidate_id=cid,input_row=row,phase=('OPEN','CLOSE','SETTLEMENT')[phase],
            timestamp_kst=str(frame.iloc[row]['timestamp_kst']),business_date=str(frame.iloc[row]['business_date']),
            spot_mark=float(sm),future_mark=float(fm),**dict(zip(LEDGER_FIELDS,map(float,marks[j]))),
            peak_equity_krw=float(peak[j]),current_drawdown_krw=float(current[j]),cumulative_mdd_krw=float(mdd[j]),
            cash_change=bool(cash_changes[j])))
    assert all(j in chosen for j in np.flatnonzero(cash_changes))
    table(out/f'{cid}_cash_margin_snapshot.csv',rows)
    summary.append(dict(candidate_id=cid,full_ledger_rows=len(marks),snapshot_rows=len(rows),
        all_cash_change_marks_included=True,drawdown_peak_and_trough_included=True,
        initial_and_maintenance_minima_included=True,full_ledger_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        scope='Cash-change and selected risk extrema only; full every-minute ledger remains in batch lossless NPZ archive'))
write_json(out/'cash_snapshot_validation.json',dict(status='PASS',candidates=summary,market_simulation_repeated=False))
print('PASS_SMALL_CASH_MARGIN_SNAPSHOTS',flush=True)
