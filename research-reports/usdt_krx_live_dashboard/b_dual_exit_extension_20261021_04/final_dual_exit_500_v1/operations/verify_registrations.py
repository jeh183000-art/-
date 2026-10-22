# /// script
# requires-python = "==3.12.0"
# dependencies = ["numpy==2.2.6"]
# ///
# Run: python -B code/bootstrap.py ../operations/verify_registrations.py
import hashlib,json
from pathlib import Path
from runner import ROOT,canonical,table,write_json,SOURCE_HASH,MARGIN_HASH
from rules import signature
registry=json.loads((ROOT/'baseline/registry.json').read_text());seen=set();prior_count=0
for source in registry['previous_rule_sources']:
    path=Path(source['path']);assert hashlib.sha256(path.read_bytes()).hexdigest()==source['sha256']
    data=json.loads(path.read_text());assert len(data)==source['executed_conditions']+source['extra_control']
    seen.update(signature(v) for v in data.values());prior_count+=source['executed_conditions']
assert prior_count==1500
rows=[]
for i in range(1,11):
    name=f'batch_{i:04d}';reg=json.loads((ROOT/'preregistration'/f'{name}.json').read_text())
    assert len(reg['conditions'])==50 and hashlib.sha256(canonical(reg['conditions'])).hexdigest()==reg['grid_sha256']
    assert reg['source_sha256']==SOURCE_HASH and reg['margin_sha256']==MARGIN_HASH
    assert not reg['A_C_D_search_enabled'] and not reg['final_oos_access'] and not reg['old_conditions_recomputed']
    receipt=json.loads((ROOT/'publication'/f'{name}_prereg_verified.json').read_text());assert receipt['status']=='PUBLISHED_VERIFIED' and receipt['grid_sha256']==reg['grid_sha256']
    for source,digest in reg['code_sha256'].items():assert hashlib.sha256((ROOT/'code'/source).read_bytes()).hexdigest()==digest
    for c in reg['conditions']:
        key=signature(c['rule']);assert key not in seen,(i,c['candidate_id']);seen.add(key)
        r=json.loads((ROOT/'batches'/name/'candidates'/c['candidate_id']/'result.json').read_text())
        assert r['rule_sha256']==c['rule_sha256']==hashlib.sha256(canonical(c['rule'])).hexdigest() and r['maximum_contracts']<=17
        if i<=2:assert c['rule']['long_recovery_pp']==c['rule']['short_recovery_pp']==.6 and c['rule']['pnl_profit_pct']==.7
        rows.append(dict(candidate_id=c['candidate_id'],status='PASS',duplicate_old=False,duplicate_new=False,rule_sha256=c['rule_sha256'],batch=i,prereg_commit=receipt['commit']))
assert len(rows)==500
out=ROOT/'registration_audit';assert not out.exists();out.mkdir()
table(out/'all_500_registration_checks.csv',rows)
write_json(out/'validation.json',dict(status='PASS',new_conditions=500,old_conditions_excluded=1500,duplicates=0,code_drift=False,first_two_batches_dual_exit_preserved=True,source_hash_fixed=True,margin_hash_fixed=True,protected_oos_access=False))
print(json.dumps(dict(status='PASS',new_conditions=500,duplicates=0)),flush=True)
