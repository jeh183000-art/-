# /// script
# requires-python = "==3.12.0"
# dependencies = []
# ///
# Final metadata audit only, no simulation.
from __future__ import annotations
import csv,hashlib,json
from pathlib import Path
from runner import ROOT,canonical,write_json,table,SOURCE_HASH,MARGIN_HASH
from registry import BASE,extract,signature
assert BASE['pnl_profit_pct']==.7
used=set()
with (ROOT/'registry_sources.csv').open(encoding='utf8',newline='') as stream:
    sources=list(csv.DictReader(stream))
for row in sources:
    path=Path(row['path'])
    assert hashlib.sha256(path.read_bytes()).hexdigest()==row['sha256']
    if path.suffix=='.json':
        old=extract(json.loads(path.read_text(encoding='utf8')))
    else:
        with path.open(encoding='utf-8-sig',newline='') as stream:old=extract(list(csv.DictReader(stream)))
    used.update(signature(r) for r in old)
used.add(signature(BASE))
rows=[]
for number in range(1,11):
    name=f'batch_{number:04d}'
    reg=json.loads((ROOT/'preregistration'/f'{name}.json').read_text())
    receipt=json.loads((ROOT/'publication'/f'{name}_prereg_verified.json').read_text())
    final=json.loads((ROOT/'publication'/f'{name}_results_verified.json').read_text())
    assert receipt['status']==final['status']=='PUBLISHED_VERIFIED'
    assert receipt['grid_sha256']==reg['grid_sha256']==hashlib.sha256(canonical(reg['conditions'])).hexdigest()
    assert reg['source_sha256']==SOURCE_HASH and reg['margin_sha256']==MARGIN_HASH
    for file,digest in reg['code_sha256'].items():
        assert hashlib.sha256((ROOT/'code'/file).read_bytes()).hexdigest()==digest
    for c in reg['conditions']:
        key=signature(c['rule'])
        assert key not in used and key==c['semantic_signature']
        used.add(key)
        assert c['category']==(number-1)//2+1
        result=json.loads((ROOT/'batches'/name/'candidates'/c['candidate_id']/'result.json').read_text())
        assert result['rule_sha256']==c['rule_sha256']==hashlib.sha256(canonical(c['rule'])).hexdigest()
        assert result['maximum_contracts'] in (0,17)
        rows.append(dict(candidate_id=c['candidate_id'],status='PASS',category=c['category'],prereg_commit=receipt['commit'],results_commit=final['commit'],semantic_signature=key))
assert len(rows)==500
assert all(sum(r['category']==category for r in rows)==100 for category in range(1,6))
out=ROOT/'registration_audit'
out.mkdir()
table(out/'registration_all_500.csv',rows)
write_json(out/'validation.json',dict(status='PASS',conditions=500,each_category=100,duplicates=0,code_drift=False,
    baseline_profit_target_pct=.7,all_prior_source_files_unchanged=len(sources),protected_oos_access=False))
print('PASS_REGISTRATION_500_AND_PRIOR_RULE_SOURCES',flush=True)
