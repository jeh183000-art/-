import importlib.util
import json

import numpy as np

from engine import simulate
from runner import ROOT, write_json
from signals import prepare
from validation2 import verify_book


def main():
    path=ROOT.parent/'lump17_sweep_20261021_01/code/tests.py'
    spec=importlib.util.spec_from_file_location('prior_fixture_only',path)
    old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
    v=list(old.fixture([0.,-1.1,-1.2,-.5,-.4,0.,1.2,1.3,.6,.5,0.]))
    v[9]=v[9].copy();v[9][3]=True
    v[13]=v[13].copy();v[13][2]=True
    v=tuple(v)
    rule=dict(family='relative',long_entry_gap_pct=-1.,short_entry_gap_pct=1.,long_recovery_pp=.5,short_recovery_pp=.5)
    args=prepare(rule,v,dict(night=np.zeros(len(v[0]),dtype=bool),volume=np.ones(len(v[0]))))
    result=simulate(v,*args)
    check=verify_book(v,result[0],result[1],result[2],result[6],result[7])
    assert check['settlement_events']>0 and check['roll_pairs']>0
    bad=result[6].copy();bad[5,1,1]+=1
    failed=False
    try:verify_book(v,result[0],result[1],result[2],bad,result[7])
    except AssertionError:failed=True
    assert failed
    missing=False
    try:verify_book(v,result[0],result[1][result[1][:,0]!=5],result[2],result[6],result[7])
    except AssertionError:missing=True
    assert missing
    assert np.nanmax(result[6][:,:,8])>0 and result[6][-1,1,8]>0
    record=dict(status='PASS',checks=['independent_vector_cash','all_settlements_required','all_roll_pairs_required','bank_tamper_detected','drawdown_is_running_max','recovery_does_not_reset_mdd'])
    write_json(ROOT/'vector_unit_tests.json',record)
    print(json.dumps(record),flush=True)


if __name__=='__main__':main()
