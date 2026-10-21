# /// script
# requires-python = "==3.12.0"
# dependencies = ["numpy==2.2.6"]
# ///
from accounts import Accounts, ExecutionPrice, Limits, Lot, Q
from simulation import Experiment, simulate
import numpy as np

def fixture(gaps):
    n=len(gaps)
    a=[np.zeros(n) for _ in range(18)]
    a[0]=np.arange(n);a[3]=np.ones(n);a[4]=np.array(gaps)
    a[5]=a[6]=np.full(n,1000.);a[7]=a[8]=np.full(n,1000.)
    a[12]=np.array([False]+[True]*(n-1));a[16]=np.full(n,.05);a[17]=np.full(n,.03)
    return tuple(a)

def test_cash_includes_costs():
    p=ExecutionPrice(1,'OPEN',1000.,1000.,.05,.03)
    a=Accounts(Limits(10000000.,30000000.,17))
    assert a.reason(p)=='SPOT_CASH'
    assert a.lots==[] and a.spot_cash==10000000.

def test_margin_and_operating_cash():
    p=ExecutionPrice(1,'OPEN',1000.,1000.,.05,.03)
    assert Accounts(Limits(30000000.,499999.,17)).reason(p)=='INITIAL_MARGIN'
    assert Accounts(Limits(30000000.,1.,17)).reason(p)=='FUTURE_OPERATING_CASH'

def test_settlement_does_not_transfer_spot():
    p=ExecutionPrice(1,'OPEN',1000.,1000.,.05,.03)
    a=Accounts(Limits(30000000.,30000000.,1))
    a.enter(Lot(1,1,0,1,1,0,1000.,1000.,1000.,0.),p)
    old_spot=a.spot_cash;old_future=a.future_cash
    a.settle(ExecutionPrice(2,'SETTLEMENT',1050.,1100.,.05,.03))
    assert a.spot_cash==old_spot and abs(a.future_cash-old_future+1000000.)<1e-7
    assert a.reason(p)=='POSITION_CAP'

def test_reverse_proceeds_restricted():
    p=ExecutionPrice(1,'OPEN',1000.,1000.,.05,.03)
    a=Accounts(Limits(15000000.,30000000.,1))
    a.enter(Lot(1,1,0,-1,1,0,1000.,1000.,1000.,0.),p)
    m=a.mark(p)
    assert m['spot_cash']>24000000. and m['spot_available']<5000000.

def test_rejected_order_has_no_cash_flow():
    v=fixture([0.,-.9,-1.1,-.4,-.4])
    r=simulate(v,Experiment('B','U-007206',Limits(1000.,30000000.,17)))
    assert len(r.rejections)==2 and not r.account.events
    assert r.account.spot_cash==1000. and r.account.future_cash==30000000.

def test_cap_blocks_actual_add_and_next_bar():
    v=fixture([0.,-.9,-1.1,-1.3,-.4,-.4])
    r=simulate(v,Experiment('B','U-007206',Limits(30000000.,30000000.,1)))
    assert sum(e['kind']=='ENTRY' for e in r.account.events)==1
    assert r.account.events[0]['row']==2 and r.account.events[0]['signal_row']==1
    assert len(r.rejections)==2 and r.account.max_sets==1

if __name__=='__main__':
    tests=[v for k,v in list(globals().items()) if k.startswith('test_')]
    for test in tests:test()
    print('PASS',len(tests),'admission/settlement/quantity tests')
