# /// script
# requires-python = "==3.12.0"
# dependencies = ["numpy==2.2.6"]
# ///
# Rule helpers for build_B.py; run through code/bootstrap.py.
from __future__ import annotations
import copy,hashlib,json
from itertools import zip_longest
from typing import Final,TypedDict,Unpack
from runner import ROOT,canonical

class Rule(TypedDict,total=False):
    family: str
    long_entry_gap_pct: float
    short_entry_gap_pct: float
    long_recovery_pp: float
    short_recovery_pp: float
    long_absolute_exit_gap_pct: float | None
    short_absolute_exit_gap_pct: float | None
    confirmation_pp: float
    confirmation_expiry_calendar_minutes: int | None
    max_hold_minutes: int | None
    gap_stop_pp: float | None
    pnl_stop_pct: float | None
    pnl_profit_pct: float
    stall_minutes: int
    entry_session: str
    minimum_minute_volume: float
    allowed_direction: int
    slippage_bp: float

BASE: Final[Rule]=json.loads((ROOT/'baseline/registry.json').read_text())['B']['rule']

def rule(e: float | None=None,r: float | None=None,**extra: Unpack[Rule]) -> Rule:
    """Copy only BF-09-027; optional symmetric E/R and declared axes replace fields."""
    value=copy.deepcopy(BASE)
    if e is not None:value.update(long_entry_gap_pct=-float(e),short_entry_gap_pct=float(e))
    if r is not None:value.update(long_recovery_pp=float(r),short_recovery_pp=float(r))
    value.update(extra)
    if value.get('confirmation_pp',0)>0:value.update(family='reversal',confirmation_expiry_calendar_minutes=240)
    return value

def signature(value: Rule) -> str:
    out={k:v for k,v in value.items() if v is not None and v!=0}
    if value['family'] in ('relative','reversal'):
        out['family']='relative'
        if value.get('confirmation_pp',0)>0:out['confirmation_expiry_calendar_minutes']=240
    if value.get('slippage_bp')==2:out.pop('slippage_bp',None)
    if value['family'] in ('mean','median','absolute'):
        out.pop('long_recovery_pp',None);out.pop('short_recovery_pp',None)
    if value['family'] in ('zscore','quantile'):
        for k in ('long_entry_gap_pct','short_entry_gap_pct','long_recovery_pp','short_recovery_pp'):out.pop(k,None)
    if value.get('allowed_direction')==1:out={k:v for k,v in out.items() if not k.startswith('short_')}
    if value.get('allowed_direction')==-1:out={k:v for k,v in out.items() if not k.startswith('long_')}
    return hashlib.sha256(canonical(out)).hexdigest()



def interleave(*groups: list[tuple[str,Rule]]) -> list[tuple[str,Rule]]:
    """Round-robin the registered hypotheses, rather than exhaust one filter first."""
    return [item for chunk in zip_longest(*groups) for item in chunk if item]
