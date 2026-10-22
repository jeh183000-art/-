# /// script
# requires-python = "==3.12.0"
# dependencies = ["numpy==2.2.6"]
# ///
# Run: python -B code/bootstrap.py build_B.py 1
from __future__ import annotations
import hashlib,json,sys
from pathlib import Path
from runner import ROOT,SOURCE_HASH,MARGIN_HASH,canonical,write_json
from rules import BASE,signature
from hypotheses import pools

def main() -> None:
    number=int(sys.argv[1]);assert 1<=number<=10
    assert json.loads((ROOT/'baseline_audit/validation.json').read_text())['status']=='PASS'
    assert json.loads((ROOT/'metric_tests.json').read_text())['status']=='PASS'
    if number>1:assert json.loads((ROOT/'publication'/f'batch_{number-1:04d}_results_verified.json').read_text())['status']=='PUBLISHED_VERIFIED'
    registry=json.loads((ROOT/'baseline/registry.json').read_text());used=set();previous=0
    for source in registry['previous_rule_sources']:
        path=Path(source['path']);assert hashlib.sha256(path.read_bytes()).hexdigest()==source['sha256']
        data=json.loads(path.read_text());assert len(data)==source['executed_conditions']+source['extra_control']
        used.update(signature(r) for r in data.values());previous+=source['executed_conditions']
    assert previous==1500;used.add(signature(BASE))
    for path in sorted((ROOT/'preregistration').glob('batch_*.json')) if (ROOT/'preregistration').exists() else []:
        used.update(signature(c['rule']) for c in json.loads(path.read_text())['conditions'])
    conditions=[]
    for group,value in pools(number):
        key=signature(value)
        if key in used:continue
        assert value['family'] in ('relative','reversal') and not value.get('allowed_direction')
        assert value['long_absolute_exit_gap_pct'] is None and value['short_absolute_exit_gap_pct'] is None
        assert min(value['long_recovery_pp'],value['short_recovery_pp'],value['pnl_profit_pct'])>0
        if number<=2:assert value['long_recovery_pp']==value['short_recovery_pp']==.6 and value['pnl_profit_pct']==.7 and not value.get('confirmation_pp')
        used.add(key);conditions.append(dict(candidate_id=f'BD-{number:02d}-{len(conditions)+1:03d}',group=group,parent_strategy='BF-09-027',rule=value,rule_sha256=hashlib.sha256(canonical(value)).hexdigest()))
        if len(conditions)==50:break
    assert len(conditions)==50,('NOT_ENOUGH_NEW_CONDITIONS',number,len(conditions))
    record=dict(batch=f'batch_{number:04d}',conditions=conditions,grid_sha256=hashlib.sha256(canonical(conditions)).hexdigest(),code_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((ROOT/'code').glob('*.py'))},source_sha256=SOURCE_HASH,margin_sha256=MARGIN_HASH,baseline_commit=registry['baseline_commit'],parent_B=BASE,prior_conditions_excluded=1500,A_C_D_search_enabled=False,final_oos_access=False,old_conditions_recomputed=False,maximum_new_conditions=500,mode='EXPLORATORY_PAPER',groups={g:sum(c['group']==g for c in conditions) for g in sorted({c['group'] for c in conditions})},frozen=dict(contracts=17,spot_quantity=170000,futures_initial_cash=30000000,additional_entries=False,simultaneous_opposite=False,external_deposits=False,slippage_bp=2),objectives=dict(score_greater_than=16.7054302006977,cycles_at_least=42,residual_contracts=0,mdd_at_most_krw=9350000,margin_shortages_and_rejections=0),score='sum unrounded completed cycle net / abs(initial spot entry notional) * 100',profit_factor='sum positive completed-cycle net KRW / abs(sum negative completed-cycle net KRW); explicit infinity when no losses',pnl_exit='Favorable recovery from entry signal close OR cost-net liquidation return target OR separately registered stop/time conditions; next contiguous observed minute OPEN proxy',input_status='INPUT_NOT_REMOTELY_REPRODUCIBLE')
    (ROOT/'preregistration').mkdir(exist_ok=True);write_json(ROOT/'preregistration'/f'batch_{number:04d}.json',record)
    print(json.dumps(dict(batch=number,count=50,groups=record['groups'],grid_sha256=record['grid_sha256'])),flush=True)

if __name__=='__main__':main()
