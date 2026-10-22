# /// script
# requires-python = "==3.12.0"
# dependencies = ["numpy==2.2.6"]
# ///
# Run bootstrap.py ../operations/stress_costs.py register|run
from __future__ import annotations
import hashlib,json,sys
from pathlib import Path
import numpy as np
from runner import ROOT,load,write_json,table,canonical,TRADE_FIELDS,EVENT_FIELDS,ORDER_FIELDS
from signals import prepare
from engine_path import simulate
from structural_audit import verify_exit_first_hit
from audit import replay
from validation2 import verify_book
from path_gate_audit import verify_gates
from profit_metrics import profit_summary

def register() -> None:
    out=ROOT/"cost_stress";out.mkdir()
    rows=[json.loads(p.read_text()) for p in (ROOT/"batches").glob("batch_*/candidates/*/result.json")]
    assert len(rows)==500
    rows=sorted([r for r in rows if r["cycles"] and r["margin_shortage_free"]],key=lambda r:r["score_pct"],reverse=True)
    seen=set();selected=[]
    settings={c["candidate_id"]:c for p in (ROOT/"preregistration").glob("batch_*.json") for c in json.loads(p.read_text())["conditions"]}
    for r in rows:
        if r["execution_path_sha256"] in seen:continue
        seen.add(r["execution_path_sha256"]);selected.append(settings[r["candidate_id"]])
        if len(selected)==3:break
    assert selected
    write_json(out/"preregistration.json",dict(selected=selected,slippage_bp=4.,
        stress_script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),baseline_slippage_bp=2.,new_rule_conditions=0,reason="Same top unique rules, higher execution costs; recalculate full exit/admission/cash paths, not subtraction only.",
        frozen_code_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/"code").glob("*.py")},
        input_sha256="62becd7d50e05bdcf47010cdcdfdd8178bbe2ef1d8099a84ab18fae8fea19fbd"))
    print("REGISTERED_STRESS_TOP3_NOT_NEW_RULES")

def run() -> None:
    root=ROOT/"cost_stress"
    reg=json.loads((root/"preregistration.json").read_text())
    assert json.loads((ROOT/"publication/stress_prereg_verified.json").read_text())["status"]=="PUBLISHED_VERIFIED"
    assert hashlib.sha256(Path(__file__).read_bytes()).hexdigest()==reg["stress_script_sha256"]
    for name,expected in reg["frozen_code_sha256"].items():assert hashlib.sha256((ROOT/"code"/name).read_bytes()).hexdigest()==expected
    v,frame,codes=load();summary=[]
    for candidate in reg["selected"]:
        rule=dict(candidate["rule"],slippage_bp=4.)
        args=prepare(rule,v,{"night":frame["session"].astype(str).str.contains("night",case=False).to_numpy(),"volume":frame["future_volume"].to_numpy()})
        values=simulate(v,*args)
        t,e,r,risk,equity,extremes,book,orders=values
        audit=replay(v,t,e,book,orders,4.)
        vector=verify_book(v,t,e,r,book,orders,4.)
        exits=verify_exit_first_hit(v,args,values)
        gates=verify_gates(v,args[0],book,orders,e,args[6],args[-2])
        out=root/candidate["candidate_id"];out.mkdir()
        np.savez_compressed(out/"all_ledgers.npz",trades=t,events=e,residual=r,risk=risk,equity=equity,
            extremes=extremes,ledger=book,orders=orders)
        cycles=[]
        for a in t:
            i,j=int(a[1]),int(a[3])
            cycles.append(dict(zip(TRADE_FIELDS,map(float,a)),candidate_id=candidate["candidate_id"],
                entry_kst=str(frame.iloc[i]["timestamp_kst"]),exit_kst=str(frame.iloc[j]["timestamp_kst"]),
                entry_notional=float(a[5]*170000),return_pct=float(a[13]/(a[5]*170000)*100)))
        table(out/"cycles.csv",cycles)
        table(out/"fills.csv",[dict(zip(EVENT_FIELDS,map(float,a))) for a in e])
        table(out/"orders.csv",[dict(zip(ORDER_FIELDS,map(float,a))) for a in orders])
        score=sum(a["return_pct"] for a in cycles)
        row=dict(candidate_id=candidate["candidate_id"],slippage_bp=4.,cycles=len(t),score_pct=score,
            net_realized=float(np.sum(t[:,13])),mdd_krw=float(risk[0]),maximum_open_loss_krw=float(risk[1]),
            residual_contracts=17 if r[0] else 0,residual_liquidation_net=float(r[10]),
            forced_terminal_score=score+(float(r[10]/(r[3]*170000)*100) if r[0] else 0),
            maintenance_breach_marks=int(audit[3]),initial_breach_marks=int(np.sum((abs(book[:,:,7])>0)&(book[:,:,9]<-.01))),
            rejected=int(np.sum(orders[:,4]==0)),insufficient_rolls=int(risk[6]),
            minimum_initial_headroom=float(audit[1]),minimum_maintenance_headroom=float(audit[2]),
            exit_first_hit_checked=exits,orders_checked=int(gates),fees=float(np.sum(e[:,8:10])),slippage=float(np.sum(e[:,10:12])))
        row.update(profit_summary(t[:,13]))
        write_json(out/"audit.json",dict(status="PASS",independent_vector=vector,max_cash_error=float(audit[0]),slippage_bp=4.))
        write_json(out/"result.json",row);summary.append(row)
    table(root/"results_4bp.csv",summary)
    write_json(root/"validation.json",dict(status="PASS",same_rule_sensitivity_cases=len(summary),new_strategy_count=0,
        fully_recomputed_state_and_cash=True,mixed_into_primary_ranking=False))
    print(json.dumps(summary))

if __name__=="__main__":
    {"register":register,"run":run}[sys.argv[1]]()
