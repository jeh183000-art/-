# /// script
# requires-python = "==3.12.0"
# dependencies = ["numpy==2.2.6"]
# ///
# Run: python -B code/bootstrap.py drawdown_tests.py
import importlib.util
import json

import numpy as np

from engine import simulate
from runner import ROOT, write_json
from signals import prepare
from validation2 import drawdown_trace, verify_book


def main() -> None:
    # Given new highs, worsening losses, partial recovery, a new high, and a new loss.
    equity = np.array([100., 120., 110., 90., 105., 125., 115., 80., 130.])
    expected = np.array([[100,0,0],[120,0,0],[120,10,10],[120,30,30],
                         [120,15,30],[125,0,30],[125,10,30],[125,45,45],[130,0,45]])
    # When computing each observation's three distinct quantities.
    actual = drawdown_trace(equity,100.)
    # Then recovery resets current drawdown but never cumulative MDD.
    np.testing.assert_array_equal(actual,expected)
    np.testing.assert_array_equal(drawdown_trace(np.array([95.,90.,100.]),100.),
                                  [[100,5,5],[100,10,10],[100,0,10]])
    path=ROOT.parent/'lump17_sweep_20261021_01/code/tests.py'
    spec=importlib.util.spec_from_file_location('frozen_fixture',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    v=list(module.fixture([0.,-1.1,-1.2,-.5,-.4,0.,1.2,1.3,.6,.5,0.]))
    v[9]=v[9].copy();v[9][3]=True
    v[13]=v[13].copy();v[13][2]=True
    v=tuple(v)
    rule=dict(family='relative',long_entry_gap_pct=-1.,short_entry_gap_pct=1.,long_recovery_pp=.5,short_recovery_pp=.5)
    args=prepare(rule,v,dict(night=np.zeros(len(v[0]),dtype=bool),volume=np.ones(len(v[0]))))
    result=simulate(v,*args)
    proof=verify_book(v,result[0],result[1],result[2],result[6],result[7])
    assert proof['settlement_events'] and proof['roll_pairs']
    rejected=[]
    for name in ('cash','mdd','settlement','roll'):
        ledger=result[6].copy();events=result[1].copy()
        if name=='cash':ledger[5,1,1]+=1
        if name=='mdd':ledger[-1,1,8]=0
        if name=='settlement':events=events[events[:,0]!=5]
        if name=='roll':events=events[events[:,0]!=4]
        try:
            verify_book(v,result[0],events,result[2],ledger,result[7])
        except AssertionError:
            rejected.append(name)
    assert rejected==['cash','mdd','settlement','roll']
    record=dict(status='PASS',manual_equity=equity.tolist(),expected=expected.tolist(),
        actual=actual.tolist(),tamper_rejections=rejected,integration=proof,
        unchanged_engine=True)
    write_json(ROOT/'drawdown_tests_v2.json',record)
    print(json.dumps(record),flush=True)


if __name__=='__main__':main()
