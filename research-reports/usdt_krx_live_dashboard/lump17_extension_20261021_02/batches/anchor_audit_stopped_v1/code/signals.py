# /// script
# requires-python = "==3.12.0"
# dependencies = ["numpy==2.2.6"]
# ///
from __future__ import annotations
import importlib.util
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
PRIOR=ROOT.parents[1]/'studies/single_set_hypotheses_20261020_01/code/signals.py'

def statistics(v, window: int) -> np.ndarray:
    path=ROOT/'feature_cache'/f'lagged_{window}.npz'
    if path.exists():return np.load(path)['stats']
    spec=importlib.util.spec_from_file_location('prior_causal_trailing',PRIOR)
    module=importlib.util.module_from_spec(spec)
    import sys
    sys.modules[spec.name]=module;spec.loader.exec_module(module)
    out=module.trailing(v[4],v[9],window)
    path.parent.mkdir(exist_ok=True);np.savez_compressed(path,stats=out)
    return out

def prepare(rule: dict, v, context):
    g=v[4];n=len(g);direction=int(rule.get('allowed_direction',0));family=rule['family']
    long_threshold=np.full(n,float(rule['long_entry_gap_pct']))
    short_threshold=np.full(n,float(rule['short_entry_gap_pct']))
    score=g.copy();mode=1
    tl=g+float(rule.get('long_recovery_pp') or 0.);ts=g-float(rule.get('short_recovery_pp') or 0.)
    exl=np.zeros(n,dtype=np.bool_);exs=exl.copy()
    window=int(rule.get('window_observations') or 0)
    if family in ('mean','median','quantile','zscore'):
        stat=statistics(v,window)
        if family in ('mean','median'):
            center=stat[:,0 if family=='mean' else 1]
            score=g-center
            fraction=float(rule.get('return_fraction') or 1.)
            tl=g+fraction*(center-g);ts=tl.copy()
        elif family=='quantile':
            long_threshold=stat[:,3];short_threshold=stat[:,4]
            exl=g>=stat[:,1];exs=g<=stat[:,1];mode=4
        else:
            score=np.divide(g-stat[:,0],stat[:,2],out=np.full(n,np.nan),where=stat[:,2]>1e-8)
            z=float(rule['z_entry']);long_threshold[:]=-z;short_threshold[:]=z
            outz=float(rule.get('z_exit') or 0.)
            exl=score>=outz;exs=score<=-outz;mode=4
    if family=='absolute':
        tl=np.full(n,float(rule['long_absolute_exit_gap_pct']));ts=np.full(n,float(rule['short_absolute_exit_gap_pct']))
    long=np.zeros(n,dtype=np.bool_);short=long.copy()
    long[1:]=(score[1:]<=long_threshold[1:])&(score[:-1]>long_threshold[:-1])
    short[1:]=(score[1:]>=short_threshold[1:])&(score[:-1]<short_threshold[:-1])
    valid=v[12]&~v[9].astype(bool)
    if rule.get('entry_session')=='regular':valid=valid&~context['night']
    if rule.get('entry_session')=='night':valid=valid&context['night']
    if rule.get('minimum_minute_volume') is not None:valid=valid&(context['volume']>=float(rule['minimum_minute_volume']))
    sign=np.zeros(n,dtype=np.int64)
    if direction in (0,1):sign[long&valid]=1
    if direction in (0,-1):sign[short&valid&(sign==0)]=-1
    return (sign,exl,exs,tl,ts,mode,float(rule.get('confirmation_pp') or 0.),
            float(rule.get('max_hold_minutes') or 0.),float(rule.get('gap_stop_pp') or 0.),
            float(rule.get('pnl_profit_pct') or 0.),float(rule.get('pnl_stop_pct') or 0.),
            float(rule.get('stall_minutes') or 0.),float(rule.get('slippage_bp') or 2.))
