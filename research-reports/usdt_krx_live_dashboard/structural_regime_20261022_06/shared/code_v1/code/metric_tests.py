# /// script
# requires-python = "==3.12.0"
# dependencies = ["numpy==2.2.6"]
# ///
# Run: python -B code/bootstrap.py metric_tests.py
import numpy as np
from profit_metrics import profit_summary
from runner import ROOT,write_json

def test_pf_when_completed_cost_net_has_profit_and_loss() -> None:
    # Given: these are already cost-net completed cycles.
    values=np.array([100.,50.,-25.])
    # When: PF is measured.
    result=profit_summary(values)
    # Then: profits 150 / loss 25 = 6.
    assert result['profit_factor_krw']==6. and result['profit_factor_status']=='FINITE'

def test_pf_when_no_losing_completed_cycles() -> None:
    # Given: all completed cycles won.
    values=np.array([5.,10.,0.])
    # When: PF is measured.
    result=profit_summary(values)
    # Then: infinity must not be silently encoded as a finite number.
    assert result['profit_factor_krw'] is None and result['profit_factor_status']=='INFINITE_NO_LOSSES'

def test_pf_when_no_completed_cycles() -> None:
    # Given: no cycle completion.
    values=np.array([],dtype=np.float64)
    # When: PF is measured.
    result=profit_summary(values)
    # Then: no defined PF, distinct from all winners.
    assert result['profit_factor_status']=='UNDEFINED_NO_COMPLETED_PNL' and result['profit_factor_krw'] is None

def test_pf_when_only_losing_cycles() -> None:
    # Given: two cost-net losses.
    values=np.array([-7.,-3.])
    # When: PF is measured.
    result=profit_summary(values)
    # Then: PF is exactly zero.
    assert result['profit_factor_krw']==0. and result['profit_factor_status']=='FINITE'

def test_pf_when_completed_pnl_is_zero() -> None:
    # Given: completed zero-net cycles.
    values=np.array([0.,0.])
    # When: PF is measured.
    result=profit_summary(values)
    # Then: no gain or loss exists for a ratio.
    assert result['profit_factor_status']=='UNDEFINED_NO_COMPLETED_PNL'

if __name__=='__main__':
    tests=[test_pf_when_completed_cost_net_has_profit_and_loss,test_pf_when_no_losing_completed_cycles,test_pf_when_no_completed_cycles,test_pf_when_only_losing_cycles,test_pf_when_completed_pnl_is_zero]
    for test in tests:test()
    write_json(ROOT/'metric_tests.json',dict(status='PASS',tests=len(tests),pf_basis='completed cycle net KRW',zero_loss_pf='EXPLICIT_INFINITY_STATUS'))
    print('PASS_PF_TESTS_5',flush=True)
