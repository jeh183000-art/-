# /// script
# requires-python = "==3.12.0"
# dependencies = ["numpy==2.2.6"]
# ///
# Run: python -B code/bootstrap.py build_extension.py 1
import copy
import hashlib
import json
import sys
from itertools import product, zip_longest
from runner import ROOT, canonical, write_json

PRIOR=ROOT.parent/'lump17_sweep_20261021_01'

def rule(family='relative',e=1.,r=.5,**extra):
    value=dict(family=family,long_entry_gap_pct=-float(e),short_entry_gap_pct=float(e),
        long_recovery_pp=float(r),short_recovery_pp=float(r),long_absolute_exit_gap_pct=None,
        short_absolute_exit_gap_pct=None,confirmation_pp=0.,confirmation_expiry_calendar_minutes=None,
        max_hold_minutes=None,gap_stop_pp=None,pnl_stop_pct=None)
    value.update(extra)
    return value


def effective(value):
    out={k:v for k,v in value.items() if v is not None and v!=0}
    if value.get('allowed_direction')==1:
        out={k:v for k,v in out.items() if not k.startswith('short_')}
    if value.get('allowed_direction')==-1:
        out={k:v for k,v in out.items() if not k.startswith('long_')}
    for k in ('long_entry_gap_pct','short_entry_gap_pct','long_recovery_pp','short_recovery_pp'):
        if value['family'] in ('quantile','zscore'):out.pop(k,None)
    if value['family'] in ('mean','median','absolute'):
        out.pop('long_recovery_pp',None);out.pop('short_recovery_pp',None)
    return hashlib.sha256(canonical(out)).hexdigest()


def pools(number):
    absolute=[('independent_absolute',rule('absolute',e=e,long_recovery_pp=None,short_recovery_pp=None,
        long_absolute_exit_gap_pct=x,short_absolute_exit_gap_pct=-x))
        for e,x in product((.65,.95,1.25,1.55,1.85,2.15,2.45,2.85,3.25,3.75,4.25),(-.4,0.,.3,.7,1.1,1.4,1.8,2.2)) if x>-e]
    relative=[('independent_recovery',rule(e=e,r=r)) for e,r in product((.35,.65,.95,1.25,1.55,1.85,2.15,2.45,3.25,4.25),(.25,.55,.75,1.1,1.4,1.8,2.4,3.2))]
    centers=[('lagged_center',rule(f,e=e,window_observations=w,return_fraction=p))
        for w,e,p,f in product((120,480,2880),(.15,.35,.55,.85),( .35,.75,1.),('mean','median'))]
    volatility=[('lagged_volatility',rule('zscore',window_observations=w,z_entry=z,z_exit=x))
        for w,z,x in product((120,480,2880),(1.25,1.75,2.25,2.75),(-.5,.25,.75,1.25))]
    reversal=[('reversal',rule('reversal',e=e,r=r,confirmation_pp=c,confirmation_expiry_calendar_minutes=240))
        for e,r,c in product((.65,.95,1.25,1.65,2.15),(.35,.65,1.1,1.7),(.08,.15,.3))]
    if number==1:
        return [item for chunk in zip_longest(absolute,relative,centers,volatility,reversal) for item in chunk if item]
    if number==2:return absolute
    if number==3:
        return [('asymmetric_thresholds',rule('absolute',e=el,short_entry_gap_pct=es,long_recovery_pp=None,short_recovery_pp=None,
                    long_absolute_exit_gap_pct=xl,short_absolute_exit_gap_pct=xs))
            for el,es,xl,xs in product((.7,1.3,1.9,2.5),(.8,1.4,2.,2.6),(.2,.8,1.4),(-.3,-.9,-1.5))]
    if number==4:return centers
    if number==5:
        quantiles=[('causal_quantile',rule('quantile',window_observations=w,allowed_direction=d,max_hold_minutes=h))
            for w,d,h in product((120,480,2880,5760),(0,1,-1),(None,720,4320))]
        return [item for chunk in zip_longest(volatility,quantiles) for item in chunk if item]
    if number==6:return reversal
    if number==7:
        return [('asymmetric_recovery',rule(e=el,short_entry_gap_pct=es,r=rl,short_recovery_pp=rs))
            for el,es,rl,rs in product((.6,1.2,1.8,2.4),(.8,1.4,2.,2.6),(.3,.7,1.3),(.4,1.,1.8))]
    if number==8:
        return [('separate_direction',rule(e=e,r=r,allowed_direction=d))
            for e,r,d in product((.4,.7,1.,1.3,1.6,1.9,2.2),(.3,.6,1.,1.6),(1,-1))]
    registrations=[json.loads(p.read_text()) for p in sorted((ROOT/'preregistration').glob('batch_*.json'))]
    lookup={r['candidate_id']:r['rule'] for reg in registrations for r in reg['conditions']}
    results=[json.loads(p.read_text()) for p in sorted((ROOT/'batches').glob('batch_*/candidates/*/result.json'))]
    ranked=sorted([r for r in results if r['feasible'] and r['cycles']],key=lambda r:r['score_pct'],reverse=True)
    # One leading example per distinct family: risk/time changes never form a full cross product.
    leaders=[];seen=set()
    for result in ranked:
        r=lookup[result['candidate_id']]
        if r['family'] not in seen:leaders.append(r);seen.add(r['family'])
    if number==9:
        axes=[('max_hold_minutes',(240,1440,4320,10080,43200)),('gap_stop_pp',(.5,1.,2.)),
              ('pnl_stop_pct',(.5,1.,2.)),('pnl_profit_pct',(.5,1.,2.))]
        return [('one_risk_axis',dict(r,**{field:value})) for field,values in axes for value in values for r in leaders]
    axes=[('pnl_profit_pct',(.3,.6,1.2)),('pnl_stop_pct',(.5,1.,2.)),
          ('entry_session',('regular','night')),('stall_minutes',(360,1440)),('minimum_minute_volume',(20,100))]
    groups=[[(field+'_axis',dict(r,**{field:value})) for value in values for r in leaders] for field,values in axes]
    return [item for chunk in zip_longest(*groups) for item in chunk if item]


