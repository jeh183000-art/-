from pathlib import Path
import json,hashlib,csv
import numpy as np
import pandas as pd
import runner
from signals import prepare
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'publish_payloads/final_fixed_validation_v1'
f=pd.read_csv(ROOT/'validation_2025_partial/matched_simulation_bars.csv',dtype={'business_date':str});res=[]
for candidate in json.loads((ROOT/'preregistration/fixed_variants.json').read_text())['conditions']:
 p=ROOT/'validation_2025_partial'/candidate['candidate_id'];n=np.load(p/'numeric_result.npz');book=np.load(p/'full_account_ledger.npz')['ledger'];held=np.isfinite(book[:,:,7])&(abs(book[:,:,7])>0)
 marks=np.full_like(book[:,:,6],np.nan)
 for ph in range(3):
  s=f.spot_open.to_numpy() if ph==0 else f.spot_close.to_numpy() if ph==1 else pd.to_numeric(f.settlement_spot_mark,errors='coerce').to_numpy()
  z=f.future_open.to_numpy() if ph==0 else f.future_close.to_numpy() if ph==1 else pd.to_numeric(f.official_daily_settlement,errors='coerce').to_numpy()
  exitcost=170000*s*.0005+10200+170000*z*.000003157+170000*(s+z)*.0002
  marks[:,ph]=book[:,ph,6]-exitcost
 values=marks[held];rows=[]
 for e in n['events']:
  if int(e[0]) in (1,2):rows.append(dict(kind=int(e[0]),direction=int(e[3]),timestamp=str(f.iloc[int(e[1])].timestamp_kst),signal_timestamp=str(f.iloc[int(e[13])].timestamp_kst),signal_gap=float(f.iloc[int(e[13])].raw_gap_close_pct),spot=float(e[4]),future=float(e[5]),contracts=17))
 valid=book.reshape(-1,11);valid=valid[np.isfinite(valid[:,5])];last=valid[-1]
 res.append(dict(candidate_id=candidate['candidate_id'],actual_entry_exit_events=rows,open_direction=int(n['residual'][1]),open_age_minutes=float(n['residual'][11]),residual_net_after_exit_cost=float(n['residual'][10]),maximum_open_loss_after_estimated_exit_cost_krw=float(max(0,-np.nanmin(values))) if len(values) else 0,ending_future_cash=float(last[1]),ending_future_unrealized=float(last[2]),ending_future_equity=float(last[1]+last[2]),closed_cycle_score_eligible=False,borrow_unverified=True,maximum_required_spot_borrow_usdt=170000 if n['residual'][1]==-1 else 0))
original_checks=[]
for r in csv.DictReader((ROOT/'data_audit/input_inventory_sha256.csv').open()):
 p=Path(r['path']);original_checks.append(dict(path=r['path'],sha256=r['sha256'],unchanged=hashlib.sha256(p.read_bytes()).hexdigest()==r['sha256']))
assert all(r['unchanged'] for r in original_checks)
# Prefix causality: fixed-threshold signals and targets cannot change when future rows are removed.
n=len(f);v=[np.zeros(n) for _ in runner.NAMES];v[4]=f.raw_gap_close_pct.to_numpy();v[9]=f.contract_roll.astype(bool).to_numpy();v[12]=f.continuous_prev.astype(bool).to_numpy()
checks=[]
for c in json.loads((ROOT/'preregistration/fixed_variants.json').read_text())['conditions']:
 a=prepare(c['rule'],v,{'night':f.session.eq('night').to_numpy(),'volume':f.future_volume.to_numpy()})
 for cut in (100,10000,n-100):
  b=prepare(c['rule'],[z[:cut] for z in v],{'night':f.session.eq('night').to_numpy()[:cut],'volume':f.future_volume.to_numpy()[:cut]})
  for x,y in zip(a[:5],b[:5]):np.testing.assert_equal(x[:cut],y)
  checks.append(dict(candidate_id=c['candidate_id'],cut=cut,status='PASS'))
runner.write_json(OUT/'post_audit.json',dict(status='PASS',risk_details=res,source_hash_checks=original_checks,prefix_causality=checks,no_trades_recalculated=True))
print(json.dumps(dict(risk_details=res,input_rows=len(f),regular_by_date=f[f.session=='regular'].groupby('business_date').size().to_dict()),ensure_ascii=False))
