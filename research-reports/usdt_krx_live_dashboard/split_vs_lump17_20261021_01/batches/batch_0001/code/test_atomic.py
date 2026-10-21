# /// script
# requires-python = "==3.12.0"
# dependencies = ["numpy==2.2.6"]
# ///
from accounts import Limits
from simulation import Experiment,simulate
import numpy as np

def fixture():
    n=5;a=[np.zeros(n) for _ in range(18)]
    a[0]=np.arange(n);a[3]=np.ones(n);a[4]=np.array([0.,-1.1,-1.1,-.4,-.4])
    a[5]=a[6]=np.full(n,1000.);a[7]=a[8]=np.full(n,1000.)
    a[12]=np.array([False,True,True,True,True]);a[16]=np.full(n,.05);a[17]=np.full(n,.03)
    return tuple(a)

def test_atomic_denial():
    r=simulate(fixture(),Experiment('B','S1-050',Limits(0.,1000000.,17,True,True),17))
    assert len(r.orders)==1 and r.orders[0]['reason']=='INITIAL_MARGIN'
    assert r.orders[0]['requested_contracts']==17 and r.orders[0]['filled_contracts']==0
    assert not r.account.events and r.account.future_cash==1000000.

def test_atomic_acceptance_cost_and_quantity():
    r=simulate(fixture(),Experiment('B','S1-050',Limits(0.,30000000.,17,True,True),17))
    e=[e for e in r.account.events if e['kind']=='ENTRY']
    assert len(e)==17 and len({x['order_id'] for x in e})==1
    assert sum(x['spot_quantity_change'] for x in e)==170000.
    assert sum(x['future_quantity_change'] for x in e)==-17
    assert all(x['row']==2 for x in e) and len(r.account.fills)==17
    assert abs(sum(x['future_fee'] for x in e)-17*(600+1000*10000*.000003157))<1e-7

def test_deficit_is_not_fake_liquidation():
    v=list(fixture());v[4]=np.array([0.,-1.1,-1.1,-1.1,-1.1])
    v[7]=v[8]=np.array([1000.,1000.,1000.,5000.,5000.])
    r=simulate(tuple(v),Experiment('B','S1-050',Limits(0.,30000000.,17,True,True),17))
    assert r.deficits and len(r.account.lots)==17
    assert not any(e['kind']=='EXIT' for e in r.account.events)

def test_roll_cost_is_seventeen_contracts():
    v=list(fixture());v[4]=np.array([0.,-1.1,-1.1,-1.1,-1.1])
    v[9]=np.array([False,False,False,True,False]);v[10]=np.array([0.,0.,0.,1050.,0.])
    r=simulate(tuple(v),Experiment('B','S1-050',Limits(0.,30000000.,17,True,True),17))
    closes=[e for e in r.account.events if e['kind']=='ROLL_CLOSE']
    opens=[e for e in r.account.events if e['kind']=='ROLL_OPEN']
    assert len(closes)==len(opens)==17
    assert abs(sum(e['future_fee'] for e in closes)-17*(600+1050*10000*.000003157))<1e-7
    assert abs(sum(e['future_fee'] for e in opens)-17*(600+1000*10000*.000003157))<1e-7

if __name__=='__main__':
    test_atomic_denial();test_atomic_acceptance_cost_and_quantity();test_deficit_is_not_fake_liquidation();test_roll_cost_is_seventeen_contracts()
    print('PASS 4 atomic bundle, quantity, costs, and deficit-policy tests')
