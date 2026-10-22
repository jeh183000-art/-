# /// script
# requires-python = "==3.12.0"
# dependencies = ["numpy==2.2.6"]
# ///
# Five path hypotheses, 100 each; fixed before any new simulation.
from __future__ import annotations
from itertools import zip_longest
from registry import BASE
from path_schema import PathRule

def seeds() -> list[PathRule]:
    """Keep the original B and broad asymmetric entries, not only its neighborhood."""
    return [dict(BASE,long_entry_gap_pct=-l,short_entry_gap_pct=s)
            for l,s in ((.97,.85),(.4,1.6),(1.6,.4),(.65,1.3),(1.3,.65),(2.2,1.1),(1.1,2.2),(2.8,2.8))]

def interleave(groups: list[list[tuple[str,PathRule]]]) -> list[tuple[str,PathRule]]:
    return [r for chunk in zip_longest(*groups) for r in chunk if r is not None]

def pools(category: int) -> list[tuple[str,PathRule]]:
    """All proposals are post-observation exploratory hypotheses, never OOS claims."""
    anchors=seeds()
    if category==1:
        return [('directional_entry_recovery',dict(BASE,
            long_entry_gap_pct=-(.25,.5,.8,1.2,1.6,2.1,2.7,3.5)[i%8],
            short_entry_gap_pct=(.3,.6,.95,1.4,1.9,2.5,3.2)[(i//8+shift)%7],
            long_recovery_pp=(.25,.5,.75,1.1)[(i+shift)%4],
            short_recovery_pp=(.3,.6,.9,1.3)[(i//4+shift)%4]))
            for shift in range(12) for i in range(56)]
    if category==2:
        variants=[dict(pnl_profit_pct=0.),dict(pnl_profit_pct=.7),
            dict(pnl_profit_pct=.7,pnl_profit_long_pct=.3,pnl_profit_short_pct=.9),
            dict(pnl_profit_pct=.7,pnl_profit_long_pct=1.1,pnl_profit_short_pct=.35),
            dict(pnl_profit_pct=.7,pnl_profit_long_pct=0.,pnl_profit_short_pct=.7),
            dict(pnl_profit_pct=.7,pnl_profit_long_pct=.7,pnl_profit_short_pct=0.)]
        return [('matched_exit_ablation',dict(a,long_recovery_pp=r,short_recovery_pp=r,**variant))
            for r in (.25,.45,.6,.85,1.2) for a in anchors for variant in variants]
    if category==3:
        groups=[]
        for c in (0.,.04,.12,.3):
            groups.append([('confirmation_reentry',dict(a,confirmation_pp=c,
                confirmation_min_observations=bars,confirmation_expiry_calendar_minutes=expiry,
                cooldown_minutes=cool))
                for cool in (0,30,180,720) for bars in (2,5,10) for expiry in (30,120,240) for a in anchors])
        groups.append([('cooldown_new_cross_only',dict(a,cooldown_minutes=c)) for c in (15,60,360,1440) for a in anchors])
        return interleave(groups)
    if category==4:
        groups=[]
        for mode in ('mean_shift','median_shift','volatility'):
            groups.append([('causal_'+mode,dict(a,threshold_mode=mode,window_observations=w,
                center_weight=weight,volatility_entry_scale=(mode=='volatility'),
                volatility_recovery_scale=dynamic))
                for w in (60,180,360) for weight in (.35,.7) for dynamic in (False,True) for a in anchors])
        return interleave(groups)
    groups=[]
    for field,values in [('max_hold_minutes',(720,2160,5760,11520,21600,43200)),
                         ('stall_minutes',(240,1440,5760,11520)),
                         ('pnl_stop_pct',(.3,.8,1.8,3.)),
                         ('gap_stop_pp',(.4,.9,1.7,2.5))]:
        groups.append([('risk_'+field,dict(a,**{field:value})) for value in values for a in anchors])
    groups.append([('risk_time_and_stall',dict(a,max_hold_minutes=t,stall_minutes=s))
        for t,s in ((4320,720),(10080,2880),(20160,5760),(40320,11520)) for a in anchors])
    return interleave(groups)
