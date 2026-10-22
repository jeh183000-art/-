# /// script
# requires-python = "==3.12.0"
# dependencies = ["numpy==2.2.6"]
# ///
# Independent exit-first-hit audit of saved account marks.
from __future__ import annotations
import numpy as np

def verify_exit_first_hit(v: tuple[np.ndarray,...], args: tuple, values: tuple) -> int:
    """Reconstruct each exit trigger from saved prices/paid-cost account marks."""
    trades,events,residual,risk,equity,extremes,book,orders=values
    records=[(int(t[1]),int(t[2]),int(t[4]),float(t[5]),float(t[16]),int(t[18])) for t in trades]
    if residual[0]:
        records.append((int(residual[2]),-1,int(residual[1]),float(residual[3]),0.,0))
    checked=0
    for start,exit_row,sign,spot_entry,target,bits in records:
        if exit_row<0:
            entry_events=events[(events[:,0]==1)&(events[:,1]==start)]
            assert len(entry_events)==1
            signal=int(entry_events[0,13])
            target=float(args[3 if sign==1 else 4][signal])
        signal_gap=float(v[4][start-1])
        best_gap=sign*v[4][start]
        last_progress=float(v[0][start])
        best_ret=-1e100
        end=exit_row+1 if exit_row>=0 else len(v[0])
        first=-1
        for i in range(start,end):
            oriented=sign*v[4][i]
            if oriented>best_gap+.01:
                best_gap=oriented
                last_progress=v[0][i]
            close_cost=v[6][i]*170000*.0005+10200+v[8][i]*170000*.000003157+(v[6][i]+v[8][i])*170000*args[-1]/10000
            ret=float((book[i,1,6]-close_cost)/(spot_entry*170000)*100)
            best_ret=max(best_ret,ret)
            reached=bool(args[1 if sign==1 else 2][i]) if args[5]==4 else sign*(v[4][i]-target)>=-1e-12
            reached=reached and bool(args[-2][5])
            stop_gap=args[8]>0 and sign*(v[4][i]-signal_gap)<=-args[8]
            pl=args[-2][0 if sign==1 else 1]
            pl=args[9] if pl<0 else pl
            stop_pnl=(pl>0 and ret>=pl) or (args[10]>0 and ret<=-args[10])
            timed=args[7]>0 and v[0][i]-v[0][start]>=args[7]
            stalled=args[11]>0 and v[0][i]-last_progress>=args[11]
            custom=False
            if len(args[-2])>6:
                p=int(args[-2][6])
                armed=best_ret>=args[-2][7]
                fell=ret<=best_ret-args[-2][8]
                custom=armed and fell and (p==1 or (p==2 and v[0][i]-last_progress>=args[-2][9]))
            code=int(reached)+2*int(stop_gap)+4*int(stop_pnl)+8*int(timed)+16*int(stalled)+32*int(custom)
            eligible=i+1<len(v[0]) and bool(v[12][i+1]) and not bool(v[9][i])
            if eligible and code:
                first=i
                assert exit_row==i and code==bits
                break
        assert first==exit_row
        checked+=1
    return checked
