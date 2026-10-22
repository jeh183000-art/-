# /// script
# requires-python = "==3.12.0"
# dependencies = ["numpy==2.2.6"]
# ///
# Synthetic prices only; test financial and exit audits on new state.
from __future__ import annotations
import numpy as np
from path_tests import synthetic
from registry import BASE
from legacy_signals import prepare
from engine_path import simulate
from structural_audit import verify_exit_first_hit
from audit import replay
from validation2 import verify_book
from runner import ROOT,write_json

def main() -> None:
    checks=[]
    for sign in (1,-1):
        # Given a hedge crosses entry, profits, retraces, then recovers.
        v=synthetic((np.array([-.4,-1.1,-1.1,-.7,-.2,-.1,-.5,-.5,-.2])*sign).tolist())
        rule=dict(BASE,long_entry_gap_pct=-1.,short_entry_gap_pct=1.,pnl_profit_pct=0.,gap_exit_enabled=False)
        args=list(prepare(rule,v,{"night":np.zeros(len(v[0]),dtype=bool),"volume":np.ones(len(v[0]))}))
        args[-2]=np.r_[args[-2],1,.3,.2,0.]
        # When net-return retracement triggers a full exit.
        values=simulate(v,*args)
        # Then one correct-sign atomic bundle closes, next OPEN, with independently verified cost.
        assert len(values[0])==1 and int(values[0][0,4])==sign and int(values[0][0,18])==32
        assert values[0][0,3]==values[0][0,2]+1
        assert verify_exit_first_hit(v,tuple(args),values)==1
        replay(v,values[0],values[1],values[6],values[7],2.)
        verify_book(v,values[0],values[1],values[2],values[6],values[7],2.)
        checks.append(dict(direction=sign,status="PASS",cycles=1))
        # Given the valid saved exit; When it is backdated; Then audit rejects.
        tampered=list(values);tampered[0]=values[0].copy();tampered[0][0,2]-=1
        with np.testing.assert_raises(AssertionError):verify_exit_first_hit(v,tuple(args),tuple(tampered))
    write_json(ROOT/"trail_integration_tests.json",dict(status="PASS",checks=checks,tamper_rejected=True))
    print("PASS_TRAILING_ACCOUNT_AND_FIRST_EXIT")

if __name__=="__main__":main()
