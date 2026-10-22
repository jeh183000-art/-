# /// script
# requires-python = "==3.12.0"
# dependencies = []
# ///
# Saved-result diagnostics only. No engine, data scope, ranking or rules are changed.
from __future__ import annotations
import csv,gzip,json,math,statistics
from collections import defaultdict
from runner import ROOT,table,write_json
from registry import BASE,signature

rules={c['candidate_id']:c['rule'] for p in sorted((ROOT/'preregistration').glob('batch_*.json')) for c in json.loads(p.read_text())['conditions']}
conditions={c['candidate_id']:c for c in json.loads((ROOT/'all_500_preregistration.json').read_text())['conditions']}
paths={p.parent.name:p.parent for p in (ROOT/'batches').glob('batch_*/candidates/*/result.json')}
results={cid:json.loads((p/'result.json').read_text()) for cid,p in paths.items()}
assert len(results)==500
out=ROOT/'diagnostics';out.mkdir()
periods=[];concentration=[];triggers=[];path_comparison=[]
with gzip.open(ROOT/'control_regression/CONTROL_B/cycles.csv.gz','rt',encoding='utf8',newline='') as stream:parent_cycles=list(csv.DictReader(stream))
def cycle_key(c):
    return (int(float(c['direction'])),int(float(c['entry_row'])),int(float(c['exit_row'])))
parent_map={cycle_key(c):c for c in parent_cycles}
for cid,folder in paths.items():
    with gzip.open(folder/'cycles.csv.gz','rt',encoding='utf8',newline='') as stream:cycles=list(csv.DictReader(stream))
    new_map={cycle_key(c):c for c in cycles}
    common=set(parent_map)&set(new_map)
    for key in common:assert abs(float(parent_map[key]['net'])-float(new_map[key]['net']))<.01
    parent_only=[c for k,c in parent_map.items() if k not in common]
    new_only=[c for k,c in new_map.items() if k not in common]
    delta=sum(float(c['return_pct']) for c in new_only)-sum(float(c['return_pct']) for c in parent_only)
    assert abs(delta-results[cid]['score_delta_B_pp'])<1e-8
    path_comparison.append(dict(candidate_id=cid,identical_parent_cycles=len(common),parent_unmatched_cycles=len(parent_only),new_unmatched_cycles=len(new_only),score_change_pp=delta,new_unmatched_score_pct=sum(float(c['return_pct']) for c in new_only),removed_parent_score_pct=sum(float(c['return_pct']) for c in parent_only)))
    monthly=defaultdict(list)
    returns=[float(c['return_pct']) for c in cycles]
    for cycle in cycles:monthly[cycle['exit_business_date'][:7]].append(cycle)
    for month in (f'2026-{m:02d}' for m in range(1,11)):
        monthly.setdefault(month,[])
    for month,selected in sorted(monthly.items()):
        periods.append(dict(candidate_id=cid,exit_business_month=month,cycles=len(selected),
            score_pct=sum(float(c['return_pct']) for c in selected),net_krw=sum(float(c['net']) for c in selected)))
    positive=sorted((r for r in returns if r>0),reverse=True);net=sum(returns)
    concentration.append(dict(candidate_id=cid,cycles=len(cycles),
        top3_positive_return_share_pct=sum(positive[:3])/sum(positive)*100 if positive else None,
        top5_positive_return_share_pct=sum(positive[:5])/sum(positive)*100 if positive else None,
        top3_net_return_share_pct=sum(positive[:3])/net*100 if net>0 else None,
        top5_net_return_share_pct=sum(positive[:5])/net*100 if net else None,
        median_completed_hold_minutes=statistics.median([float(c['hold_minutes']) for c in cycles]) if cycles else None))
    with (folder/'exit_attribution.csv').open(encoding='utf8',newline='') as stream:exits=list(csv.DictReader(stream))
    for r in exits:
        bits=int(r['reason_bits']);profit=r['profit']=='True'
        names=[k for k,v in [('gap_recovery',bool(bits&1)),('net_profit',profit),('gap_stop',bool(bits&2)),('net_stop',bool(bits&4) and not profit),('time',bool(bits&8)),('stall',bool(bits&16))] if v]
        assert names
        triggers.append(dict(candidate_id=cid,cycle_id=r['cycle_id'],signal_row=r['signal_row'],causes=';'.join(names),simultaneous_causes=len(names)))
coverage=[]
for category in range(1,6):
    subset=[c for c in conditions.values() if c['category']==category]
    for key in ('long_entry_gap_pct','short_entry_gap_pct','long_recovery_pp','short_recovery_pp','pnl_profit_pct','pnl_profit_long_pct','pnl_profit_short_pct','confirmation_pp','confirmation_min_observations','confirmation_expiry_calendar_minutes','cooldown_minutes','threshold_mode','window_observations','center_weight','volatility_recovery_scale','max_hold_minutes','stall_minutes','gap_stop_pp','pnl_stop_pct'):
        values=sorted({json.dumps(c['rule'].get(key),sort_keys=True) for c in subset})
        coverage.append(dict(category=category,conditions=len(subset),parameter=key,registered_values_json='['+','.join(values)+']'))
table(out/'hypothesis_coverage.csv',coverage)
table(out/'monthly_contribution.csv',periods)
table(out/'profit_concentration.csv',concentration)
table(out/'baseline_cycle_path_comparison.csv',path_comparison)
table(out/'all_exit_causes.csv',triggers)
groups=defaultdict(list)
for r in results.values():groups[r['execution_path_sha256']].append(r['candidate_id'])
baseline=json.loads((ROOT/'control_regression/CONTROL_B/result_repaired.json').read_text())
groups[baseline['execution_path_sha256']].append('BF-09-027_CONTROL')
table(out/'execution_equivalence.csv',[dict(path_sha256=k,new_conditions=sum(x!='BF-09-027_CONTROL' for x in v),baseline_control_references=sum(x=='BF-09-027_CONTROL' for x in v),candidate_ids=';'.join(v)) for k,v in groups.items()])

