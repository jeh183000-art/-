# /// script
# requires-python = "==3.12.0"
# dependencies = ["numpy==2.2.6"]
# ///
# Run after the saved CONTROL exists; no simulation call.
import json
import numpy as np
from runner import ROOT,load,write_json
from registry import BASE
from path_metrics import MetricContext,enrich
target=ROOT/'control_regression'
v,frame,codes=load()
with np.load(target/'CONTROL_B/numeric_result.npz') as source:
    trades=source['trades'];events=source['events']
with np.load(target/'CONTROL_B/full_account_ledger.npz') as source:
    ledger=source['ledger']
metrics_out=target/'serialized_metrics_check';metrics_out.mkdir()
# Given: actual saved CONTROL marks that previously yielded NumPy scalar trigger counts.
metrics=enrich(MetricContext(BASE,v,trades,ledger,events,metrics_out))
# When: the public result is encoded under strict JSON.
encoded=json.dumps(metrics,allow_nan=False)
decoded=json.loads(encoded)
# Then: the 42 actual exits partition correctly and contain only valid JSON scalars.
assert decoded['exit_gap_only']==41 and decoded['exit_profit_only']==0 and decoded['exit_gap_profit_both']==1
assert decoded['exit_gap_only']+decoded['exit_profit_only']+decoded['exit_gap_profit_both']+decoded['exit_other']==42
incomplete=(target/'CONTROL_B/result.json').read_text()
complete_prefix=incomplete.rsplit(',\n',1)[0]+'\n}'
result=json.loads(complete_prefix);result.update(metrics)
write_json(target/'CONTROL_B/result_repaired.json',result)
validation=json.loads((target/'validation_saved_arrays.json').read_text())
validation.update(serialization_regression_test='PASS',new_condition_count=0)
write_json(target/'validation.json',validation)
write_json(ROOT/'path_metric_tests.json',dict(status='PASS',saved_control_reused=True,new_simulations=0,exit_partition=42,strict_json=True))
print('PASS_SAVED_CONTROL_SERIALIZATION_AND_EXACT_ARRAY_REGRESSION',flush=True)
