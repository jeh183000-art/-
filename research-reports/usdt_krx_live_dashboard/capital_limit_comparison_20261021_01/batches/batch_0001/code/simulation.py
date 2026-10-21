# /// script
# requires-python = "==3.12.0"
# dependencies = ["numpy==2.2.6"]
# ///
"""Observed-bar signal transitions with admission checked at execution time."""
from __future__ import annotations
import math
from dataclasses import dataclass
import numpy as np
from accounts import Accounts, ExecutionPrice, Limits, Lot, Q, costs

@dataclass(frozen=True,slots=True)
class Experiment:
    name: str
    strategy: str
    limits: Limits

@dataclass(slots=True)
class Outcome:
    account: Accounts
    marks: list[dict]
    rejections: list[dict]
    stress: list[dict]

def simulate(v: tuple[np.ndarray,...], case: Experiment) -> Outcome:
    book=Accounts(case.limits)
    marks=[]
    rejected=[]
    stress={}
    pending=[]
    close_reason=''
    cycle=serial=0
    armed=0
    trough=armed_at=0.
    def price(i: int, phase: str) -> ExecutionPrice:
        match phase:
            case 'OPEN': s,f=v[5][i],v[7][i]
            case 'CLOSE': s,f=v[6][i],v[8][i]
            case 'SETTLEMENT': s,f=v[15][i],v[14][i]
            case unexpected: raise AssertionError(unexpected)
        return ExecutionPrice(i,phase,float(s),float(f),float(v[16][i]),float(v[17][i]))
    for i in range(len(v[0])):
        p=price(i,'OPEN')
        if v[9][i] and book.lots:
            old=ExecutionPrice(i,'ROLL',p.spot,float(v[10][i]),p.initial,p.maintenance)
            m=book.mark(old,False)
            count=len(book.lots)
            _,cf,_,cs=costs(old)
            _,of,_,os=costs(p)
            after=m['future_equity']-count*(cf+cs+of+os)
            if case.limits.enabled and (after<count*p.future*Q*p.initial-1e-7 or after<0):
                book.exit_all(old,'ROLL_MARGIN_FORCED')
                pending=[]
                close_reason=''
            else:
                book.roll(old,p)
        if v[12][i]:
            if close_reason:
                book.exit_all(p,close_reason)
                close_reason=''
                pending=[]
            else:
                for stage,d,signal,target in pending:
                    if any(l.stage==stage for l in book.lots):
                        continue
                    reason=book.reason(p) if case.limits.enabled else 'ACCEPT'
                    if reason!='ACCEPT':
                        rejected.append(dict(row=i,signal_row=signal,stage=stage,direction=d,reason=reason,**{k:v for k,v in book.mark(p,False).items() if k not in ('row','phase')}))
                        continue
                    if not book.lots:
                        cycle+=1
                    serial+=1
                    book.enter(Lot(serial,cycle,stage,d,i,signal,p.spot,p.future,p.future,target),p)
            pending=[]
        breach=False
        for phase in ('OPEN','CLOSE','SETTLEMENT'):
            if phase=='SETTLEMENT' and not v[13][i]:
                continue
            pmark=price(i,phase)
            if phase=='SETTLEMENT':
                book.settle(pmark)
            m=book.mark(pmark)
            marks.append(m)
            breach=breach or m['maintenance_headroom'] < -1e-7 or m['spot_available'] < -1e-7
            if book.lots and case.limits.enabled:
                for shock in (.05,.07,.10):
                    d=book.lots[0].direction
                    sf=pmark.future*(1+d*shock)
                    sfuture=m['future_equity']-len(book.lots)*pmark.future*Q*shock
                    need=len(book.lots)*sf*Q*pmark.maintenance
                    record=dict(row=i,phase=phase,shock_pct=shock*100,contracts=len(book.lots),future_price=pmark.future,
                        stressed_price=sf,spot_assumption='UNCHANGED_ISOLATED_FUTURES_SHOCK',future_equity_after_shock=sfuture,
                        maintenance_after_shock=need,headroom_after_shock=sfuture-need,
                        portfolio_shock_loss=len(book.lots)*pmark.future*Q*shock)
                    key=(shock,len(book.lots))
                    if key not in stress or record['headroom_after_shock']<stress[key]['headroom_after_shock']:
                        stress[key]=record
        next_ok=i+1<len(v[0]) and bool(v[12][i+1])
        if case.limits.enabled and breach and book.lots:
            if next_ok:
                close_reason='MAINTENANCE_OR_SPOT_COLLATERAL_FORCED'
            continue
        if book.lots and next_ok and not v[9][i]:
            d=book.lots[0].direction
            if d*(v[4][i]-book.lots[0].target)>=-1e-12:
                close_reason='TARGET'
        if case.strategy=='U-007206':
            if next_ok and not v[9][i] and not close_reason and v[12][i] and i>0:
                start=max(0,math.floor(-(v[4][i-1]+.8)/.2+1e-10)+1)
                end=math.floor((-.8-v[4][i])/.2+1e-10)
                for k in range(start,end+1):
                    if all(l.stage!=k for l in book.lots):
                        pending.append((k,1,i,-.5))
        elif not book.lots and next_ok and not v[9][i]:
            sign=0
            if v[12][i] and i>0:
                if v[4][i]<=-1 and v[4][i-1]>-1:
                    sign=1
                if case.strategy=='S1-050' and v[4][i]>=1 and v[4][i-1]<1:
                    sign=-1
            if case.strategy=='S1-037':
                if not v[12][i] or v[9][i] or (armed and v[0][i]-armed_at>240):
                    armed=0
                if sign:
                    armed,trough,armed_at=sign,sign*v[4][i],v[0][i]
                sign=0
                if armed:
                    oriented=armed*v[4][i]
                    trough=min(trough,oriented)
                    if oriented>=0:
                        armed=0
                    elif oriented>=trough+.1:
                        sign,armed=armed,0
            if sign:
                pending=[(0,sign,i,float(v[4][i]+sign*.5))]
        else:
            armed=0
    return Outcome(book,marks,rejected,list(stress.values()))
