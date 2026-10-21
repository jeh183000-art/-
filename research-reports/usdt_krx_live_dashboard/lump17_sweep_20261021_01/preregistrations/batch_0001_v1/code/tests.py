from __future__ import annotations

import copy
import json
import numpy as np

from audit import replay
from engine import simulate
from runner import ROOT, write_json
from signals import prepare


def fixture(gaps, initial=.05):
    n=len(gaps); zero=np.zeros(n); one=np.ones(n)
    future=np.full(n,1400.); spot=future*(1+np.array(gaps)/100)
    contiguous=np.ones(n,dtype=np.bool_);contiguous[0]=False
    return (np.arange(n,dtype=np.int64),zero.astype(np.int64),zero.astype(bool),one.astype(np.int64),np.array(gaps),
            spot,spot,future,future,zero.astype(bool),future,one.astype(np.int64),contiguous,
            zero.astype(bool),future,spot,np.full(n,initial),np.full(n,initial*.7))


def run(v, **changes):
    rule=dict(family='relative',long_entry_gap_pct=-1.,short_entry_gap_pct=1.,long_recovery_pp=.5,short_recovery_pp=.5)
    rule.update(changes)
    args=prepare(rule,v,dict(night=np.zeros(len(v[0]),dtype=bool),volume=np.ones(len(v[0]))))
    out=simulate(v,*args)
    checked=replay(v,out[0],out[1],out[6],out[7],args[-1])
    assert checked[0]<.01
    return out


def main():
    v=fixture([0.,-1.1,-1.2,-.5,-.4,0.,1.2,1.3,.6,.5,0.])
    out=run(v)
    assert len(out[0])==2 and np.array_equal(out[0][:,1],[2,7]) and np.array_equal(out[0][:,3],[4,9])
    assert np.all(out[7][:,3:5]==17)
    assert np.sum(out[1][:,0]==1)==2 and np.all(np.abs(out[6][:,1,7])<=1)
    expensive=run(fixture([0.,-1.1,-1.2,-.5,-.4],initial=.2))
    assert len(expensive[0])==0 and len(expensive[7])==1 and expensive[7][0,4]==0
    assert not np.any(expensive[1]) and not np.any(np.nan_to_num(expensive[6][:,:,7]))
    first=run(fixture([-1.5,-1.7,-1.3,-.5,0.]))
    assert len(first[7])==0
    reversal=run(fixture([0.,-1.1,-1.4,-1.2,-1.1,-.6,-.5]),family='reversal',confirmation_pp=.15)
    assert len(reversal[0])==1 and reversal[0][0,1]==4
    absolute=run(v,family='absolute',long_absolute_exit_gap_pct=0.,short_absolute_exit_gap_pct=0.)
    assert len(absolute[0])==1 and absolute[0][0,3]==6
    asym=run(v,short_entry_gap_pct=2.)
    assert len(asym[0])==1
    gap=list(v);gap[12]=v[12].copy();gap[12][2]=False
    assert len(run(tuple(gap))[7])==1
    roll=list(v);roll[9]=v[9].copy();roll[9][3]=True;roll[13]=v[13].copy();roll[13][2]=True
    rolled=run(tuple(roll))
    assert np.any(rolled[1][:,0]==3) and np.any(rolled[1][:,0]==4) and np.any(rolled[1][:,0]==5)
    tampered=out[6].copy();tampered[3,1,1]+=1
    rejected=False
    try:replay(v,out[0],out[1],tampered,out[7],2.)
    except AssertionError:rejected=True
    assert rejected
    prefix=run(tuple(a[:6] for a in v))
    np.testing.assert_allclose(prefix[6],out[6][:6],equal_nan=True)
    record=dict(status='PASS',checks=['two_directions_one_slot','atomic_17','no_additions','insufficient_margin_all_rejected',
         'initial_extreme_no_retroactive_entry','reversal_confirmation','signed_absolute_exit','asymmetric_entry',
         'no_gap_fill','roll_both_sides','official_settlement','independent_audit_detects_cash_tamper','prefix_causality'])
    write_json(ROOT/'unit_tests.json',record)
    print(json.dumps(record),flush=True)


if __name__=='__main__':main()
