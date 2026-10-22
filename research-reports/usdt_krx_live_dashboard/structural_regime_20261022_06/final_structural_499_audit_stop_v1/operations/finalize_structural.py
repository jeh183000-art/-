# /// script
# requires-python = "==3.12.0"
# dependencies = ["numpy==2.2.6"]
# ///
# Saved-result publication only; no engine call.
from __future__ import annotations
import csv,gzip,hashlib,json,shutil,sys
from collections import defaultdict
from pathlib import Path
import numpy as np
from runner import ROOT,load,table,write_json,LEDGER_FIELDS

def main() -> None:
    out=ROOT/"publish_payloads/final_structural_499_audit_stop_v1";out.mkdir()
    validation=json.loads((ROOT/"final_audit/validation.json").read_text())
    assert validation["financial_metrics"]=="PASS" and validation["semantic_uniqueness"]=="FAIL"
    incident=json.loads((ROOT/"semantic_duplicate_incident.json").read_text())
    excluded={d["duplicate"] for d in incident["duplicates"]}
    attempts=[json.loads(p.read_text()) for p in sorted((ROOT/"batches").glob("batch_*/candidates/*/result.json"))]
    assert len(attempts)==500
    unique=[r for r in attempts if r["candidate_id"] not in excluded]
    assert len(unique)==499
    unique.sort(key=lambda r:r["score_pct"],reverse=True)
    completed=[r for r in unique if r["cycles"]]
    feasible=[r for r in completed if r["margin_shortage_free"]]
    nores=[r for r in feasible if not r["residual_contracts"]]
    rows=dict(raw_best=completed[0],margin_free_best=feasible[0],no_residual_best=nores[0],
              min42_best=next(r for r in feasible if r["cycles"]>=42))
    for name,records in [("results_all_500_attempts.csv",attempts),("ranking_unique_499.csv",unique),
        ("top20_score.csv",completed[:20]),("top20_margin_free.csv",feasible[:20]),
        ("top20_no_residual.csv",nores[:20]),("top20_min42.csv",[r for r in feasible if r["cycles"]>=42][:20]),
        ("target_pass.csv",[r for r in unique if r["goal_qualified"]]),
        ("zero_completed.csv",[r for r in unique if not r["cycles"]]),
        ("margin_problems.csv",[r for r in unique if not r["margin_shortage_free"]]),
        ("open_residuals.csv",[r for r in unique if r["residual_contracts"]]),
        ("semantic_duplicates.csv",[r for r in attempts if r["candidate_id"] in excluded])]:
        table(out/name,records)
    keys=("meets_25_pct","meets_60m_krw","meets_cycle_count","meets_mdd_limit","meets_residual_zero","margin_shortage_free")
    table(out/"target_shortfalls.csv",[dict(r,failed_targets=";".join(k for k in keys if not r[k])) for r in unique if not r["goal_qualified"]])
    registrations=[json.loads(p.read_text()) for p in sorted((ROOT/"preregistration").glob("batch_*.json"))]
    conditions=[c for p in registrations for c in p["conditions"]]
    rules={c["candidate_id"]:c["rule"] for c in conditions}
    write_json(out/"settings_all_500_attempts.json",dict(registrations=registrations,semantic_exclusion_ids=sorted(excluded)))
    paths=defaultdict(list)
    for r in unique:paths[r["execution_path_sha256"]].append(r["candidate_id"])
    table(out/"equivalent_execution_paths.csv",[dict(sha256=k,count=len(ids),candidate_ids=";".join(ids)) for k,ids in paths.items()])
    families=[]
    for mode in ("driver","residual","momentum","trail","opportunity","selector"):
        selected=[r for r in unique if r["structure"]==mode]
        valid=[r for r in selected if r["cycles"] and r["margin_shortage_free"]]
        winner=max(valid,key=lambda x:x["score_pct"]) if valid else None
        families.append(dict(structure=mode,unique_rules=len(selected),attempts=sum(r["structure"]==mode for r in attempts),
            zero_cycles=sum(not r["cycles"] for r in selected),margin_problems=sum(not r["margin_shortage_free"] for r in selected),
            residual_candidates=sum(bool(r["residual_contracts"]) for r in selected),
            best_id=winner["candidate_id"] if winner else None,best_score=winner["score_pct"] if winner else None,
            best_net=winner["net_realized"] if winner else None))
    table(out/"family_comparison.csv",families)
    shutil.copytree(ROOT/"final_audit",out/"validation")
    shutil.copytree(ROOT/"diagnosis",out/"diagnosis")
    shutil.copytree(ROOT/"cost_stress",out/"cost_stress")
    shutil.copytree(ROOT/"baseline_audit",out/"baseline_audit")
    shutil.copytree(ROOT/"operations",out/"operations")
    for name in ("semantic_duplicate_incident.json","halfway_250_diagnosis.json","registry_sources.csv","registry_summary.json","external_dependencies.json"):
        shutil.copy2(ROOT/name,out/name)
    shutil.copy2(ROOT/"publication/code_ref.json",out/"strategy_code_ref.json")
    index=[]
    for number in range(1,11):
        result=json.loads((ROOT/"publication"/f"batch_{number:04d}_results_verified.json").read_text())
        prereg=json.loads((ROOT/"publication"/f"batch_{number:04d}_prereg_verified.json").read_text())
        assert result["status"]==prereg["status"]=="PUBLISHED_VERIFIED"
        summary=json.loads((Path(result["local"])/"publication_summary.json").read_text())
        index.append(dict(batch=number,attempted_conditions=50,unique_conditions=49 if number==9 else 50,
            result_commit=result["commit"],result_path=result["remote"],prereg_commit=prereg["commit"],
            prereg_path=prereg["remote"],files=result["files"],status=result["status"],
            c_free_gib=summary["c_free_gib"],d_free_gib=summary["d_free_gib"]))
    table(out/"batch_publication_index.csv",index)
    v,frame,codes=load()
    for cid in dict.fromkeys(r["candidate_id"] for r in rows.values()):
        source=ROOT/"batches"/f"batch_{int(cid.split('-')[1]):04d}"/"candidates"/cid
        for kind in ("cycles","fills","orders"):
            with gzip.open(source/(kind+".csv.gz"),"rb") as inp,(out/(cid+"_"+kind+".csv")).open("xb") as dst:shutil.copyfileobj(inp,dst)
        for kind in ("exit_attribution.csv","residual.csv","period_contribution.csv"):
            shutil.copy2(source/kind,out/(cid+"_"+kind))
        with np.load(source/"full_account_ledger.npz") as z:book=z["ledger"]
        flat=book.reshape(-1,11)
        valid=np.flatnonzero(np.isfinite(flat[:,5]))
        values=flat[valid]
        selected=set(valid[np.r_[True,np.any(np.diff(values[:,:2],axis=0)!=0,axis=1)]].tolist())
        for column in (4,5,6,8,9):
            selected.add(int(valid[np.argmin(values[:,column])]))
            selected.add(int(valid[np.argmax(values[:,column])]))
        snapshots=[]
        for pos in sorted(selected):
            i,phase=divmod(pos,3)
            snapshots.append(dict(row=i,phase=("OPEN","CLOSE","SETTLEMENT")[phase],timestamp_kst=str(frame.iloc[i]["timestamp_kst"]),
                **dict(zip(LEDGER_FIELDS,map(float,flat[pos])))))
        table(out/(cid+"_cash_margin_snapshot.csv"),snapshots)
    write_json(out/"selected_rules_and_metrics.json",{k:dict(result=r,rule=rules[r["candidate_id"]]) for k,r in rows.items()})
    table(out/"costs.csv",[{k:r[k] for k in ("candidate_id","fees_krw","slippage_krw","borrow_unverified")} for r in unique])
    table(out/"risks.csv",[{k:r[k] for k in ("candidate_id","mdd_krw","maximum_open_loss_krw","minimum_initial_headroom_krw",
        "minimum_maintenance_headroom_krw","initial_margin_deficit_marks","maintenance_breach_marks","insufficient_rolls","admission_rejections",
        "residual_contracts","residual_net_after_exit_cost","forced_terminal_score_pct","average_spot_exposure_krw","spot_financing_proxy_krw")} for r in unique])
    summary=dict(status="STOPPED_RULE_DEDUP_AUDIT_FAILURE",attempts=500,unique_rules=499,duplicate_rules=1,
        unique_execution_paths=len(paths),goal_pass=sum(r["goal_qualified"] for r in unique),
        zero_cycles=sum(not r["cycles"] for r in unique),margin_problems=sum(not r["margin_shortage_free"] for r in unique),
        residual_candidates=sum(bool(r["residual_contracts"]) for r in unique),
        completed_cycles_attempt_sum=sum(r["cycles"] for r in attempts),completed_cycles_unique_rule_sum=sum(r["cycles"] for r in unique),
        best=rows["raw_best"],best_no_residual=rows["no_residual_best"],best_rule=rules[rows["raw_best"]["candidate_id"]],
        best_no_residual_rule=rules[rows["no_residual_best"]["candidate_id"]],families=families,
        fees="Primary2bp; stress4bp separate; fixed600KRW/contract+.0003157% clearing; spot.05% per side",
        source_status="INPUT_NOT_REMOTELY_REPRODUCIBLE",financial_validation="PASS",semantic_uniqueness="FAIL",
        additional_simulations_blocked=True,worker_running=False,final_oos_access=False,original_B_profit_target=.7,
        gateway_changed=False,scheduler_changed=False,collector_changed=False)
    write_json(out/"summary.json",summary)
    write_json(out/"environment.json",dict(python=sys.version,numpy=np.__version__,numba="0.61.2",pandas_loader="3.0.1",
        process_utf8=True,storage="D_ONLY",packages_changed=False))
    write_json(out/"provenance.json",dict(source_sha256="62becd7d50e05bdcf47010cdcdfdd8178bbe2ef1d8099a84ab18fae8fea19fbd",
        margin_sha256="910816bc61c9d9b7361bec370e225bfeae9cde0f11b889265cb4409ecb9344b8",
        baseline_commit="c63352755d43b067b2124e748297efe6cbf6ecbf",prior_final_commit="d3faabebf5828cc00db4979dc48b12af63f4a751",
        input_status="INPUT_NOT_REMOTELY_REPRODUCIBLE",scope="Same approved exploratory 2026 KRX business dates Jan1..Oct15",
        final_oos_access=False,cost_stress_prereg_commit=json.loads((ROOT/"publication/stress_prereg_verified.json").read_text())["commit"]))
    write_json(out/"checkpoint.json",summary)
    print(json.dumps(summary))

if __name__=="__main__":main()
