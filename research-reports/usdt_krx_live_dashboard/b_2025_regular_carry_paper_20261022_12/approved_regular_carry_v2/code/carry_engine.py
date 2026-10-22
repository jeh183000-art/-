# /// script
# requires-python = ">=3.12"
# dependencies = ["numpy==2.2.6"]
# ///
# How to run: imported by run_carry_quarter.py; approved conditional carry only.
from __future__ import annotations
from dataclasses import dataclass,asdict
from typing import Mapping
from model import Q,INITIAL_F,Quote,Variant,Position,Costs,costs,execution,valuation,crossing

@dataclass(slots=True) # noqa: MUTABLE_OK
class State:
    """Mutable simulation account and pending-order accumulator, persisted across calendar boundaries."""
    sc:float=0.0
    fc:float=INITIAL_F
    realized:float=0.0
    counter:int=0
    pos:Position|None=None
    pending_entry:tuple[int,Quote]|None=None
    pending_exit:Quote|None=None
    exit_cause:str=''
    peakloss:float=0.0
    prev:Quote|None=None
    cycle_bridges:int=0
    cycle_unseen_minutes:float=0.0
    peak_equity:float=INITIAL_F
    mdd:float=0.0

    def encode(self)->Mapping:return asdict(self)

    @classmethod
    def restore(cls,r:Mapping)->State:
        values=dict(r)
        if r['pos'] is not None:
            p=r['pos'];values['pos']=Position(p['cycle'],p['direction'],Quote.parse(p['signal']),Quote.parse(p['entry']),p['sp'],p['fp'],Costs(**p['costs']))
        if r['prev'] is not None:values['prev']=Quote.parse(r['prev'])
        if r['pending_entry'] is not None:values['pending_entry']=(int(r['pending_entry'][0]),Quote.parse(r['pending_entry'][1]))
        if r['pending_exit'] is not None:values['pending_exit']=Quote.parse(r['pending_exit'])
        return cls(**values)

@dataclass(frozen=True,slots=True)
class TickResult:
    fills:tuple[Mapping,...]
    cycles:tuple[Mapping,...]
    signals:tuple[Mapping,...]
    mark:Mapping


