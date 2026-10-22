# /// script
# requires-python = "==3.12.0"
# dependencies = ["numpy==2.2.6"]
# ///
# Run: python -B code/bootstrap.py ../operations/verify_actual_mdd.py
import json
import numpy as np
from runner import ROOT, table, write_json

rows=[]
for path in sorted((ROOT/'batches').glob('batch_*/candidates/*/full_account_ledger.npz')):
    with np.load(path) as source:account=source['ledger']
    mask=np.isfinite(account[:,:,5])
    equity=account[:,:,5][mask];recorded_mdd=account[:,:,8][mask]
    peak=np.maximum.accumulate(np.maximum(30000000.,equity))
    current=peak-equity;expected=np.maximum.accumulate(current)
    assert np.all(np.diff(recorded_mdd)>=0),path
    error=float(np.max(np.abs(recorded_mdd-expected)))
    assert error<.01,(path,error)
    rows.append(dict(candidate_id=path.parent.name,evaluation_marks=len(equity),status='PASS',
        actual_mdd_decreases=0,maximum_difference_krw=error,
        final_peak_equity_krw=float(peak[-1]),final_current_drawdown_krw=float(current[-1]),
        final_cumulative_mdd_krw=float(recorded_mdd[-1])))
assert len(rows)==500
out=ROOT/'actual_mdd_audit';assert not out.exists();out.mkdir()
table(out/'actual_mdd_all_500.csv',rows)
result=dict(status='PASS_ACTUAL_RECORDED_MDD_NONDECREASING',conditions=500,
    evaluation_marks=sum(r['evaluation_marks'] for r in rows),decreases=0,
    maximum_difference_krw=max(r['maximum_difference_krw'] for r in rows))
write_json(out/'validation.json',result)
print(json.dumps(result),flush=True)
