# /// script
# requires-python = "==3.12.0"
# dependencies = ["numpy==2.2.6"]
# ///
# Run: python -B code/bootstrap.py ../operations/probe_pool_capacity.py
import json
from pathlib import Path
from runner import ROOT,write_json
from rules import signature
from hypotheses import pools
used=set()
for source in json.loads((ROOT/'baseline/registry.json').read_text())['previous_rule_sources']:
    used.update(signature(r) for r in json.loads(Path(source['path']).read_text()).values())
rows=[]
for number in range(1,9):
    selected=[]
    for group,r in pools(number):
        key=signature(r)
        if key in used:continue
        used.add(key);selected.append((group,r))
        if len(selected)==50:break
    assert len(selected)==50,(number,len(selected))
    rows.append(dict(batch=number,available_new_conditions=len(selected),groups=sorted({x[0] for x in selected}),market_runs=0))
write_json(ROOT/'pool_capacity_check.json',dict(status='PASS',first_eight_pools=rows,formal_registration=False,market_runs=0))
print(json.dumps(rows),flush=True)
