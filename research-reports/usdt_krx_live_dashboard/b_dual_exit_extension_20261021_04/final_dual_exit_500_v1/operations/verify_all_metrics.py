# /// script
# requires-python = "==3.12.0"
# dependencies = ["numpy==2.2.6"]
# ///
# Run: python -B code/bootstrap.py ../operations/verify_all_metrics.py
import csv,gzip,json,hashlib
from runner import ROOT,table,write_json
rows=[]
for path in sorted((ROOT/'batches').glob('batch_*/candidates/*/result.json')):
    result=json.loads(path.read_text())
    with gzip.open(path.parent/'cycles.csv.gz','rt',encoding='utf8',newline='') as stream:cycles=list(csv.DictReader(stream))
    assert len(cycles)==result['cycles']
    net=sum(float(r['net']) for r in cycles)
    score=sum(float(r['net'])/abs(float(r['spot_entry_notional']))*100 for r in cycles)
    assert abs(net-result['net_realized'])<.01 and abs(score-result['score_pct'])<1e-9
    for r in cycles:assert float(r['contracts'])==17 and float(r['spot_quantity'])==170000 and abs(float(r['spot_entry_notional'])-float(r['entry_spot'])*170000)<.01
    gains=sum(max(float(r['net']),0.) for r in cycles);losses=-sum(min(float(r['net']),0.) for r in cycles)
    if losses>0:assert result['profit_factor_status']=='FINITE' and abs(gains/losses-result['profit_factor_krw'])<1e-10
    else:assert result['profit_factor_krw'] is None and result['profit_factor_status']==('INFINITE_NO_LOSSES' if gains>0 else 'UNDEFINED_NO_COMPLETED_PNL')
    with (path.parent/'residual.csv').open(encoding='utf8',newline='') as stream:residual=next(csv.DictReader(stream))
    residual_contracts=int(float(residual['contracts']));residual_net=float(residual['net_after_exit_cost'])
    assert residual_contracts==result['residual_contracts'] and abs(residual_net-result['residual_net_after_exit_cost'])<.01
    forced=score+(residual_net/(float(residual['spot_entry'])*170000)*100 if residual_contracts else 0.)
    assert abs(forced-result['forced_terminal_score_pct'])<1e-9
    qualified=bool(score>16.7054302006977 and len(cycles)>=42 and residual_contracts==0 and result['mdd_krw']<=9350000.01 and result['admission_rejections']==0 and result['initial_margin_deficit_marks']==0 and result['maintenance_breach_marks']==0 and result['insufficient_rolls']==0)
    assert qualified==result['goal_qualified']
    book_hash=hashlib.sha256((path.parent/'full_account_ledger.npz').read_bytes()).hexdigest()
    rows.append(dict(candidate_id=result['candidate_id'],account_path_sha256=book_hash,status='PASS',cycles=len(cycles),score_error_pp=score-result['score_pct'],net_error_krw=net-result['net_realized'],profit_factor_status=result['profit_factor_status'],gap_target_exits=sum(bool(int(float(r['exit_reason_bits']))&1) for r in cycles),pnl_rule_exits=sum(bool(int(float(r['exit_reason_bits']))&4) for r in cycles),both_gap_and_pnl_exits=sum((int(float(r['exit_reason_bits']))&5)==5 for r in cycles)))
assert len(rows)==500
out=ROOT/'metrics_audit';assert not out.exists();out.mkdir()
table(out/'all_500_metrics_checks.csv',rows)
groups={}
for r in rows:groups.setdefault(r['account_path_sha256'],[]).append(r['candidate_id'])
table(out/'account_path_groups.csv',[dict(account_path_sha256=k,conditions=len(v),candidate_ids=';'.join(v)) for k,v in sorted(groups.items())])
write_json(out/'validation.json',dict(status='PASS',conditions=500,cycles=sum(r['cycles'] for r in rows),max_net_error_krw=max(abs(r['net_error_krw']) for r in rows),max_score_error_pp=max(abs(r['score_error_pp']) for r in rows),PF_independently_verified=True,unique_account_path_hashes=len(groups),distinct_rules_not_independent_observations=True))
print(json.dumps(dict(status='PASS',conditions=500)),flush=True)
