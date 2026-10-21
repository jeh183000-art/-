# /// script
# requires-python = "==3.12.0"
# dependencies = ["numpy==2.2.6"]
# ///
from accounts import Limits
from simulation import Experiment, simulate
from test_accounts import fixture
import numpy as np

def test_maintenance_exit_is_next_observed_open():
    v=list(fixture([0.,-.9,-.9,-.9,-.9,-.9]))
    v[7]=np.array([1000.,1000.,1000.,5000.,5000.,5000.])
    v[8]=v[7].copy()
    r=simulate(tuple(v),Experiment('B','U-007206',Limits(30000000.,30000000.,1)))
    exits=[e for e in r.account.events if e['kind']=='EXIT']
    assert len(exits)==1 and exits[0]['row']==4
    assert exits[0]['exit_reason']=='MAINTENANCE_OR_SPOT_COLLATERAL_FORCED'
    assert r.account.future_cash<0 and not r.account.lots

def test_roll_margin_refusal_unwinds_old_hedge():
    v=list(fixture([0.,-.9,-.9,-.9,-.9]))
    v[7]=np.array([1000.,1000.,1000.,5000.,5000.]);v[8]=v[7].copy()
    v[9]=np.array([False,False,False,True,False])
    v[10]=np.array([0.,0.,0.,5000.,0.])
    r=simulate(tuple(v),Experiment('B','U-007206',Limits(30000000.,30000000.,1)))
    exits=[e for e in r.account.events if e['kind']=='EXIT']
    assert len(exits)==1 and exits[0]['row']==3
    assert exits[0]['exit_reason']=='ROLL_MARGIN_FORCED'
    assert not any(e['kind']=='ROLL_OPEN' for e in r.account.events)

if __name__=='__main__':
    test_maintenance_exit_is_next_observed_open()
    test_roll_margin_refusal_unwinds_old_hedge()
    print('PASS 2 maintenance/roll forced-path tests')
