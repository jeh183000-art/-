import hashlib,json
from runner import ROOT,canonical,table,write_json
from build_B import OLD,signature
old=json.loads(OLD.read_text());seen={signature(v) for v in old.values()};rows=[]
for i in range(1,11):
 name=f'batch_{i:04d}'
 reg=json.loads((ROOT/'preregistration'/f'{name}.json').read_text())
 assert len(reg['conditions'])==50
 assert hashlib.sha256(canonical(reg['conditions'])).hexdigest()==reg['grid_sha256']
 assert reg['A_C_D_search_enabled'] is False and reg['final_oos_access'] is False and reg['old_1000_recomputed'] is False
 receipt=json.loads((ROOT/'publication'/f'{name}_prereg_verified.json').read_text())
 assert receipt['status']=='PUBLISHED_VERIFIED' and receipt['grid_sha256']==reg['grid_sha256']
 for source,digest in reg['code_sha256'].items():assert hashlib.sha256((ROOT/'code'/source).read_bytes()).hexdigest()==digest
 for c in reg['conditions']:
  key=signature(c['rule']);assert key not in seen,(i,c['candidate_id']);seen.add(key)
  r=json.loads((ROOT/'batches'/name/'candidates'/c['candidate_id']/'result.json').read_text())
  assert r['rule_sha256']==c['rule_sha256']==hashlib.sha256(canonical(c['rule'])).hexdigest()
  assert r['maximum_contracts']<=17
  rows.append(dict(candidate_id=c['candidate_id'],status='PASS',duplicate_old=False,duplicate_new=False,registered_rule_sha256=c['rule_sha256'],batch=i,prereg_commit=receipt['commit']))
assert len(rows)==500
out=ROOT/'registration_audit';assert not out.exists();out.mkdir()
table(out/'all_500_registration_checks.csv',rows)
write_json(out/'validation.json',dict(status='PASS',new_conditions=500,old_registered_settings_including_control=len(old),duplicates=0,code_drift=False,registered_A_C_D_search=False,protected_oos_access=False))
print(json.dumps(dict(status='PASS',new_conditions=500,duplicates=0)),flush=True)
