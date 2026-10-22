# /// script
# requires-python = "==3.12.0"
# dependencies = ["numpy==2.2.6"]
# ///
# Run: python -B code/bootstrap.py path_tests.py
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
from engine_path import simulate
from signals import prepare, statistics
from runner import ROOT,load,calculate,canonical,write_json
from registry import BASE
import hashlib

def synthetic(gap: list[float]) -> tuple[np.ndarray,...]:
    """Small observed continuous session, no roll or settlement."""
    n=len(gap)
    v=[np.zeros(n) for _ in range(18)]
    v[0]=np.arange(n,dtype=float);v[3]=np.ones(n,dtype=np.int64)
    v[4]=np.array(gap);v[5]=1400*(1+v[4]/100);v[6]=v[5].copy()
    v[7]=np.full(n,1400.);v[8]=v[7].copy()
    v[9]=np.zeros(n,dtype=np.bool_);v[12]=np.ones(n,dtype=np.bool_);v[12][0]=False
    v[13]=np.zeros(n,dtype=np.bool_);v[16]=np.full(n,.05);v[17]=np.full(n,.04)
    return tuple(v)

def execute(rule, v):
    context={'night':np.zeros(len(v[0]),dtype=np.bool_),'volume':np.ones(len(v[0]))}
    return simulate(v,*prepare(rule,v,context))

def test_cooldown_when_fresh_crossings_repeat() -> None:
    # Given: two separate discount/recovery paths.
    v=synthetic([-.4,-1.1,-1.1,-.4,-.4,-1.1,-1.1,-.4,-.4])
    rule=dict(BASE,long_entry_gap_pct=-1.,pnl_profit_pct=0.)
    # When: only the post-exit cooldown changes.
    normal=execute(rule,v);delayed=execute(dict(rule,cooldown_minutes=10),v)
    # Then: the second crossing is discarded, never deferred.
    assert len(normal[0])==2 and len(delayed[0])==1

def test_directional_profit_when_gap_target_unreached() -> None:
    # Given: reverse-only opportunities with no recovery-target hit.
    v=synthetic([.4,1.1,1.1,.6,.6,.6,.6])
    rule=dict(BASE,short_entry_gap_pct=1.,short_recovery_pp=2.,pnl_profit_long_pct=2.)
    # When: the reverse net-profit threshold changes independently.
    low=execute(dict(rule,pnl_profit_short_pct=.05),v)
    high=execute(dict(rule,pnl_profit_short_pct=2.),v)
    # Then: only the small reverse profit threshold closes the position.
    assert len(low[0])==1 and len(high[0])==0 and high[2][0]>0

def test_confirmation_when_minimum_observations_apply() -> None:
    # Given: a crossing, adverse trough and subsequent reversal.
    v=synthetic([-.4,-1.1,-1.2,-1.,-.9,-.3,-.2,-.1,-.1])
    rule=dict(BASE,long_entry_gap_pct=-1.,confirmation_pp=.05,pnl_profit_pct=0.)
    # When: four observed confirmation bars are required.
    normal=execute(rule,v);slow=execute(dict(rule,confirmation_min_observations=4),v)
    # Then: the actual entry signal and fill move forward, without backdating.
    assert int(normal[1][0,1])==4 and int(slow[1][0,1])==6

def test_expiry_when_confirmation_is_too_late() -> None:
    # Given: four-bar confirmation cannot fit in a one-minute expiry.
    v=synthetic([-.4,-1.1,-1.2,-1.,-.9,-.3,-.2,-.1,-.1])
    rule=dict(BASE,long_entry_gap_pct=-1.,confirmation_pp=.05,
              confirmation_min_observations=4,confirmation_expiry_calendar_minutes=1)
    # When: the confirmation expires.
    result=execute(rule,v)
    # Then: no order is created.
    assert len(result[-1])==0

def test_statistics_when_future_is_changed_and_history_breaks() -> None:
    # Given: an identical observed prefix and a changed future.
    v=list(synthetic(list(np.linspace(-1.,1.,50))));v[0][20:]+=120
    before=statistics(tuple(v),10)
    altered=[x.copy() for x in v];altered[4][35:]=500.
    # When: causal trailing features are recalculated for the distinct input.
    after=statistics(tuple(altered),10)
    # Then: the earlier prefix is unchanged; gap resets require a fresh full window.
    np.testing.assert_array_equal(before[:35],after[:35])
    assert np.isnan(before[20:30]).all() and np.isfinite(before[30]).all()
    assert abs(before[10,0]-np.mean(v[4][:10]))<1e-12

def test_gate_audit_when_order_is_tampered() -> None:
    # Given: known valid flat-state admissions.
    from path_gate_audit import verify_gates
    v=synthetic([-.4,-1.1,-1.1,-.4,-.4,-1.1,-1.1,-.4,-.4])
    r=dict(BASE,long_entry_gap_pct=-1.,pnl_profit_pct=0.)
    args=prepare(r,v,{'night':np.zeros(len(v[0]),dtype=np.bool_),'volume':np.ones(len(v[0]))})
    values=simulate(v,*args)
    assert verify_gates(v,args[0],values[6],values[7],values[1],args[6],args[-2])==2
    # When: an actual entry signal is backdated.
    bad=values[7].copy();bad[0,1]-=1
    # Then: the independent admission audit must reject it.
    with np.testing.assert_raises(AssertionError):
        verify_gates(v,args[0],values[6],bad,values[1],args[6],args[-2])

def test_gap_disabled_when_no_profit_target_reached() -> None:
    # Given: a path that reaches only the gap target.
    v=synthetic([-.4,-1.1,-1.1,-.4,-.4])
    rule=dict(BASE,long_entry_gap_pct=-1.,pnl_profit_pct=2.)
    # When: the gap exit is disabled explicitly.
    r=execute(dict(rule,gap_exit_enabled=False),v)
    # Then: no phantom gap exit is allowed.
    assert len(r[0])==0 and r[2][0]>0

def main() -> None:
    tests=[test_cooldown_when_fresh_crossings_repeat,test_directional_profit_when_gap_target_unreached,
        test_confirmation_when_minimum_observations_apply,test_expiry_when_confirmation_is_too_late,
        test_statistics_when_future_is_changed_and_history_breaks,test_gate_audit_when_order_is_tampered,test_gap_disabled_when_no_profit_target_reached]
    for test in tests:test()
    write_json(ROOT/'path_tests_v2.json',dict(status='PASS',tests=len(tests),causal_prefix_invariant=True,
        input_keyed_features=True,cooldown_not_queued=True,actual_confirmation_signal=True))
    print('PASS_PATH_TESTS_7',flush=True)

if __name__=='__main__':main()
