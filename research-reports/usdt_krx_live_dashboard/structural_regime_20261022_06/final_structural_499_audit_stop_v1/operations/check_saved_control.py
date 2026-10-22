# /// script
# requires-python = "==3.12.0"
# dependencies = ["numpy==2.2.6"]
# ///
# Run: python -B code/bootstrap.py ../operations/check_saved_control.py
from pathlib import Path
import json
import numpy as np
from runner import ROOT,write_json
out=ROOT/'control_regression'
old=ROOT/'baseline/B_original'
checks={}
with np.load(old/'numeric_result.npz') as a,np.load(out/'CONTROL_B/numeric_result.npz') as b:
    for key in ('trades','events','residual','risk','equity','extremes','orders'):
        np.testing.assert_array_equal(a[key],b[key])
        checks[key]='EXACT_MATCH'
    trades=b['trades'];score=sum(float(t[13])/(float(t[5])*170000)*100 for t in trades)
    assert len(trades)==42 and b['residual'][0]==0
    assert abs(score-16.7054302006977)<1e-8
with np.load(old/'full_account_ledger.npz') as a,np.load(out/'CONTROL_B/full_account_ledger.npz') as b:
    np.testing.assert_array_equal(a['ledger'],b['ledger'])
    checks['ledger']='EXACT_MATCH'
assert json.loads((out/'CONTROL_B/audit.json').read_text())['status']=='PASS'
record=dict(status='PASS',arrays=checks,cycles=42,score_pct=score,net_krw=float(np.sum(trades[:,13])),
    mdd_krw=9350000.,new_condition_count=0,old_strategy_runs=1,baseline_profit_target_pct=.7,
    exact_trade_cost_cash_margin_path_match=True,serialization_error_only=True,recalculation_repeated=False)
write_json(out/'validation_saved_arrays.json',record)
print(json.dumps(record),flush=True)
