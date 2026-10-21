# /// script
# requires-python = "==3.12.0"
# dependencies = []
# ///
"""Separate simulated spot cash and daily-settled futures accounts."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Final

Q: Final = 10000.0

@dataclass(frozen=True, slots=True)
class ExecutionPrice:
    row: int
    phase: str
    spot: float
    future: float
    initial: float
    maintenance: float

@dataclass(frozen=True, slots=True)
class Limits:
    spot: float
    future: float
    cap: int
    enabled: bool = True

@dataclass(slots=True)
class Lot:
    """Mutable settlement basis and accumulated costs for one hedge set."""
    set_id: int
    cycle: int
    stage: int
    direction: int
    entry_i: int
    signal_i: int
    entry_s: float
    entry_f: float
    basis: float
    target: float
    future_gross: float = 0.0
    fees: float = 0.0
    slip: float = 0.0
    rolls: int = 0

@dataclass(slots=True)
class Accounts:
    """Mutable cash book; account transfers and external deposits never occur."""
    limits: Limits
    spot_cash: float = field(init=False)
    future_cash: float = field(init=False)
    lots: list[Lot] = field(default_factory=list)
    events: list[dict] = field(default_factory=list)
    fills: list[dict] = field(default_factory=list)
    peak: float = field(init=False)
    mdd: float = 0.0
    max_loss: float = 0.0
    max_sets: int = 0
    max_initial: float = 0.0
    minimum_headroom: float = float('inf')
    breach_marks: int = 0
    realized: float = 0.0
    sequence: int = 0

    def __post_init__(self) -> None:
        self.spot_cash=self.limits.spot
        self.future_cash=self.limits.future
        self.peak=self.limits.spot+self.limits.future

    def mark(self, p: ExecutionPrice, update: bool = True) -> dict:
        count=len(self.lots)
        fu=sum(l.direction*(l.basis-p.future)*Q for l in self.lots)
        market=sum(l.direction*p.spot*Q for l in self.lots)
        open_net=sum(l.direction*(p.spot-l.entry_s)*Q+l.future_gross+l.direction*(l.basis-p.future)*Q-l.fees-l.slip for l in self.lots)
        equity=self.spot_cash+market+self.future_cash+fu
        initial=count*p.future*Q*p.initial
        maintenance=count*p.future*Q*p.maintenance
        short_proceeds=sum(l.entry_s*Q for l in self.lots if l.direction<0)
        short_collateral=sum(p.spot*Q for l in self.lots if l.direction<0)
        free_spot=self.spot_cash-short_proceeds-short_collateral
        head=self.future_cash+fu-maintenance
        if update:
            self.peak=max(self.peak,equity)
            self.mdd=max(self.mdd,self.peak-equity)
            self.max_loss=max(self.max_loss,-open_net)
            self.max_sets=max(self.max_sets,count)
            self.max_initial=max(self.max_initial,initial)
            self.minimum_headroom=min(self.minimum_headroom,head)
            self.breach_marks+=int(head < -1e-7)
        return dict(row=p.row,phase=p.phase,spot_price=p.spot,future_price=p.future,sets=count,
                    spot_cash=self.spot_cash,future_cash=self.future_cash,future_unrealized=fu,
                    spot_market_value=market,short_proceeds_restricted=short_proceeds,
                    short_collateral=short_collateral,spot_available=free_spot,
                    future_equity=self.future_cash+fu,initial_required=initial,maintenance_required=maintenance,
                    maintenance_headroom=head,total_equity=equity,mdd=self.mdd,open_net=open_net)

    def reason(self, p: ExecutionPrice) -> str:
        sf,ff,ss,fs=costs(p)
        m=self.mark(p,False)
        if len(self.lots)>=self.limits.cap:
            return 'POSITION_CAP'
        if m['spot_available'] < p.spot*Q+sf+ss-1e-7:
            return 'SPOT_CASH'
        if self.future_cash-ff-fs < -1e-7:
            return 'FUTURE_OPERATING_CASH'
        if m['maintenance_headroom'] < -1e-7:
            return 'MAINTENANCE'
        if m['future_equity']-ff-fs < (len(self.lots)+1)*p.future*Q*p.initial-1e-7:
            return 'INITIAL_MARGIN'
        return 'ACCEPT'

    def record(self, kind: str, lot: Lot, p: ExecutionPrice, delta: tuple[float,...]) -> None:
        ds,df,sf,ff,ss,fs,sg,fg=delta
        self.spot_cash+=ds
        self.future_cash+=df
        self.sequence+=1
        self.events.append(dict(sequence=self.sequence,kind=kind,row=p.row,set_id=lot.set_id,cycle_id=lot.cycle,
            stage=lot.stage,direction=lot.direction,signal_row=lot.signal_i if kind=='ENTRY' else p.row-1 if kind=='EXIT' and p.phase!='ROLL' else -1,
            spot_price=p.spot,future_price=p.future,spot_delta=ds,future_delta=df,
            spot_fee=sf,future_fee=ff,spot_slippage=ss,future_slippage=fs,
            spot_gross=sg,future_segment=fg,spot_cash_after=self.spot_cash,future_cash_after=self.future_cash))

    def enter(self, lot: Lot, p: ExecutionPrice) -> None:
        sf,ff,ss,fs=costs(p)
        lot.fees=sf+ff
        lot.slip=ss+fs
        self.lots.append(lot)
        self.record('ENTRY',lot,p,(-lot.direction*p.spot*Q-sf-ss,-ff-fs,sf,ff,ss,fs,0.,0.))

    def exit_all(self, p: ExecutionPrice, reason: str) -> None:
        while self.lots:
            lot=self.lots.pop()
            sf,ff,ss,fs=costs(p)
            sg=lot.direction*(p.spot-lot.entry_s)*Q
            fg=lot.direction*(lot.basis-p.future)*Q
            net=sg+lot.future_gross+fg-lot.fees-lot.slip-sf-ff-ss-fs
            self.record('EXIT',lot,p,(lot.direction*p.spot*Q-sf-ss,fg-ff-fs,sf,ff,ss,fs,sg,fg))
            self.events[-1]['exit_reason']=reason
            self.fills.append(dict(set_id=lot.set_id,cycle_id=lot.cycle,stage=lot.stage,direction=lot.direction,
                entry_signal_row=lot.signal_i,entry_row=lot.entry_i,exit_row=p.row,
                entry_spot=lot.entry_s,entry_future=lot.entry_f,exit_spot=p.spot,exit_future=p.future,
                spot_gross=sg,future_gross=lot.future_gross+fg,fees=lot.fees+sf+ff,
                slippage=lot.slip+ss+fs,net=net,rolls=lot.rolls,reason=reason))
            self.realized+=net

    def settle(self, p: ExecutionPrice) -> None:
        for lot in self.lots:
            gain=lot.direction*(lot.basis-p.future)*Q
            lot.future_gross+=gain
            lot.basis=p.future
            self.record('SETTLE',lot,p,(0.,gain,0.,0.,0.,0.,0.,gain))

    def roll(self, old: ExecutionPrice, new: ExecutionPrice) -> None:
        for lot in self.lots:
            gain=lot.direction*(lot.basis-old.future)*Q
            _,cf,_,cs=costs(old)
            _,of,_,os=costs(new)
            lot.future_gross+=gain
            lot.fees+=cf+of
            lot.slip+=cs+os
            lot.basis=new.future
            lot.rolls+=1
            self.record('ROLL_CLOSE',lot,old,(0.,gain-cf-cs,0.,cf,0.,cs,0.,gain))
            self.record('ROLL_OPEN',lot,new,(0.,-of-os,0.,of,0.,os,0.,0.))

def costs(p: ExecutionPrice) -> tuple[float,float,float,float]:
    return p.spot*Q*.0005,600.+p.future*Q*.000003157,p.spot*Q*.0002,p.future*Q*.0002
