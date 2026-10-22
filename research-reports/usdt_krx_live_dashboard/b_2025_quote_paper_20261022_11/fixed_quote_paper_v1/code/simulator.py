# /// script
# requires-python = ">=3.12"
# dependencies = ["numpy==2.2.6"]
# ///
# How to run: invoked only by fixed_rule_run.py.
from __future__ import annotations
from dataclasses import asdict,dataclass
from typing import Mapping
from model import Q,INITIAL_F,Quote,Variant,Position,Book,costs,execution,valuation,crossing,frozen_drawdowns

@dataclass(frozen=True,slots=True)
class SegmentRun:
    book:Book
    fills:tuple[Mapping,...]
    cycles:tuple[Mapping,...]
    marks:tuple[Mapping,...]
    residual:Mapping|None
    canceled_entries:int


def run_segment(quotes:list[Quote],variant:Variant,book:Book)->SegmentRun:
    """One held bundle at most; a censored open bundle is never liquidated or rolled."""
    sc,fc,realized,counter=book.spot_cash,book.future_cash,book.realized,book.cycle_counter
    fills=[];cycles=[];marks=[];pos=None;pending_entry=None;pending_exit=None
    peakloss=0.0;exit_cause='';entry_ignored=0
    for i,q in enumerate(quotes):
        if i:
            assert (q.t-quotes[i-1].t).total_seconds()==60
        if pending_exit is not None:
            assert pos is not None and (q.t-pending_exit.t).total_seconds()==60
            sp,fp=execution(q,pos.direction,False);c=costs(sp,fp)
            sg=pos.direction*(sp-pos.sp)*Q;fg=pos.direction*(pos.fp-fp)*Q
            sc+=pos.direction*sp*Q-c.sf-c.ss;fc+=fg-c.ff-c.fs
            net=sg+fg-pos.costs.total-c.total;realized+=net;peakloss=max(peakloss,-net)
            fills.append(dict(kind='EXIT',cycle=pos.cycle,t=q.t.isoformat(),signal_t=pending_exit.t.isoformat(),direction=pos.direction,quantity_usdt=Q,contracts=17,spot_notional=sp*Q,future_notional=fp*Q,spot_gross=sg,future_gross=fg,spot_fee=c.sf,future_fee=c.ff,spot_slippage=c.ss,future_slippage=c.fs,spot_cash=sc,future_cash=fc,source=q.source,line=q.line,reason=exit_cause))
            cycles.append(dict(cycle=pos.cycle,direction=pos.direction,entry_signal_t=pos.signal.t.isoformat(),entry_t=pos.entry.t.isoformat(),exit_signal_t=pending_exit.t.isoformat(),exit_t=q.t.isoformat(),entry_signal_gap=pos.signal.gap,exit_signal_gap=pending_exit.gap,entry_notional=abs(pos.sp*Q),spot_gross=sg,future_gross=fg,total_fees=pos.costs.sf+pos.costs.ff+c.sf+c.ff,total_slippage=pos.costs.ss+pos.costs.fs+c.ss+c.fs,net=net,return_pct=net/abs(pos.sp*Q)*100,holding_minutes=(q.t-pos.entry.t).total_seconds()/60,max_liquidation_loss_krw=peakloss,exit_reason=exit_cause,rolls=0,borrowing_verified=False))
            pos=None;pending_exit=None
        if pending_entry is not None:
            assert pos is None
            direction,signal=pending_entry
            assert (q.t-signal.t).total_seconds()==60
            sp,fp=execution(q,direction,True);c=costs(sp,fp);counter+=1
            sc-=direction*sp*Q+c.sf+c.ss;fc-=c.ff+c.fs
            pos=Position(counter,direction,signal,q,sp,fp,c);peakloss=0.0
            fills.append(dict(kind='ENTRY',cycle=counter,t=q.t.isoformat(),signal_t=signal.t.isoformat(),direction=direction,quantity_usdt=Q,contracts=17,spot_notional=sp*Q,future_notional=fp*Q,spot_gross=0.,future_gross=0.,spot_fee=c.sf,future_fee=c.ff,spot_slippage=c.ss,future_slippage=c.fs,spot_cash=sc,future_cash=fc,source=q.source,line=q.line,reason='MIDPOINT_THRESHOLD_CROSS'))
            pending_entry=None
        open_net=0.0;fu=0.0;reserved=0.0;position=0;need=0.0
        if pos is not None:
            open_net,fu,c=valuation(pos,q);reserved=c.total;position=pos.direction;need=pos.sp*Q
            peakloss=max(peakloss,-open_net)
            gap_exit=pos.direction*(q.gap-pos.signal.gap)>=.6-1e-12
            pnl_exit=variant.pnl_target is not None and open_net/abs(pos.sp*Q)*100>=variant.pnl_target-1e-12
            if gap_exit or pnl_exit:
                pending_exit=q;exit_cause='BOTH' if gap_exit and pnl_exit else 'RECOVERY' if gap_exit else 'PNL_TARGET'
            if i and crossing(quotes[i-1],q):entry_ignored+=1
        elif i:
            direction=crossing(quotes[i-1],q)
            if direction:pending_entry=(direction,q)
        total=realized+open_net
        marks.append(dict(t=q.t.isoformat(),cycle=pos.cycle if pos else 0,held_direction=position,contracts=17 if pos else 0,spot_cash=sc,future_cash=fc,future_unrealized=fu,realized_net=realized,open_net_after_close_cost=open_net,estimated_exit_cost=reserved,combined_pnl=total,combined_equity=INITIAL_F+total,required_spot_notional=need,initial_margin='UNVERIFIED',maintenance_margin='UNVERIFIED',depth_and_fill='UNVERIFIED',source=q.source,line=q.line))
    residual=None
    if pos is not None:
        net,fg,closing=valuation(pos,quotes[-1])
        residual=dict(cycle=pos.cycle,direction=pos.direction,entry_t=pos.entry.t.isoformat(),last_observed_t=quotes[-1].t.isoformat(),contracts=17,entry_notional=pos.sp*Q,liquidation_estimate_net=net,future_unrealized=fg,estimated_close_cost=closing.total,holding_minutes=(quotes[-1].t-pos.entry.t).total_seconds()/60,max_liquidation_loss_krw=peakloss,pending_exit_at_boundary=pending_exit is not None,status='UNVERIFIABLE_OPEN_NOT_REALIZED',full_year_chain_continuation=False)
    return SegmentRun(Book(sc,fc,realized,counter),tuple(fills),tuple(cycles),tuple(marks),residual,int(pending_entry is not None))
