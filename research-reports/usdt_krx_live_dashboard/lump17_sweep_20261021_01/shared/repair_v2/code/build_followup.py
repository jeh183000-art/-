from __future__ import annotations

import copy
import hashlib
import json
import sys

from runner import ROOT, canonical, write_json


def rule(family='relative', e=1., r=.5, **extra):
    value=dict(family=family,long_entry_gap_pct=-float(e),short_entry_gap_pct=float(e),
               long_recovery_pp=float(r),short_recovery_pp=float(r),long_absolute_exit_gap_pct=None,
               short_absolute_exit_gap_pct=None,confirmation_pp=0.,confirmation_expiry_calendar_minutes=None,
               max_hold_minutes=None,gap_stop_pp=None,pnl_stop_pct=None)
    value.update(extra)
    return value


def pool(number, leaders):
    if number==2:
        for e in (.3,.5,1.5,2.,2.5,3.,3.5,4.):
            for r in (.2,.4,.6,.8,1.,1.5,2.):yield 'wide_relative',rule(e=e,r=r)
    elif number==3:
        for window in (60,240,720,1440,4320):
            for e in (.2,.4,.6):
                for fraction in (.5,1.):
                    for family in ('mean','median'):
                        yield 'lagged_center_regression',rule(family,e=e,window_observations=window,return_fraction=fraction)
    elif number==4:
        for window in (60,240,720,1440,4320):
            for z in (1.,1.5,2.,2.5):
                for exit_z in (0.,.5):yield 'lagged_volatility',rule('zscore',window_observations=window,z_entry=z,z_exit=exit_z)
        for window in (60,240,720,1440,4320):
            for direction in (0,1):yield 'lagged_quantile_10_90',rule('quantile',window_observations=window,allowed_direction=direction)
    elif number==5:
        for e in (.5,.8,1.,1.5,2.):
            for confirm in (.05,.1,.2):
                for r in (.4,.8):yield 'reversal_wider',rule('reversal',e=e,r=r,confirmation_pp=confirm,confirmation_expiry_calendar_minutes=240)
        for e in (.8,1.2):
            for r in (.4,.8):
                for hold in (60,240,720,1440,4320):yield 'calendar_time_exit',rule(e=e,r=r,max_hold_minutes=hold)
    elif number==6:
        for el in (.5,.8,1.1,1.5,2.):
            for es in (.6,1.,1.4,2.,3.):
                for rl,rs in ((.4,.8),(.8,.4)):
                    yield 'wide_asymmetric',rule(e=el,r=rl,short_entry_gap_pct=es,short_recovery_pp=rs)
    elif number==7:
        entry_leaders=[c for c in leaders if c['family'] in ('relative','reversal','mean','median','absolute')]
        for candidate in entry_leaders[:15]:
            for delta in (-.2,-.1,.1,.2):
                value=copy.deepcopy(candidate)
                value['long_entry_gap_pct']=round(value['long_entry_gap_pct']-delta,8)
                value['short_entry_gap_pct']=round(value['short_entry_gap_pct']+delta,8)
                if value['long_entry_gap_pct']<0<value['short_entry_gap_pct']:yield 'adaptive_entry_neighbours',value
            for delta in (-.1,.1):
                value=copy.deepcopy(candidate)
                if value['family'] in ('relative','reversal') and value.get('long_recovery_pp') and value.get('short_recovery_pp'):
                    value['long_recovery_pp']=round(value['long_recovery_pp']+delta,8)
                    value['short_recovery_pp']=round(value['short_recovery_pp']+delta,8)
                    if min(value['long_recovery_pp'],value['short_recovery_pp'])>0:yield 'adaptive_recovery_neighbours',value
    elif number==8:
        for candidate in leaders:
            if candidate.get('allowed_direction',0)==0:
                yield 'long_only_borrow_free_auxiliary',dict(candidate,allowed_direction=1)
    elif number==9:
        for candidate in leaders[:20]:
            for field, values in [('max_hold_minutes',(360,1440,4320)),('gap_stop_pp',(.5,1.)),('pnl_stop_pct',(1.,2.))]:
                for value in values:yield 'adaptive_one_risk_axis',dict(candidate,**{field:value})
    elif number==10:
        for candidate in leaders[:30]:
            for session in ('regular','night'):yield 'entry_session_auxiliary',dict(candidate,entry_session=session)
            for minutes in (240,720):yield 'stalled_recovery_auxiliary',dict(candidate,stall_minutes=minutes)
    else:raise ValueError(number)


def main():
    number=int(sys.argv[1]);assert 2<=number<=10
    prior_receipt=json.loads((ROOT/'publication'/f'batch_{number-1:04d}_results_verified.json').read_text())
    assert prior_receipt['status']=='PUBLISHED_VERIFIED'
    registrations=[json.loads(p.read_text()) for p in sorted((ROOT/'preregistration').glob('batch_*.json'))]
    previous=[row for registration in registrations for row in registration['conditions']]
    used={row['rule_sha256'] for row in previous}
    scores=[]
    for path in sorted((ROOT/'batches').glob('batch_*/candidates/*/result.json')):
        result=json.loads(path.read_text())
        if result['feasible'] and result['cycles']>0:scores.append(result)
    scores.sort(key=lambda x:x['score_pct'],reverse=True)
    lookup={row['candidate_id']:row['rule'] for row in previous}
    leaders=[lookup[row['candidate_id']] for row in scores]
    rows=[]
    for group,value in pool(number,leaders):
        key=hashlib.sha256(canonical(value)).hexdigest()
        if key in used:continue
        used.add(key)
        rows.append(dict(candidate_id=f'L17-{number:02d}-{len(rows)+1:03d}',group=group,rule=value,rule_sha256=key))
        if len(rows)==50:break
    assert len(rows)==50,('INSUFFICIENT_UNIQUE_RULES',number,len(rows))
    registration=copy.deepcopy(registrations[0])
    registration.update(batch=f'batch_{number:04d}',conditions=rows,grid_sha256=hashlib.sha256(canonical(rows)).hexdigest(),
        groups={group:sum(row['group']==group for row in rows) for group in sorted({row['group'] for row in rows})},
        adaptive_exploration=number>=7,previous_batch_commit=prior_receipt['commit'],
        dynamic_definition='Trailing statistics exclude current observation and reset on contract roll. Mean/median partial-return target frozen at signal; zscore and quantile exits recomputed causally.',
        duplicates='Exact rule hashes excluded across this 17-contract study; baseline 1.0/.5 excluded. Earlier 1-contract or multi-add signal overlaps are not independent discoveries.',
        budget='All candidates, including long-only auxiliaries, count inside 500 new conditions. Baseline CONTROL excluded.')
    write_json(ROOT/'preregistration'/f'batch_{number:04d}.json',registration)
    print(json.dumps(dict(batch=number,conditions=50,grid_sha256=registration['grid_sha256'],groups=registration['groups'])),flush=True)


if __name__=='__main__':main()