def advance(s:State,q:Quote,v:Variant)->TickResult:
    fills=[];cycles=[];signals=[];closure=False
    if s.prev is not None:
        elapsed=(q.t-s.prev.t).total_seconds()/60;closure=elapsed!=1
        if closure:
            assert s.prev.t.date()!=q.t.date() and s.prev.t.strftime('%H:%M:%S')=='15:30:00' and q.t.strftime('%H:%M:%S')=='09:00:00'
            assert s.prev.reference_contract==q.reference_contract
            if s.pending_entry is not None or s.pending_exit is not None:
                signals.append(dict(kind='CANCEL_PENDING_AT_CLOSURE',t=q.t.isoformat(),direction=s.pos.direction if s.pos else 0,cycle=s.pos.cycle if s.pos else 0,gap=q.gap,reason='REEVALUATE_AT_OBSERVED_OPEN_NO_RETROACTIVE_FILL',source=q.source,line=q.line))
            s.pending_entry=None;s.pending_exit=None
            if s.pos is not None:s.cycle_bridges+=1;s.cycle_unseen_minutes+=elapsed-1
    if s.pending_exit is not None:
        p=s.pos;assert p is not None and (q.t-s.pending_exit.t).total_seconds()==60
        sp,fp=execution(q,p.direction,False);c=costs(sp,fp)
        sg=p.direction*(sp-p.sp)*Q;fg=p.direction*(p.fp-fp)*Q
        s.sc+=p.direction*sp*Q-c.sf-c.ss;s.fc+=fg-c.ff-c.fs
        net=sg+fg-p.costs.total-c.total;s.realized+=net;s.peakloss=max(s.peakloss,-net)
        fills.append(dict(kind='EXIT',cycle=p.cycle,t=q.t.isoformat(),signal_t=s.pending_exit.t.isoformat(),direction=p.direction,quantity_usdt=Q,contracts=17,spot_notional=sp*Q,future_notional=fp*Q,spot_gross=sg,future_gross=fg,spot_fee=c.sf,future_fee=c.ff,spot_slippage=c.ss,future_slippage=c.fs,spot_cash=s.sc,future_cash=s.fc,source=q.source,line=q.line,reason=s.exit_cause))
        cycles.append(dict(cycle=p.cycle,direction=p.direction,entry_signal_t=p.signal.t.isoformat(),entry_t=p.entry.t.isoformat(),exit_signal_t=s.pending_exit.t.isoformat(),exit_t=q.t.isoformat(),entry_signal_gap=p.signal.gap,exit_signal_gap=s.pending_exit.gap,entry_notional=p.sp*Q,spot_gross=sg,future_gross=fg,total_fees=p.costs.sf+p.costs.ff+c.sf+c.ff,total_slippage=p.costs.ss+p.costs.fs+c.ss+c.fs,net=net,return_pct=net/(p.sp*Q)*100,holding_minutes=(q.t-p.entry.t).total_seconds()/60,max_liquidation_loss_krw=s.peakloss,normal_closure_bridges=s.cycle_bridges,unobserved_calendar_minutes=s.cycle_unseen_minutes,exit_reason=s.exit_cause,rolls=0,actual_contract_and_borrow_verified=False))
        s.pos=None;s.pending_exit=None
    if s.pending_entry is not None:
        assert s.pos is None
        d,signal=s.pending_entry;assert (q.t-signal.t).total_seconds()==60
        sp,fp=execution(q,d,True);c=costs(sp,fp);s.counter+=1
        s.sc-=d*sp*Q+c.sf+c.ss;s.fc-=c.ff+c.fs
        s.pos=Position(s.counter,d,signal,q,sp,fp,c);s.peakloss=0.;s.cycle_bridges=0;s.cycle_unseen_minutes=0.
        fills.append(dict(kind='ENTRY',cycle=s.counter,t=q.t.isoformat(),signal_t=signal.t.isoformat(),direction=d,quantity_usdt=Q,contracts=17,spot_notional=sp*Q,future_notional=fp*Q,spot_gross=0.,future_gross=0.,spot_fee=c.sf,future_fee=c.ff,spot_slippage=c.ss,future_slippage=c.fs,spot_cash=s.sc,future_cash=s.fc,source=q.source,line=q.line,reason='MIDPOINT_THRESHOLD_CROSS'))
        s.pending_entry=None
    open_net=0.;fu=0.;reserved=0.;position=0;need=0.
    if s.pos is not None:
        p=s.pos;open_net,fu,c=valuation(p,q);reserved=c.total;position=p.direction;need=p.sp*Q;s.peakloss=max(s.peakloss,-open_net)
        gap_exit=p.direction*(q.gap-p.signal.gap)>=.6-1e-12
        pnl_exit=v.pnl_target is not None and open_net/(p.sp*Q)*100>=v.pnl_target-1e-12
        if gap_exit or pnl_exit:
            s.pending_exit=q;s.exit_cause='BOTH' if gap_exit and pnl_exit else 'RECOVERY' if gap_exit else 'PNL_TARGET'
            signals.append(dict(kind='EXIT_SIGNAL',t=q.t.isoformat(),direction=p.direction,cycle=p.cycle,gap=q.gap,reason=s.exit_cause,source=q.source,line=q.line))
    elif s.prev is not None and not closure:
        d=crossing(s.prev,q)
        if d:
            s.pending_entry=(d,q);signals.append(dict(kind='ENTRY_SIGNAL',t=q.t.isoformat(),direction=d,cycle=s.counter+1,gap=q.gap,reason='MIDPOINT_THRESHOLD_CROSS',source=q.source,line=q.line))
    total=s.realized+open_net;eq=INITIAL_F+total;s.peak_equity=max(s.peak_equity,eq);dd=s.peak_equity-eq;s.mdd=max(s.mdd,dd)
    mark=dict(t=q.t.isoformat(),cycle=s.pos.cycle if s.pos else 0,held_direction=position,contracts=17 if s.pos else 0,spot_cash=s.sc,future_cash=s.fc,future_unrealized=fu,realized_net=s.realized,open_net_after_close_cost=open_net,estimated_exit_cost=reserved,combined_pnl=total,combined_equity=eq,required_spot_notional=need,running_equity_peak=s.peak_equity,current_drawdown=dd,cumulative_mdd=s.mdd,future_account_equity=s.fc+fu,first_quote_after_closure=closure,margin='UNVERIFIED',source=q.source,line=q.line)
    s.prev=q
    return TickResult(tuple(fills),tuple(cycles),tuple(signals),mark)


def residual(s:State,reason:str)->Mapping|None:
    if s.pos is None:return None
    p=s.pos;q=s.prev;assert q is not None
    net,fg,c=valuation(p,q)
    return dict(cycle=p.cycle,direction=p.direction,entry_t=p.entry.t.isoformat(),last_observed_t=q.t.isoformat(),contracts=17,entry_notional=p.sp*Q,liquidation_estimate_net=net,future_unrealized=fg,estimated_close_cost=c.total,holding_minutes=(q.t-p.entry.t).total_seconds()/60,max_liquidation_loss_krw=s.peakloss,normal_closure_bridges=s.cycle_bridges,unobserved_calendar_minutes=s.cycle_unseen_minutes,pending_exit_at_boundary=s.pending_exit is not None,status='UNVERIFIABLE_OPEN_NOT_REALIZED',risk_reason=reason)
