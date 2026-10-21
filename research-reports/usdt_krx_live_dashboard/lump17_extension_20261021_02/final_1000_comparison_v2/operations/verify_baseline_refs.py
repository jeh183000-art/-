# /// script
# requires-python = "==3.12.0"
# dependencies = []
# ///
# Run: python -B code/bootstrap.py ../operations/verify_baseline_refs.py
import csv
import json
from typing import assert_never
from runner import ROOT, write_json

prior=ROOT.parent/'lump17_sweep_20261021_01'
with (prior/'publish_payloads/final_500_audit_v1/results_all_500.csv').open(encoding='utf8',newline='') as stream:
    baseline={r['candidate_id']:r for r in csv.DictReader(stream)}
checked=0;fields=0
for path in sorted((prior/'batches').glob('batch_*/candidates/*/result.json')):
    current=json.loads(path.read_text());old=baseline[current['candidate_id']]
    for key,value in current.items():
        assert key in old,key
        match value:
            case None:assert old[key]==''
            case bool():assert old[key]==str(value)
            case int() | float():assert float(old[key])==value,(path,key)
            case str():assert old[key]==value,(path,key)
            case unreachable:assert_never(unreachable)
        fields+=1
    checked+=1
assert checked==len(baseline)==500
settings=json.loads((prior/'publish_payloads/final_500_audit_v1/settings_all_500.json').read_text())['conditions']
registry={r['candidate_id']:r['rule'] for p in (prior/'preregistration').glob('batch_*.json') for r in json.loads(p.read_text())['conditions']}
for row in settings:assert row['rule']==registry[row['candidate_id']]
result=dict(status='PASS_OLD_500_ALL_RESULT_FIELDS_AND_RULES_UNCHANGED',conditions=checked,result_fields_compared=fields,
    baseline_remote_bytes_proof=json.loads((ROOT/'publication/original_500_baseline_read.json').read_text()),market_simulations_repeated=0)
write_json(ROOT/'publish_payloads/final_1000_comparison_v2/baseline_validation.json',result)
print(json.dumps(result),flush=True)
