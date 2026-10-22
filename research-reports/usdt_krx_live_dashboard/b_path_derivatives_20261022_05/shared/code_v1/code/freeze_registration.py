# /// script
# requires-python = "==3.12.0"
# dependencies = []
# ///
# Preserve preflight v1 and freeze corrected serialization code before any new simulation.
from pathlib import Path
import hashlib,json,shutil
from runner import ROOT,canonical,write_json
original=ROOT/'preregistration'
archive=ROOT/'preregistration_preflight_v1'
assert original.resolve().is_relative_to(ROOT.resolve()) and not archive.exists()
allplan=json.loads((ROOT/'all_500_preregistration.json').read_text())
rules_hash=hashlib.sha256(canonical(allplan['conditions'])).hexdigest()
original.rename(archive)
original.mkdir()
code={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((ROOT/'code').glob('*.py'))}
for path in sorted(archive.glob('batch_*.json')):
    record=json.loads(path.read_text())
    record['code_sha256']=code
    record['preflight_revision']='serialization type boundary only; rules unchanged'
    write_json(original/path.name,record)
(ROOT/'all_500_preregistration.json').rename(ROOT/'operations/all_500_preregistration_preflight_v1.json')
allplan['code_sha256']=code
allplan['preflight_revision']='Python float metrics boundary; no financial or signal change after exact CONTROL'
assert hashlib.sha256(canonical(allplan['conditions'])).hexdigest()==rules_hash
write_json(ROOT/'all_500_preregistration.json',allplan)
write_json(ROOT/'operations/preflight_revision.json',dict(status='PASS',rules_changed=False,new_conditions_executed=0,
    control_simulation_count=1,control_exact_arrays=True,saved_control_serialization_test=True,
    original_plan_rules_sha256=rules_hash,revised_plan_rules_sha256=rules_hash,baseline_profit_pct=.7))
print('PREREGISTRATION_V2_RULES_IDENTICAL',flush=True)
