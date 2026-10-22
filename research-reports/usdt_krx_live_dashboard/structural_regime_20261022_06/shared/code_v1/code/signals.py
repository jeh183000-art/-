# /// script
# requires-python = "==3.12.0"
# dependencies = ["numpy==2.2.6"]
# ///
# Every signal uses completed observed bars; all fills occur later.
from __future__ import annotations
from typing import assert_never
import numpy as np
from legacy_signals import prepare as legacy_prepare, statistics
from structural_features import features, select_past
from structural_schema import StructuralRule
from path_schema import Context

def crossing(low: np.ndarray, high: np.ndarray, reverse: bool) -> np.ndarray:
    """Emit fresh band passes; reverse=True means inside-band reversal entry."""
    result=np.zeros(len(low),dtype=np.int64)
    if reverse:
        result[1:][(low[1:]>0)&(low[:-1]<=0)]=1
        result[1:][(high[1:]<0)&(high[:-1]>=0)]=-1
    else:
        result[1:][(low[1:]<=0)&(low[:-1]>0)]=1
        result[1:][(high[1:]>=0)&(high[:-1]<0)]=-1
    return result

def prepare(rule: StructuralRule, v: tuple[np.ndarray, ...], context: Context) -> tuple:
    """One account receives only the selected structural entry and exit series."""
    args=list(legacy_prepare(rule,v,context))
    if not rule.get("structure"):
        return tuple(args)
    gap=v[4]
    center,sigma,z,ds,df=features(v,int(rule["lookback"]))
    width=float(rule["entry_width"])
    inner=float(rule["inner_width"])
    valid=np.isfinite(z)&np.isfinite(ds)&v[12]&~v[9].astype(bool)
    exit_valid=valid.copy()
    sign=crossing(z+width,z-width,bool(rule.get("reversal_entry",False)))
    exlong=z>=-inner
    exshort=z<=inner
    external_exit=True
    structure=rule["structure"]
    match structure:
        case "driver":
            sign=crossing(gap+width,gap-width,False)
            share=abs(ds)/(abs(ds)+abs(df)+1e-12)
            driver=rule["driver"]
            match driver:
                case "spot": valid &= share>=rule["driver_share"]
                case "future": valid &= (1-share)>=rule["driver_share"]
                case "balanced": valid &= abs(share-.5)<=rule["driver_share"]
                case unknown: assert_never(unknown)
            valid &= abs(ds-df)>=rule["impulse_pp"]
            external_exit=False
        case "residual":
            drift=np.full(len(z),np.nan)
            drift[1:]=abs(np.diff(center))
            valid &= drift<=rule["center_drift_limit"]
        case "momentum":
            sign=-sign
            exlong=z<=inner
            exshort=z>=-inner
            valid &= abs(ds-df)>=rule["impulse_pp"]
        case "trail":
            if rule.get("entry_model","residual")=="fixed":
                sign=crossing(gap+width,gap-width,False)
            external_exit=False
        case "opportunity":
            sign=crossing(z+width,z-width,True)
            exlong=(z>inner)|((ds-df)<-rule["impulse_pp"])
            exshort=(z<-inner)|((ds-df)>rule["impulse_pp"])
        case "selector":
            choice=select_past(v,z,int(rule["selector_horizon"]),int(rule["selector_memory"]),
                               int(rule["selector_update_observations"]),float(rule["selector_min_edge_pp"]))
            sign=sign*choice
            exlong=np.where(choice==-1,z<=inner,z>=-inner)
            exshort=np.where(choice==-1,z>=-inner,z<=inner)
            valid &= choice!=0
        case unknown:
            assert_never(unknown)
    sign[~valid]=0
    args[0]=sign
    args[1]=np.asarray(exlong&exit_valid,dtype=np.bool_)
    args[2]=np.asarray(exshort&exit_valid,dtype=np.bool_)
    if external_exit: args[5]=4
    else: args[5]=1
    arm=float(rule.get("trailing_arm_pct") or 0)
    giveback=float(rule.get("trailing_giveback_pct") or 0)
    stalled=float(rule.get("stalled_trail_minutes") or 0)
    policy=2 if stalled>0 else 1 if arm>0 else 0
    args[-2]=np.r_[args[-2],policy,arm,giveback,stalled]
    if structure=="trail": args[-2][5]=0
    return tuple(args)
