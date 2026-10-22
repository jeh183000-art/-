# /// script
# requires-python = "==3.12.0"
# dependencies = ["numpy==2.2.6"]
# ///
# Independent sums/date parsing/peak-MDD on saved CSV and NPZ, no simulation.
from __future__ import annotations
import csv,gzip,hashlib,json,math
from collections import defaultdict
from datetime import datetime
import numpy as np
from runner import ROOT,table,write_json,canonical
from build_structural import normalized

def main() -> None:
    out=ROOT/"final_audit"
    registrations=[json.loads(p.read_text()) for p in sorted((ROOT/"preregistration").glob("batch_*.json"))]
    assert len(registrations)==10
    files={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/"code").glob("*.py")}
    conditions=[c for r in registrations for c in r["conditions"]]
    seen={};duplicates=[];semantic=[];metrics=[];months=[];quarters=[];concentration=[]
    for registration in registrations:
        assert files==registration["code_sha256"]
        assert hashlib.sha256(canonical(registration["conditions"])).hexdigest()==registration["grid_sha256"]
    for c in conditions:
        rule=normalized(c["rule"])
        if rule["structure"]=="driver" and rule["driver"]=="balanced" and rule["driver_share"]>=.5:rule["driver_share"]=.5
        fingerprint=hashlib.sha256(canonical(rule)).hexdigest()
        if fingerprint in seen:
            duplicates.append(dict(original=seen[fingerprint],duplicate=c["candidate_id"]))
        else:
            seen[fingerprint]=c["candidate_id"]
        semantic.append(dict(candidate_id=c["candidate_id"],normalized_sha256=fingerprint,
            balance_filter_inert=bool(rule["structure"]=="driver" and rule.get("driver")=="balanced" and rule["driver_share"]>=.5)))
        batch=c["candidate_id"].split("-")[1]
        folder=ROOT/"batches"/f"batch_{int(batch):04d}"/"candidates"/c["candidate_id"]
        result=json.loads((folder/"result.json").read_text())
        assert json.loads((folder/"audit.json").read_text())["status"]=="PASS"
        with gzip.open(folder/"cycles.csv.gz","rt",encoding="utf8",newline="") as stream:
            rows=list(csv.DictReader(stream))
        total_net=math.fsum(float(r["net"]) for r in rows)
        returns=[float(r["net"])/(abs(float(r["entry_spot"]))*170000)*100 for r in rows]
        score=math.fsum(returns)
        assert len(rows)==result["cycles"] and abs(score-result["score_pct"])<1e-8 and abs(total_net-result["net_realized"])<.01
        grouping=defaultdict(list)
        for r,ret in zip(rows,returns):
            raw=r["exit_business_date"]
            day=datetime.strptime(raw,"%Y-%m-%d" if "-" in raw else "%Y%m%d")
            assert "20260101"<=day.strftime("%Y%m%d")<="20261015"
            grouping[("month",day.strftime("%Y-%m"))].append((float(r["net"]),ret))
            grouping[("quarter",f"{day.year}-Q{(day.month-1)//3+1}")].append((float(r["net"]),ret))
        with (folder/"period_contribution.csv").open(encoding="utf8",newline="") as stream:
            stored={(r["period_type"],r["period"]):r for r in csv.DictReader(stream)}
        assert set(grouping)==set(stored)
        for key,values in grouping.items():
            ref=stored[key]
            assert int(ref["cycles"])==len(values)
            assert abs(float(ref["net"])-math.fsum(x[0] for x in values))<.01
            assert abs(float(ref["score_pct"])-math.fsum(x[1] for x in values))<1e-8
        for month in range(1,11):
            values=grouping[("month",f"2026-{month:02d}")]
            months.append(dict(candidate_id=c["candidate_id"],period=f"2026-{month:02d}",cycles=len(values),
                net=math.fsum(x[0] for x in values),score_pct=math.fsum(x[1] for x in values)))
        for quarter in range(1,5):
            values=grouping[("quarter",f"2026-Q{quarter}")]
            quarters.append(dict(candidate_id=c["candidate_id"],period=f"2026-Q{quarter}",cycles=len(values),
                net=math.fsum(x[0] for x in values),score_pct=math.fsum(x[1] for x in values)))
        positive=sorted((r for r in returns if r>0),reverse=True)
        concentration.append(dict(candidate_id=c["candidate_id"],top1_score_share_pct=100*sum(positive[:1])/sum(positive) if positive else None,
            top3_score_share_pct=100*sum(positive[:3])/sum(positive) if positive else None,
            top5_score_share_pct=100*sum(positive[:5])/sum(positive) if positive else None))
        with np.load(folder/"full_account_ledger.npz") as saved:book=saved["ledger"].reshape(-1,11)
        book=book[np.isfinite(book[:,5])]
        peaks=np.maximum.accumulate(np.r_[30000000.,book[:,5]])[1:]
        running=np.maximum.accumulate(peaks-book[:,5])
        assert np.all(np.diff(book[:,8])>=0)
        assert np.max(abs(running-book[:,8]))<.01
        assert abs(float(np.max(running))-result["mdd_krw"])<.01
        goal=bool(score>=25.-1e-8 and total_net>=60000000.-.01 and len(rows)>=42 and result["mdd_krw"]<=9350000.01 and
                  result["residual_contracts"]==0 and result["margin_shortage_free"])
        assert goal==result["goal_qualified"]
        metrics.append(dict(candidate_id=c["candidate_id"],cycles=len(rows),score_pct=score,net=total_net,
            mdd_krw=float(np.max(running)),goal_qualified=goal,status="PASS"))
    for r in csv.DictReader((ROOT/"registry_sources.csv").open(encoding="utf8",newline="")):
        assert hashlib.sha256(__import__("pathlib").Path(r["path"]).read_bytes()).hexdigest()==r["sha256"]
    for dep in json.loads((ROOT/"external_dependencies.json").read_text())["files"]:
        assert hashlib.sha256(__import__("pathlib").Path(dep["path"]).read_bytes()).hexdigest()==dep["sha256"]
    incident=json.loads((ROOT/"semantic_duplicate_incident.json").read_text())
    assert duplicates==[{k:d[k] for k in ("original","duplicate")} for d in incident["duplicates"]]
    table(out/"confirmed_semantic_duplicates.csv",duplicates)
    table(out/"semantic_duplicates_audit.csv",semantic)
    table(out/"independent_all_metrics.csv",metrics)
    table(out/"monthly_contribution.csv",months)
    table(out/"quarterly_contribution.csv",quarters)
    table(out/"profit_concentration.csv",concentration)
    write_json(out/"validation.json",dict(status="FINANCIAL_METRICS_PASS_SEMANTIC_UNIQUENESS_FAIL",semantic_uniqueness="FAIL",financial_metrics="PASS",conditions=500,unique_semantic_rules=len(seen),duplicates=duplicates,
        independent_date_parser="datetime.strptime",monthly_rows=len(months),quarterly_rows=len(quarters),
        completed_cycles=sum(r["cycles"] for r in metrics),goals=sum(r["goal_qualified"] for r in metrics),
        score_tolerance_pp=1e-8,money_tolerance_krw=.01,
        cumulative_mdd_nondecreasing=True,all_original_rule_metadata_hashes_preserved=True,
        external_dependencies_unchanged=True,code_hashes_match_every_registration=True,simulation_repeated=False))
    print(json.dumps(dict(status="FINANCIAL_METRICS_PASS_SEMANTIC_UNIQUENESS_FAIL",attempted=500,unique=len(seen),cycles=sum(r["cycles"] for r in metrics))))

if __name__=="__main__":main()
