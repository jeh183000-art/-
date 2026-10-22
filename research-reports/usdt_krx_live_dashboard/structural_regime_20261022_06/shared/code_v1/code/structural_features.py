# /// script
# requires-python = "==3.12.0"
# dependencies = ["numpy==2.2.6", "numba==0.61.2"]
# ///
# Run using bootstrap.py, no interpolation and no future rows.
from __future__ import annotations
import numpy as np
from numba import njit
from legacy_signals import statistics

def features(v: tuple[np.ndarray, ...], window: int) -> tuple[np.ndarray, ...]:
    """Lagged center/std plus current completed-bar price-driver attribution."""
    stat = statistics(v, window)
    gap = v[4]
    n = len(gap)
    ds = np.full(n, np.nan)
    df = ds.copy()
    age = 0
    for i in range(n):
        if i == 0 or v[9][i] or v[0][i]-v[0][i-1]>30:
            age = 0
        if age >= window:
            ds[i] = 100*np.log(v[6][i]/v[6][i-window])
            df[i] = 100*np.log(v[8][i]/v[8][i-window])
        age += 1
    center = stat[:, 1]
    sigma = np.maximum(stat[:, 2], .05)
    z = (gap-center)/sigma
    return center, sigma, z, ds, df

@njit(cache=True)
def select_past(v, z, horizon, memory, update, min_edge):
    """Select from matured lagged hedge forecasts, never an end-of-period winner.
    
    Proxy probes overlap and are not investable shadow-account returns.
    All probes are dated before the present decision, use next OPEN and
    current CLOSE, include both-leg fees and 2bp execution charges.
    A selected rule alone emits signals to the single real PAPER account.
    """
    n=len(z)
    gains=np.zeros((n,2))
    valid=np.zeros(n)
    cumulative=np.zeros((n+1,2))
    counts=np.zeros(n+1)
    out=np.zeros(n,dtype=np.int64)
    last_choice=0
    for i in range(n):
        a=i-horizon
        if a>=1 and np.isfinite(z[a]) and abs(z[a])>=1 and v[12][a+1] and v[3][a]==v[3][i]:
            so,fo=v[5][a+1],v[7][a+1]
            sc,fc=v[6][i],v[8][i]
            cost=(so+sc)*.0005+(fo+fc)*.000003157+1200/10000+(so+sc+fo+fc)*.0002
            direction=1 if z[a]<0 else -1
            gross=direction*((sc-so)-(fc-fo))
            gains[i,0]=100*(gross-cost)/so
            gains[i,1]=100*(-gross-cost)/so
            valid[i]=1
        cumulative[i+1]=cumulative[i]+gains[i]
        counts[i+1]=counts[i]+valid[i]
        if i%update==0:
            left=max(0,i-memory)
            count=counts[i]-counts[left]
            last_choice=0
            if count>=20:
                mr=(cumulative[i,0]-cumulative[left,0])/count
                trend=(cumulative[i,1]-cumulative[left,1])/count
                if max(mr,trend)>min_edge:
                    last_choice=1 if mr>=trend else -1
        out[i]=last_choice
    return out
