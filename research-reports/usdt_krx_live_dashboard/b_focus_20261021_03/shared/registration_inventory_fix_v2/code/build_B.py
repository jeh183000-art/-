# /// script
# requires-python = "==3.12.0"
# dependencies = ["numpy==2.2.6"]
# ///
# Run: python -B code/bootstrap.py build_B.py 1
import copy
import csv
import hashlib
import json
import sys
from itertools import zip_longest
from runner import ROOT, canonical, write_json

BASE=json.loads((ROOT/'baseline/registry.json').read_text())['B']['rule']
OLD=ROOT.parent/'lump17_extension_20261021_02/publish_payloads/final_1000_comparison_v2/settings_all_1000.json'


def rule(e=1.,r=.6,**extra):
    value=copy.deepcopy(BASE)
    value.update(family='relative',long_entry_gap_pct=-float(e),short_entry_gap_pct=float(e),long_recovery_pp=float(r),short_recovery_pp=float(r))
    value.update(extra)
    if value.get('confirmation_pp',0)>0:value.update(family='reversal',confirmation_expiry_calendar_minutes=240)
    return value


def signature(value):
    out={k:v for k,v in value.items() if v is not None and v!=0}
    if value['family'] in ('relative','reversal'):
        out['family']='relative'
        if value.get('confirmation_pp',0)>0:out['confirmation_expiry_calendar_minutes']=240
    if value.get('slippage_bp')==2:out.pop('slippage_bp',None)
    if value['family'] in ('mean','median','absolute'):
        out.pop('long_recovery_pp',None);out.pop('short_recovery_pp',None)
    if value['family'] in ('zscore','quantile'):
        for k in ('long_entry_gap_pct','short_entry_gap_pct','long_recovery_pp','short_recovery_pp'):out.pop(k,None)
    if value.get('allowed_direction')==1:out={k:v for k,v in out.items() if not k.startswith('short_')}
    if value.get('allowed_direction')==-1:out={k:v for k,v in out.items() if not k.startswith('long_')}
    return hashlib.sha256(canonical(out)).hexdigest()


def interleave(*groups):
    return [item for chunk in zip_longest(*groups) for item in chunk if item]


def pools(number):
    es=(.55,.75,.9,1.1,1.3,1.6,2.,2.4,2.8,3.2);rs=(.25,.45,.6,.75,.9,1.05,1.2,1.5)
    wide=[('wide_entry_recovery',rule(e=e,r=rs[(i+shift)%len(rs)])) for shift in range(len(rs)) for i,e in enumerate(es)]
    el=(.6,.85,1.,1.15,1.4,1.8,2.3);short=(.65,.9,1.,1.2,1.5,2.,2.5)
    asym_e=[('asymmetric_entry',rule(e=e,r=r,short_entry_gap_pct=short[(i+shift)%len(short)])) for r in (.6,.75,.45) for shift in range(len(short)) for i,e in enumerate(el)]
    rl=(.3,.45,.6,.75,.9);rr=(.35,.5,.65,.8,1.)
    asym_r=[('asymmetric_recovery',rule(e=e,r=r,short_recovery_pp=rr[(i+shift)%len(rr)])) for e in (.85,1.,1.15,1.4) for shift in range(len(rr)) for i,r in enumerate(rl)]
    confirmation=[('reversal_confirmation',rule(e=e,r=(.4,.6,.8,1.)[(i+shift)%4],confirmation_pp=c)) for c in (.04,.12,.25,.35) for shift in range(4) for i,e in enumerate((.65,.85,1.,1.15,1.4,1.8))]
    seeds=[rule(),rule(e=.85),rule(e=1.15),rule(r=.45),rule(r=.75),rule(e=.85,short_entry_gap_pct=1.15)]
    times=[('calendar_time_cap',dict(r,max_hold_minutes=h)) for h in (90,480,2880,10080,20160,30,180,960,5760,14400,28800) for r in seeds]
    profit=[('net_profit_exit',dict(r,pnl_profit_pct=p)) for p in (.15,.25,.4,.7,.9,1.2) for r in seeds]
    stop=[('net_loss_stop',dict(r,pnl_stop_pct=p)) for p in (.3,.7,1.5,3.,.45,.9) for r in seeds]
    gap=[('gap_loss_stop',dict(r,gap_stop_pp=p)) for p in (.3,.7,1.25,2.5,.45,.9) for r in seeds]
    pnl=interleave(profit,stop,gap)
    if number==1:return interleave(wide,asym_e,confirmation,times,pnl)
    if number==2:return wide
    if number==3:return asym_e
    if number==4:return asym_r
    if number==5:return confirmation
    if number==6:return times
    if number==7:return pnl
    if number==8:
        filters=[('entry_session',dict(r,entry_session=s)) for s in ('regular','night') for r in seeds+ [rule(e=e,r=r) for e in (.65,.95,1.25,1.55) for r in (.55,.7)]]
        volume=[('minute_volume',dict(r,minimum_minute_volume=z)) for z in (10,50,200,500) for r in seeds]
        stalled=[('stalled_recovery',dict(r,stall_minutes=z)) for z in (90,480,2880,10080) for r in seeds]
        return interleave(filters,volume,stalled)+wide
    registrations=[json.loads(p.read_text()) for p in sorted((ROOT/'preregistration').glob('batch_*.json'))]
    lookup={c['candidate_id']:c for reg in registrations for c in reg['conditions']}
    results=[json.loads(p.read_text()) for p in sorted((ROOT/'batches').glob('batch_*/candidates/*/result.json'))]
    structural=lambda r: r['cycles']>=39 and r['residual_contracts']==0 and r['mdd_krw']<=9350000.01 and r['margin_shortage_free']
    ranked=sorted([r for r in results if r['cycles'] and r['feasible']],key=lambda r:(structural(r),r['score_pct']),reverse=True)
    leaders=[copy.deepcopy(BASE)];seen=set()
    for result in ranked:
        candidate=lookup[result['candidate_id']]
        if candidate['group'] not in seen:
            seen.add(candidate['group']);leaders.append(candidate['rule'])
        if len(leaders)==13:break
    if number==9:
        proposals=[]
        for field in ('long_entry_gap_pct','short_entry_gap_pct','long_recovery_pp','short_recovery_pp'):
            for delta in (-.4,-.25,-.12,.12,.25,.4):
                for parent in leaders:
                    value=dict(parent);value[field]=round(value[field]+delta,8)
                    if value['long_entry_gap_pct']<0<value['short_entry_gap_pct'] and min(value['long_recovery_pp'],value['short_recovery_pp'])>0:
                        proposals.append(('B_descendant_one_parameter_refinement',value))
        return proposals
    axes=[('max_hold_minutes',(720,7200,20160,43200)),('pnl_profit_pct',(.2,.5,.8)),('pnl_stop_pct',(.4,.8,1.2)),('confirmation_pp',(.08,.16)),('stall_minutes',(180,960,5760))]
    groups=[]
    for field,values in axes:
        group=[]
        for value in values:
            for parent in leaders:
                item=dict(parent,**{field:value})
                if field=='confirmation_pp':item.update(family='reversal',confirmation_expiry_calendar_minutes=240)
                group.append(('final_'+field,item))
        groups.append(group)
    return interleave(*groups)+wide+asym_r


