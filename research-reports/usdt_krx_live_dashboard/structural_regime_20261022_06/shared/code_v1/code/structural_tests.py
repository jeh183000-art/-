# /// script
# requires-python = "==3.12.0"
# dependencies = ["numpy==2.2.6"]
# ///
# Run: bootstrap.py structural_tests.py; finite fixtures and prefix invariance.
from __future__ import annotations
import json,random
import numpy as np
from exit_policy import state_exit
from signals import prepare,crossing
from build_structural import proposal,MODES
from runner import ROOT,load,write_json

def main() -> None:
    # Given symmetric threshold observations; When crossing; Then hedge sides oppose.
    x=np.array([0.,-1.1,-.4,1.1,.3])
    out=crossing(x+1,x-1,False)
    np.testing.assert_array_equal(out,[0,1,0,-1,0])
    # Given rising then falling net profit; When trail; Then arm prevents loss-only trigger.
    options=np.array([-1,-1,0,240,0,0,1,.6,.2,0.])
    assert not state_exit(-.5,.1,0,options)
    assert not state_exit(.65,.7,0,options)
    assert state_exit(.45,.7,0,options)
    # Given stalled policy; When progress resumes; Then duration changes actual exit.
    options[6]=2;options[9]=120
    assert not state_exit(.45,.7,119,options)
    assert state_exit(.45,.7,120,options)
    v,frame,codes=load()
    checks=[]
    rng=random.Random(20261022)
    for mode in MODES:
        rule=proposal(mode,rng)
        args=prepare(rule,v,{"night":np.zeros(len(v[0]),dtype=bool),"volume":np.zeros(len(v[0]))})
        for end in (12501,24019):
            cut=tuple(a[:end] for a in v)
            short=prepare(rule,cut,{"night":np.zeros(end,dtype=bool),"volume":np.zeros(end)})
            for k in range(5):
                np.testing.assert_array_equal(args[k][:end],short[k])
            checks.append(dict(structure=mode,cut=end,arrays=5,status="PASS"))
    write_json(ROOT/"structural_tests.json",dict(status="PASS",side_sign_test=True,trailing_tests=5,
        prefix_checks=checks,prior_observations_only=True,source_scope="approved only"))
    print(json.dumps(dict(status="PASS",prefix_checks=len(checks))))

if __name__=="__main__":main()