def main():
    number=int(sys.argv[1]);assert number==10
    assert json.loads((ROOT/'anchor_audit_v2/anchor_validation.json').read_text())['status']=='PASS'
    if number>1:assert json.loads((ROOT/'publication'/f'batch_{number-1:04d}_results_verified.json').read_text())['status']=='PUBLISHED_VERIFIED'
    old=[json.loads(p.read_text()) for p in sorted((PRIOR/'preregistration').glob('batch_*.json'))]
    current=[json.loads(p.read_text()) for p in sorted((ROOT/'preregistration').glob('batch_*.json'))] if (ROOT/'preregistration').exists() else []
    used={effective(c['rule']) for reg in old+current for c in reg['conditions']}
    used.add(effective(rule(e=1.,r=.5)))
    rows=[]
    for group,value in pools(number):
        key=effective(value)
        if key in used:continue
        used.add(key)
        rows.append(dict(candidate_id=f'L18-{number:02d}-{len(rows)+1:03d}',group=group,rule=value,rule_sha256=hashlib.sha256(canonical(value)).hexdigest()))
        if len(rows)==50:break
    assert len(rows)==50,('INSUFFICIENT_UNIQUE_CONDITIONS',number,len(rows))
    registration=dict(batch=f'batch_{number:04d}',conditions=rows,grid_sha256=hashlib.sha256(canonical(rows)).hexdigest(),
        code_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((ROOT/'code').glob('*.py'))},
        groups={g:sum(r['group']==g for r in rows) for g in sorted({r['group'] for r in rows})},
        controls=dict(contracts=17,spot_quantity=170000,futures_initial_cash=30000000,additions=False,simultaneous_opposite=False,external_deposits=False),
        duplicate_policy='Effective rule parameters deduplicated against old500, control and all extension preregistrations',
        causal_statistics='Exclude current bar; reset at roll; observation count windows; frozen mean/median targets; causal moving z/quantile exits',
        score='sum(unrounded completed-cycle net / absolute initial spot notional * 100)',new_condition_budget=500,
        exploratory_only=True,protected_final_oos_access=False)
    (ROOT/'preregistration').mkdir(exist_ok=True)
    write_json(ROOT/'preregistration'/f'batch_{number:04d}.json',registration)
    print(json.dumps(dict(batch=number,conditions=50,groups=registration['groups'],grid_sha256=registration['grid_sha256'])),flush=True)


if __name__=='__main__':main()