old_lookup={}
for name in ('lump17_sweep_20261021_01','lump17_extension_20261021_02','b_focus_20261021_03','b_dual_exit_extension_20261021_04'):
    root=ROOT.parent/name
    for reg in sorted((root/'preregistration').glob('batch_*.json')):
        for c in json.loads(reg.read_text())['conditions']:
            p=root/'batches'/reg.stem/'candidates'/c['candidate_id']/'result.json'
            if p.exists():old_lookup.setdefault(signature(c['rule']),dict(candidate_id=c['candidate_id'],result=json.loads(p.read_text()),source=str(p)))
lookup=dict(old_lookup)
lookup[signature(BASE)]=dict(candidate_id='BF-09-027',result=baseline,source='CONTROL exact original arrays; baseline commit c63352755d43b067b2124e748297efe6cbf6ecbf')
for cid,r in results.items():lookup[signature(rules[cid])]=dict(candidate_id=cid,result=r,source=str(paths[cid]/'result.json'))
reuse=[]
with (ROOT/'reuse_rules.csv').open(encoding='utf8',newline='') as stream:
    for row in csv.DictReader(stream):
        ref=lookup.get(row['signature'])
        reuse.append(dict(category=row['category'],rule_signature=row['signature'],reused_candidate=ref['candidate_id'] if ref else '',
            saved_result_source=ref['source'] if ref else '',score_pct=ref['result']['score_pct'] if ref else None,new_simulation_count=0))
table(out/'reused_saved_results.csv',reuse)
pairs=[]
for cid,r in results.items():
    if conditions[cid]['category']!=2:continue
    for policy,value in [('recovery_only',0.),('B_dual_profit_0p7',.7)]:
        ref_rule={k:v for k,v in rules[cid].items() if k not in ('pnl_profit_long_pct','pnl_profit_short_pct')}
        ref_rule['pnl_profit_pct']=value
        ref=lookup.get(signature(ref_rule))
        pairs.append(dict(candidate_id=cid,reference_policy=policy,reference_candidate=ref['candidate_id'] if ref else '',
            reference_source=ref['source'] if ref else '',reference_score_pct=ref['result']['score_pct'] if ref else None,
            score_difference_pp=r['score_pct']-ref['result']['score_pct'] if ref else None,
            identical_entry_and_recovery=True,self_reference=bool(ref and ref['candidate_id']==cid),reference_simulation_repeated=False))
table(out/'matched_exit_ablation.csv',pairs)

def vector(rule):
    """Distance is registered parameter proximity, never outcome similarity."""
    return [float(rule.get(k) or 0) for k in ('long_entry_gap_pct','short_entry_gap_pct','long_recovery_pp','short_recovery_pp','confirmation_pp','gap_stop_pp','pnl_stop_pct','center_weight')]+[
        float(rule.get('pnl_profit_long_pct',rule.get('pnl_profit_pct') or 0)),
        float(rule.get('pnl_profit_short_pct',rule.get('pnl_profit_pct') or 0)),
        float(rule.get('cooldown_minutes') or 0)/1440,float(rule.get('max_hold_minutes') or 0)/1440,
        float(rule.get('stall_minutes') or 0)/1440,float(rule.get('window_observations') or 0)/360,
        float(rule.get('confirmation_min_observations') or 0)/10,
        float(rule.get('confirmation_expiry_calendar_minutes') or 240)/240,
        float(bool(rule.get('volatility_recovery_scale')))]
selected=sorted([r for r in results.values() if r['cycles']],key=lambda r:r['score_pct'],reverse=True)[:20]
for group in sorted({r['group'] for r in results.values()}):
    selected+=sorted([r for r in results.values() if r['cycles'] and r['group']==group],key=lambda r:r['score_pct'],reverse=True)[:1]
neighbors=[]
for winner in {r['candidate_id']:r for r in selected}.values():
    cid=winner['candidate_id'];a=vector(rules[cid])
    cohort=[r for r in results.values() if r['candidate_id']!=cid and r['group']==winner['group'] and rules[r['candidate_id']].get('threshold_mode','fixed')==rules[cid].get('threshold_mode','fixed')]
    distances=[(math.sqrt(sum((x-y)**2 for x,y in zip(a,vector(rules[r['candidate_id']])))),r) for r in cohort]
    for distance,r in sorted(distances,key=lambda pair:(pair[0],pair[1]['candidate_id']))[:5]:
        neighbors.append(dict(candidate_id=cid,neighbor=r['candidate_id'],parameter_distance=distance,neighbor_score_pct=r['score_pct'],score_difference_pp=r['score_pct']-winner['score_pct'],neighbor_cycles=r['cycles'],same_execution_path=r['execution_path_sha256']==winner['execution_path_sha256']))
table(out/'neighbor_sensitivity.csv',neighbors)
write_json(out/'validation.json',dict(status='PASS',conditions=500,unique_new_execution_paths=len({r['execution_path_sha256'] for r in results.values()}),
    old_result_reuse_without_simulation=len(reuse),completed_cycles=len(triggers),entry_matched_exit_comparisons=len(pairs),
    all_results_exploratory=True,protected_oos_access=False))
print('PASS_SAVED_RESULT_DIAGNOSTICS_500',flush=True)
