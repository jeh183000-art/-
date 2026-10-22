# /// script
# requires-python = "==3.12.0"
# dependencies = ["numpy==2.2.6"]
# ///
# Read only numeric outputs; no simulation or strategy changes.
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
from runner import ROOT,table,write_json

def folder(cid: str) -> Path:
    return ROOT/"batches"/f"batch_{int(cid.split('-')[1]):04d}"/"candidates"/cid

def main() -> None:
    out=ROOT/"final_audit"
    a,b=folder("SR-09-001"),folder("SR-09-005")
    arrays=[]
    with np.load(a/"numeric_result.npz") as x,np.load(b/"numeric_result.npz") as y:
        for key in x.files:
            np.testing.assert_array_equal(x[key],y[key]);arrays.append(key)
    with np.load(a/"full_account_ledger.npz") as x,np.load(b/"full_account_ledger.npz") as y:
        np.testing.assert_array_equal(x["ledger"],y["ledger"]);arrays.append("ledger")
    shares=np.linspace(0,1,10001)
    assert np.all(abs(shares-.5)<=.6) and np.all(abs(shares-.5)<=.8)
    write_json(out/"duplicate_ledger_proof.json",dict(status="CONFIRMED_DUPLICATE",original="SR-09-001",duplicate="SR-09-005",
        exact_arrays=arrays,synthetic_share_points=10001,all_balanced_filters_true=True,
        root_cause="Adaptive crossover retained dominance cutoff .6/.8 after switching driver to balanced; semantic hash did not canonicalize saturated balance cutoff.",
        original_failed_auditor_preserved=True,no_frozen_builder_change=True,no_resimulation=True))
    comparisons=[]
    selected=json.loads((ROOT/"cost_stress/preregistration.json").read_text())["selected"]
    for c in selected:
        cid=c["candidate_id"]
        with np.load(folder(cid)/"numeric_result.npz") as r:t2=r["trades"].copy()
        with np.load(ROOT/"cost_stress"/cid/"all_ledgers.npz") as r:t4=r["trades"].copy()
        keys=lambda t:{(int(x[1]),int(x[3]),int(x[4])):x for x in t}
        x,y=keys(t2),keys(t4)
        common=set(x)&set(y)
        for key in common:
            assert y[key][13]<=x[key][13]+.01
        comparisons.append(dict(candidate_id=cid,cycles_2bp=len(t2),cycles_4bp=len(t4),
            same_complete_intervals=len(common),different_2bp_intervals=len(set(x)-set(y)),
            different_4bp_intervals=len(set(y)-set(x)),
            net_2bp=float(np.sum(t2[:,13])),net_4bp=float(np.sum(t4[:,13])),
            score_2bp=float(sum(t[13]/(t[5]*170000)*100 for t in t2)),
            score_4bp=float(sum(t[13]/(t[5]*170000)*100 for t in t4)),
            matched_intervals_higher_cost_never_improves_net=True,
            note="Full cost-adjusted arm/exit/cash path re-evaluated; differing paths can produce non-monotonic aggregate profit. Not repricing identical fills."))
    table(out/"cost_stress_path_comparison.csv",comparisons)
    decomposition=[]
    for cid,path in [("BF-09-027",ROOT/"baseline/B_original/numeric_result.npz"),
                     ("SR-10-034",folder("SR-10-034")/"numeric_result.npz"),
                     ("SR-07-028",folder("SR-07-028")/"numeric_result.npz")]:
        with np.load(path) as source:t=source["trades"]
        gross=float(np.sum(t[:,9]+t[:,10]));cost=float(np.sum(t[:,11]+t[:,12]));net=float(np.sum(t[:,13]))
        assert abs(gross-cost-net)<.01
        decomposition.append(dict(candidate_id=cid,completed_cycles=len(t),completed_spot_gross=float(np.sum(t[:,9])),
            completed_future_gross=float(np.sum(t[:,10])),completed_gross=gross,completed_fees=float(np.sum(t[:,11])),
            completed_slippage=float(np.sum(t[:,12])),completed_cost=cost,net=net,cost_to_gross_pct=100*cost/gross,
            gross_per_cycle=gross/len(t),net_per_cycle=net/len(t),cost_per_cycle=cost/len(t)))
    table(out/"closed_cycle_cost_decomposition.csv",decomposition)
    write_json(out/"forensic_validation.json",dict(status="PASS_READONLY_FORENSIC",duplicate_financial_arrays_identical=True,
        matched_stress_intervals_cost_monotonic=True,stress_cases=3,simulation_repeated=False))
    print(json.dumps(dict(cost_comparison=comparisons,decomposition=decomposition)))

if __name__=="__main__":main()
