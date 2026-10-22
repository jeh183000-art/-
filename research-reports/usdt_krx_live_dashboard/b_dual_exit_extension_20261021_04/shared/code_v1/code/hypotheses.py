# /// script
# requires-python = "==3.12.0"
# dependencies = ["numpy==2.2.6"]
# ///
# Pools for build_B.py, frozen before the first market run.
from __future__ import annotations
import json
from typing import Final
from runner import ROOT
from rules import BASE,Rule,rule,interleave

SEEDS: Final[list[Rule]]=[rule(),rule(e=.65),rule(e=1.3),rule(e=.75,short_entry_gap_pct=1.15),rule(e=1.45,short_entry_gap_pct=.6),rule(e=.5,short_entry_gap_pct=1.8),rule(e=2.2,short_entry_gap_pct=1.1),rule(e=1.1,short_entry_gap_pct=2.2)]

def pools(number: int) -> list[tuple[str,Rule]]:
    """Coarse entry only, separate exits, joint/asymmetric exits, confirmation, then risk."""
    longs=(.35,.55,.75,.95,1.15,1.45,1.85,2.3,2.8,3.4)
    shorts=(.3,.5,.7,.9,1.1,1.4,1.8,2.2,2.7,3.3)
    entry=[('dual_exit_entry_only',rule(e=e,short_entry_gap_pct=shorts[(i+shift)%10])) for shift in range(10) for i,e in enumerate(longs)]
    otherl=(.25,.45,.65,.85,1.05,1.25,1.6,2.05,2.55,3.05)
    others=(.35,.55,.75,.95,1.25,1.65,2.05,2.45,3.05,3.65)
    entry += [('dual_exit_entry_only_broad',rule(e=e,short_entry_gap_pct=others[(i+shift)%10])) for shift in range(10) for i,e in enumerate(otherl)]
    if number in (1,2):return entry
    if number==3:
        return [('recovery_only',dict(seed,long_recovery_pp=r,short_recovery_pp=r)) for r in (.15,.25,.35,.45,.55,.75,.9,1.1,1.4,1.8) for seed in SEEDS]
    if number==4:
        return [('net_profit_only',dict(seed,pnl_profit_pct=p)) for p in (.08,.12,.18,.28,.4,.55,.85,1.1,1.5,2.2,3.,.95) for seed in SEEDS]
    if number==5:
        rs=(.25,.4,.55,.8,1.1,1.5);ps=(.15,.3,.5,.75,1.,1.5)
        return [('joint_recovery_profit',dict(seed,long_recovery_pp=r,short_recovery_pp=r,pnl_profit_pct=ps[(i+shift+j)%6])) for shift in range(6) for i,r in enumerate(rs) for j,seed in enumerate(SEEDS)]
    if number==6:
        rl=(.2,.35,.5,.75,1.,1.4);rr=(.25,.45,.65,.9,1.2,1.6);ps=(.35,.7,1.1)
        return [('asymmetric_recovery_dual_exit',dict(seed,long_recovery_pp=r,short_recovery_pp=rr[(i+shift)%6],pnl_profit_pct=ps[(shift+i+j)%3])) for shift in range(6) for i,r in enumerate(rl) for j,seed in enumerate(SEEDS)]
    if number==7:
        return [('confirmed_dual_exit',dict(seed,family='reversal',confirmation_pp=c,confirmation_expiry_calendar_minutes=240,long_recovery_pp=(.4,.6,.9,1.2)[(i+j)%4],short_recovery_pp=(.4,.6,.9,1.2)[(i+j)%4],pnl_profit_pct=(.35,.7,1.05)[(i+j)%3])) for i,c in enumerate((.03,.08,.15,.3,.5,.7)) for j,seed in enumerate(SEEDS)] + [('confirmed_dual_exit_additional',dict(seed,family='reversal',confirmation_pp=c,confirmation_expiry_calendar_minutes=240)) for c in (.05,.12,.25,.4,.6) for seed in SEEDS]
    if number==8:
        time=[('dual_exit_time_cap',dict(seed,max_hold_minutes=h)) for h in (720,2880,10080,20160,30240) for seed in SEEDS]
        loss=[('dual_exit_net_loss_stop',dict(seed,pnl_stop_pct=p)) for p in (.5,1.2,2.5) for seed in SEEDS]
        gap=[('dual_exit_gap_stop',dict(seed,gap_stop_pp=p)) for p in (.5,1.25,2.) for seed in SEEDS]
        stall=[('dual_exit_stall',dict(seed,stall_minutes=h)) for h in (480,4320,14400) for seed in SEEDS]
        return interleave(time,loss,gap,stall)
    lookup={c['candidate_id']:c for path in sorted((ROOT/'preregistration').glob('batch_*.json')) for c in json.loads(path.read_text())['conditions']}
    results=[json.loads(path.read_text()) for path in sorted((ROOT/'batches').glob('batch_*/candidates/*/result.json'))]
    structural=lambda r: r['cycles']>=42 and r['residual_contracts']==0 and r['mdd_krw']<=9350000.01 and r['margin_shortage_free']
    ranked=sorted([r for r in results if r['feasible'] and r['cycles']],key=lambda r:(structural(r),r['score_pct']),reverse=True)
    leaders=[dict(BASE)];groups=set()
    for result in ranked:
        candidate=lookup[result['candidate_id']]
        if candidate['group'] not in groups:leaders.append(dict(candidate['rule']));groups.add(candidate['group'])
        if len(leaders)==12:break
    if number==9:
        groups=[]
        for field in ('long_entry_gap_pct','short_entry_gap_pct','long_recovery_pp','short_recovery_pp','pnl_profit_pct'):
            proposals=[]
            for delta in (-.5,-.25,-.1,.1,.25,.5):
                for parent in leaders:
                    value=dict(parent);value[field]=round(value[field]+delta,8)
                    if value['long_entry_gap_pct']<0<value['short_entry_gap_pct'] and min(value['long_recovery_pp'],value['short_recovery_pp'],value['pnl_profit_pct'])>0:proposals.append(('dual_exit_one_axis_refinement',value))
            groups.append(proposals)
        return interleave(*groups)
    proposals=[]
    for field,values in [('minimum_minute_volume',(5,25,100,300)),('entry_session',('regular','night')),('confirmation_pp',(.05,.2,.4)),('max_hold_minutes',(5760,14400,43200)),('stall_minutes',(960,5760))]:
        group=[]
        for value in values:
            for parent in leaders:
                item=dict(parent,**{field:value})
                if field=='confirmation_pp':item.update(family='reversal',confirmation_expiry_calendar_minutes=240)
                group.append(('dual_exit_final_'+field,item))
        proposals.append(group)
    return interleave(*proposals)+entry
