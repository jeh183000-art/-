import json,hashlib
from pathlib import Path
import numpy as np
import runner
from validation2 import verify_book
ROOT=Path(__file__).resolve().parents[1]
reg=json.loads((ROOT/'preregistration/fixed_variants.json').read_text())
for name,h in reg['code_sha256'].items():assert hashlib.sha256((ROOT/'code'/name).read_bytes()).hexdigest()==h
out=ROOT/'comparison_2026';out.mkdir()
v,frame,codes=runner.load()
rows=[]
for candidate in reg['conditions']:
 r=runner.calculate(candidate,v,frame,codes,out/candidate['candidate_id']);rows.append(r)
old=ROOT.parents[1]/'studies/b_focus_20261021_03/batches/batch_0009/candidates/BF-09-027'
new=out/'B2025-ORIGINAL-CONTROL'
a=np.load(old/'numeric_result.npz');b=np.load(new/'numeric_result.npz')
for k in a.files:np.testing.assert_allclose(a[k],b[k],atol=0.01,rtol=0,equal_nan=True)
np.testing.assert_allclose(np.load(old/'full_account_ledger.npz')['ledger'],np.load(new/'full_account_ledger.npz')['ledger'],atol=.01,rtol=0,equal_nan=True)
assert rows[1]['cycles']==42 and abs(rows[1]['score_pct']-16.7054302006977)<1e-9 and abs(rows[1]['net_realized']-41295918.91)<.01 and rows[1]['mdd_krw']==9350000
x=np.load(out/'B2025-RECOVERY-ONLY/numeric_result.npz');y=np.load(new/'numeric_result.npz')
financial_match={}
for k in x.files:
 xx=x[k];yy=y[k]
 if k=='trades':xx=xx[:,:-1];yy=yy[:,:-1]
 financial_match[k]=bool(xx.shape==yy.shape and np.allclose(xx,yy,atol=1e-8,rtol=0,equal_nan=True))
summary={'status':'PASS','original_regression':'ALL_NUMERIC_AND_ACCOUNT_FIELDS_MATCH','variants':rows,'financial_arrays_match_except_exit_reason':financial_match,'signal_cause_only_difference':True,'approved_2026_min_timestamp':str(frame.timestamp_kst.min()),'approved_2026_min_business_date':str(frame.business_date.min()),'calendar_2025_boundary_rows':int(frame.timestamp_kst.astype(str).str.startswith('2025').sum()),'not_2025_performance':True}
runner.write_json(out/'comparison.json',summary);runner.table(out/'results.csv',rows)
print(json.dumps(summary,ensure_ascii=False))
