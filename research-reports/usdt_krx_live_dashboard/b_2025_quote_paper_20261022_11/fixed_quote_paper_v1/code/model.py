# /// script
# requires-python = ">=3.12"
# dependencies = ["numpy==2.2.6"]
# ///
# How to run: imported by fixed-rule quote PAPER modules.
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from typing import Mapping
import importlib.util
import numpy as np
from common import OLD
Q=170000.0
INITIAL_F=30000000.0

@dataclass(frozen=True,slots=True)
class Quote:
    t:datetime
    sa:float
    sb:float
    fa:float
    fb:float
    gap:float
    source:str
    line:int
    reference_contract:str
    segment:int

    @classmethod
    def parse(cls,r:Mapping)->Quote:
        q=cls(datetime.fromisoformat(r['t']),float(r['sa']),float(r['sb']),float(r['fa']),float(r['fb']),float(r['gap']),str(r['source']),int(r['line']),str(r['reference_contract']),int(r['segment']))
        assert min(q.sa,q.sb,q.fa,q.fb)>0 and q.sa>=q.sb and q.fa>=q.fb
        return q

@dataclass(frozen=True,slots=True)
class Variant:
    id:str
    pnl_target:float|None

@dataclass(frozen=True,slots=True)
class Costs:
    sf:float
    ff:float
    ss:float
    fs:float
    @property
    def total(self)->float:return self.sf+self.ff+self.ss+self.fs

@dataclass(frozen=True,slots=True)
class Position:
    cycle:int
    direction:int
    signal:Quote
    entry:Quote
    sp:float
    fp:float
    costs:Costs

@dataclass(frozen=True,slots=True)
class Book:
    spot_cash:float=0.0
    future_cash:float=INITIAL_F
    realized:float=0.0
    cycle_counter:int=0


def costs(sp:float,fp:float)->Costs:
    """Same frozen four cost terms as the approved B engine; spread is already in prices."""
    return Costs(sp*Q*.0005,17*600+fp*Q*.000003157,sp*Q*.0002,fp*Q*.0002)

def execution(q:Quote,direction:int,entry:bool)->tuple[float,float]:
    buy_spot=(direction==1)==entry
    return (q.sa,q.fb) if buy_spot else (q.sb,q.fa)

def valuation(pos:Position,q:Quote)->tuple[float,float,Costs]:
    sp,fp=execution(q,pos.direction,False)
    sg=pos.direction*(sp-pos.sp)*Q;fg=pos.direction*(pos.fp-fp)*Q
    closing=costs(sp,fp)
    return sg+fg-pos.costs.total-closing.total,fg,closing

def crossing(previous:Quote,current:Quote)->int:
    if previous.gap>-.97 and current.gap<=-.97:return 1
    if previous.gap<.85 and current.gap>=.85:return -1
    return 0


def frozen_drawdowns(equity:list[float])->np.ndarray:
    """Reuse the already regression-tested running-peak/current-DD/cumulative-MDD implementation."""
    spec=importlib.util.spec_from_file_location('verified_drawdown_module',OLD/'validation2.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module.drawdown_trace(np.asarray(equity),INITIAL_F)
