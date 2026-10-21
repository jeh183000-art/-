# /// script
# requires-python = "==3.12.0"
# dependencies = ["numpy==2.2.6"]
# ///
"""All-or-none hedge bundles; unspecified broker liquidation is never invented."""
from __future__ import annotations
import math
from dataclasses import dataclass
from typing import Literal, assert_never
import numpy as np
from accounts import Accounts, ExecutionPrice, Limits, Lot, Q, costs

@dataclass(frozen=True,slots=True)
class Experiment:
    name: str
    strategy: Literal['U-007206','S1-050']
    limits: Limits
    entry_bundle: int

@dataclass(frozen=True,slots=True)
class Outcome:
    account: Accounts
    marks: list[dict]
    orders: list[dict]
    deficits: list[dict]

def simulate(v: tuple[np.ndarray,...], case: Experiment) -> Outcome:
    book=Accounts(case.limits)
    marks=[];orders=[];deficits=[];pending=[]
    close_pending=False
    cycle=serial=order_serial=0
    split=case.strategy=='U-007206'
    def price(i: int, phase: Literal['OPEN','CLOSE','SETTLEMENT']) -> ExecutionPrice:
        match phase:
            case 'OPEN': s,f=v[5][i],v[7][i]
            case 'CLOSE': s,f=v[6][i],v[8][i]
            case 'SETTLEMENT': s,f=v[15][i],v[14][i]
            case unexpected: assert_never(unexpected)
        return ExecutionPrice(i,phase,float(s),float(f),float(v[16][i]),float(v[17][i]))
    for i in range(len(v[0])):
        p=price(i,'OPEN')
        if v[9][i] and book.lots:
            old=ExecutionPrice(i,'ROLL',p.spot,float(v[10][i]),p.initial,p.maintenance)
            m=book.mark(old,False);count=len(book.lots)
            _,cf,_,cs=costs(old);_,of,_,os=costs(p)
            after=m['future_equity']-count*(cf+cs+of+os)
            if case.limits.enabled and (after<count*p.future*Q*p.initial-1e-7 or after<0):
                deficits.append(dict(row=i,phase='ROLL',kind='ROLL_INITIAL_MARGIN',deficit=max(count*p.future*Q*p.initial-after,-after),contracts=count))
            book.roll(old,p)
        if v[12][i]:
            if close_pending:
                book.exit_all(p,'TARGET');close_pending=False;pending=[]
            else:
                bundles=[[(k,d,s,t)] for k,d,s,t in pending] if split else [pending] if pending else []
                for bundle in bundles:
                    if any(any(l.stage==x[0] for l in book.lots) for x in bundle):continue
                    count=len(bundle)
                    assert count==(1 if split else case.entry_bundle)
                    if not split:assert not book.lots
                    reason=book.reason(p,count) if case.limits.enabled else 'ACCEPT'
                    order_serial+=1
                    orders.append(dict(order_id=order_serial,row=i,signal_row=bundle[0][2],direction=bundle[0][1],
                        requested_contracts=count,requested_usdt=count*Q,filled_contracts=count if reason=='ACCEPT' else 0,
                        reason=reason,**{k:value for k,value in book.mark(p,False).items() if k not in ('row','phase')}))
                    if reason!='ACCEPT':continue
                    if not book.lots:cycle+=1
                    for k,d,signal,target in bundle:
                        serial+=1
                        lot=Lot(serial,cycle,k,d,i,signal,p.spot,p.future,p.future,target,order_id=order_serial)
                        book.enter(lot,p)
            pending=[]
        below=False
        for phase in ('OPEN','CLOSE','SETTLEMENT'):
            if phase=='SETTLEMENT' and not v[13][i]:continue
            pm=price(i,phase)
            if phase=='SETTLEMENT':book.settle(pm)
            m=book.mark(pm);marks.append(m)
            below=below or m['maintenance_headroom'] < -1e-7
            if m['maintenance_headroom'] < -1e-7 and case.limits.enabled:
                deficits.append(dict(row=i,phase=phase,kind='MAINTENANCE',deficit=-m['maintenance_headroom'],contracts=len(book.lots)))
        next_ok=i+1<len(v[0]) and bool(v[12][i+1])
        if book.lots and next_ok and not v[9][i]:
            d=book.lots[0].direction
            if d*(v[4][i]-book.lots[0].target)>=-1e-12:close_pending=True
        if case.limits.enabled and below:continue
        if split:
            if next_ok and not v[9][i] and not close_pending and v[12][i] and i>0:
                start=max(0,math.floor(-(v[4][i-1]+.8)/.2+1e-10)+1)
                end=math.floor((-.8-v[4][i])/.2+1e-10)
                for k in range(start,end+1):
                    if all(l.stage!=k for l in book.lots):pending.append((k,1,i,-.5))
        elif not book.lots and next_ok and not v[9][i] and v[12][i] and i>0:
            sign=0
            if v[4][i]<=-1 and v[4][i-1]>-1:sign=1
            if v[4][i]>=1 and v[4][i-1]<1:sign=-1
            if sign:
                pending=[(k,sign,i,float(v[4][i]+sign*.5)) for k in range(case.entry_bundle)]
    return Outcome(book,marks,orders,deficits)
