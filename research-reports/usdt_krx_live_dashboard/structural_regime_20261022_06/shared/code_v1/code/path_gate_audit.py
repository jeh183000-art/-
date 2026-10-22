# /// script
# requires-python = "==3.12.0"
# dependencies = ["numpy==2.2.6", "numba==0.61.2"]
# ///
# Independent admission-signal audit; existing financial auditors remain unchanged.
from __future__ import annotations
import numpy as np
from numba import njit

@njit(cache=True)
def verify_gates(v, signs, ledger, orders, events, confirm, options):
    """Replay only flat-state admission gates; compare every order, including rejects."""
    n=len(v[0])
    exits=np.full(n,-1e100)
    for event in events:
        if int(event[0])==2:exits[int(event[1])]=v[0][int(event[1])]
    last_exit=-1e100
    armed=0
    armed_at=trough=0.
    armed_row=0
    cursor=0
    for i in range(n):
        last_exit=max(last_exit,exits[i])
        can=i+1<n and bool(v[12][i+1]) and not bool(v[9][i])
        held=int(ledger[i,1,7])!=0
        if held or not can or v[0][i]-last_exit<options[2]:
            armed=0
            continue
        sign=int(signs[i])
        if confirm>0 or options[4]>0:
            if not v[12][i] or v[9][i] or (armed!=0 and v[0][i]-armed_at>options[3]):
                armed=0
            if sign:
                armed=sign
                trough=sign*v[4][i]
                armed_at=v[0][i]
                armed_row=i
            sign=0
            if armed:
                oriented=armed*v[4][i]
                trough=min(trough,oriented)
                if oriented>=0:
                    armed=0
                elif oriented>=trough+confirm and i-armed_row>=options[4]:
                    sign=armed
                    armed=0
        if sign:
            assert cursor<len(orders)
            order=orders[cursor]
            assert int(order[0])==i+1 and int(order[1])==i and int(order[2])==sign
            assert order[3]==17 and (order[4]==0 or order[4]==17)
            cursor+=1
    assert cursor==len(orders)
    return cursor