def main():
    number=int(sys.argv[1]);assert 1<=number<=10
    assert json.loads((ROOT/'baseline_audit/validation.json').read_text())['status']=='PASS'
    if number>1:assert json.loads((ROOT/'publication'/f'batch_{number-1:04d}_results_verified.json').read_text())['status']=='PUBLISHED_VERIFIED'
    expected=next(x['sha256'] for x in json.loads((ROOT/'baseline/registry.json').read_text())['remote_files'] if x['file']=='settings_all_1000.json')
    assert hashlib.sha256(OLD.read_bytes()).hexdigest()==expected
    old=json.loads(OLD.read_text())
    result_path=OLD.parent/'results_all_1000.csv'
    expected_result=next(x['sha256'] for x in json.loads((ROOT/'baseline/registry.json').read_text())['remote_files'] if x['file']=='results_all_1000.csv')
    assert hashlib.sha256(result_path.read_bytes()).hexdigest()==expected_result
    with result_path.open(encoding='utf8',newline='') as stream:completed={r['candidate_id'] for r in csv.DictReader(stream)}
    assert len(completed)==1000 and completed<=set(old)
    assert set(old)-completed=={'CONTROL-S1-050-LUMP17'}
    used={signature(r) for r in old.values()};used.add(signature(BASE))
    for path in sorted((ROOT/'preregistration').glob('batch_*.json')) if (ROOT/'preregistration').exists() else []:
        for c in json.loads(path.read_text())['conditions']:used.add(signature(c['rule']))
    rows=[]
    for group,value in pools(number):
        key=signature(value)
        if key in used:continue
        assert value['family'] in ('relative','reversal') and not value.get('allowed_direction')
        assert value['long_absolute_exit_gap_pct'] is None and value['short_absolute_exit_gap_pct'] is None
        used.add(key)
        rows.append(dict(candidate_id=f'BF-{number:02d}-{len(rows)+1:03d}',group=group,parent_strategy='B:L17-01-013',rule=value,rule_sha256=hashlib.sha256(canonical(value)).hexdigest()))
        if len(rows)==50:break
    assert len(rows)==50,('NOT_ENOUGH_NEW_CONDITIONS',number,len(rows))
    registration=dict(batch=f'batch_{number:04d}',conditions=rows,grid_sha256=hashlib.sha256(canonical(rows)).hexdigest(),
        code_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((ROOT/'code').glob('*.py'))},
        groups={g:sum(r['group']==g for r in rows) for g in sorted({r['group'] for r in rows})},
        input_baseline_commit='e1254e5141b3201cf594111cbc47b1fdfd6a5e9a',parent_B=BASE,A_C_D_search_enabled=False,
        frozen=dict(contracts=17,spot_quantity=170000,futures_initial_cash=30000000,additional_entries=False,simultaneous_opposite=False,external_deposits=False,slippage_bp=2),
        objectives=dict(score_greater_than=14.95131907100779,cycles_at_least=39,residual_contracts=0,mdd_at_most_krw=9350000,margin_shortages=0),
        score='sum unrounded completed cycle net / abs(initial spot entry notional) * 100',
        margin_shortage_definition='Any entry admission rejection, observed initial or maintenance deficit, or underfunded roll',
        cost_and_execution='Frozen engine; signal next contiguous observed minute OPEN proxy, spot .05% per side, futures 600/contract + .000003157 notional per side; 2bp per leg per side; both roll legs',
        pnl_exit='Existing recovery OR net-profit/loss stop OR time/stall condition; net PNL signal includes hypothetical close costs',
        old_1000_recomputed=False,maximum_new_conditions=500,final_oos_access=False,mode='EXPLORATORY_PAPER')
    (ROOT/'preregistration').mkdir(exist_ok=True)
    write_json(ROOT/'preregistration'/f'batch_{number:04d}.json',registration)
    print(json.dumps(dict(batch=number,count=50,groups=registration['groups'],grid_sha256=registration['grid_sha256'])),flush=True)


if __name__=='__main__':main()
