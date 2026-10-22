# /// script
# requires-python = "==3.12.0"
# dependencies = ["numpy==2.2.6"]
# ///
# Run: python -B code/bootstrap.py build_structural.py BATCH
from __future__ import annotations
import hashlib,json,random,sys
from collections import defaultdict
from runner import ROOT,canonical,write_json
from registry import BASE,inventory,signature
from structural_schema import StructuralRule

MODES=("driver","residual","momentum","trail","opportunity","selector")
LABELS={"driver":"가격주도 원인 선별","residual":"중심 이탈·복귀 상태","momentum":"괴리 확대 추세 추종",
        "trail":"비용차감 이익 추적","opportunity":"반전 진입·상태 전환 청산","selector":"성숙한 과거 예측 기반 선택"}

def proposal(mode: str, rng: random.Random) -> StructuralRule:
    """Produce a structurally identified rule, never a quantity/cost change."""
    r=dict(BASE)
    r.update(structure=mode,family="structural_"+mode,slippage_bp=2.,
        lookback=rng.choice([60,120,240,480]),entry_width=rng.choice([1.,1.5,2.,2.5]),
        inner_width=rng.choice([0.,.25,.5]),long_recovery_pp=rng.choice([.35,.6,.9]),
        short_recovery_pp=rng.choice([.35,.6,.9]),pnl_profit_pct=0.,
        max_hold_minutes=0.,pnl_stop_pct=0.,gap_exit_enabled=True,
        confirmation_pp=0.,cooldown_minutes=0.,reversal_entry=False)
    match mode:
        case "driver":
            r.update(entry_width=rng.choice([.4,.7,1.,1.4,1.8]),driver=rng.choice(["spot","future","balanced"]),
                driver_share=rng.choice([.6,.8]),
                impulse_pp=rng.choice([.1,.25,.4]),pnl_profit_pct=rng.choice([0.,.7]))
            if r["driver"]=="balanced":r["driver_share"]=rng.choice([.1,.25,.4])
        case "residual":
            r.update(center_drift_limit=rng.choice([.002,.01,.03]),reversal_entry=rng.choice([False,True]),
                     pnl_profit_pct=rng.choice([0.,.5,.9]))
        case "momentum":
            r.update(impulse_pp=rng.choice([.05,.15,.3]),max_hold_minutes=rng.choice([360.,1440.,4320.]),
                pnl_profit_pct=rng.choice([0.,1.]))
        case "trail":
            r.update(entry_model=rng.choice(["fixed","residual"]),entry_width=rng.choice([.7,1.,1.5,2.]),
                trailing_arm_pct=rng.choice([.3,.6,1.,1.5]),trailing_giveback_pct=rng.choice([.1,.2,.4]),
                stalled_trail_minutes=rng.choice([0.,120.,720.]),max_hold_minutes=rng.choice([0.,4320.]),
                gap_exit_enabled=False)
        case "opportunity":
            r.update(reversal_entry=True,impulse_pp=rng.choice([.1,.3,.6]),
                max_hold_minutes=rng.choice([360.,1440.,4320.]),pnl_stop_pct=rng.choice([.8,1.5]))
        case "selector":
            r.update(selector_horizon=rng.choice([30,60,180]),selector_memory=rng.choice([1440,4320,10080]),
                selector_update_observations=rng.choice([240,720]),selector_min_edge_pp=rng.choice([0.,.1,.25]),
                max_hold_minutes=rng.choice([1440.,4320.]))
        case unknown:
            raise AssertionError(mode)
    if mode not in ("driver",):
        r["long_recovery_pp"]=.6;r["short_recovery_pp"]=.6
    return r

def normalized(rule: StructuralRule) -> StructuralRule:
    """Drop inactive parameters before dedup; execution equivalence is separate."""
    r=dict(rule)
    mode=r["structure"]
    for k in ("long_entry_gap_pct","short_entry_gap_pct","long_absolute_exit_gap_pct","short_absolute_exit_gap_pct"):
        r.pop(k,None)
    if mode!="driver":
        r.pop("long_recovery_pp",None);r.pop("short_recovery_pp",None)
    if mode in ("driver","trail"):
        r.pop("inner_width",None)
    return r

def main() -> None:
    number=int(sys.argv[1]);assert 1<=number<=10
    if not (ROOT/"registry_sources.csv").exists():
        inventory()
    previous=[json.loads(p.read_text()) for p in sorted((ROOT/"preregistration").glob("batch_*.json"))]
    assert len(previous)==number-1
    used={hashlib.sha256(canonical(normalized(c["rule"]))).hexdigest() for p in previous for c in p["conditions"]}
    history=[json.loads(p.read_text()) for p in (ROOT/"batches").glob("batch_*/candidates/*/result.json")]
    counts=dict(zip(MODES,[10,10,10,10,5,5]))
    seeds={}
    if number>5:
        groups=defaultdict(list)
        for row in history:
            if row["cycles"] and row["margin_shortage_free"]:groups[row["structure"]].append(row)
        best=sorted(groups,key=lambda k:max(x["score_pct"] for x in groups[k]),reverse=True)
        counts={k:6 for k in MODES}
        for k in best[:2]:counts[k]+=7
        if len(best)<2:
            for k in MODES[:2-len(best)]:counts[k]+=7
        for k in best:
            winner=max(groups[k],key=lambda x:x["score_pct"])
            for p in previous:
                for c in p["conditions"]:
                    if c["candidate_id"]==winner["candidate_id"]:seeds[k]=c["rule"]
    rng=random.Random(202610220600+number)
    candidates=[];rejected=0
    for mode,count in counts.items():
        for slot in range(count):
            for attempt in range(20000):
                r=proposal(mode,rng)
                if number>5 and mode in seeds and slot%2==0:
                    anchor=seeds[mode]
                    mutable=[k for k in r if k in anchor and r[k]!=anchor[k] and k not in ("structure","family")]
                    if mutable:
                        keep=set(rng.sample(mutable,min(2,len(mutable))))
                        r={k:(r[k] if k in keep else anchor.get(k,r[k])) for k in r}
                norm=normalized(r)
                fingerprint=hashlib.sha256(canonical(norm)).hexdigest()
                if fingerprint not in used:
                    used.add(fingerprint);break
                rejected+=1
            else:raise AssertionError("UNIQUE_POOL_EXHAUSTED")
            cid=f"SR-{number:02d}-{len(candidates)+1:03d}"
            candidates.append(dict(candidate_id=cid,group=LABELS[mode],category=mode,
                hypothesis="후속 탐색: "+LABELS[mode],rule=r,
                rule_sha256=hashlib.sha256(canonical(r)).hexdigest(),semantic_sha256=fingerprint,
                structurally_new=True,improvement_intent=dict(driver="비용 대비 불리한 거래 제거",
                residual="거래 기회 증가",momentum="거래당 이익 확대",trail="거래당 이익 확대",
                opportunity="장기 보유 감소",selector="비용 대비 불리한 거래 제거")[mode]))
    assert len(candidates)==50
    hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((ROOT/"code").glob("*.py"))}
    record=dict(batch=f"batch_{number:04d}",conditions=candidates,grid_sha256=hashlib.sha256(canonical(candidates)).hexdigest(),
        code_sha256=hashes,source_sha256="62becd7d50e05bdcf47010cdcdfdd8178bbe2ef1d8099a84ab18fae8fea19fbd",
        margin_sha256="910816bc61c9d9b7361bec370e225bfeae9cde0f11b889265cb4409ecb9344b8",
        allocation=counts,structural_conditions=50,micro_tuning_conditions=0,
        duplicate_proposals_skipped=rejected,prior_new_conditions=len(history),
        adaptive_generation=number>5,past_results_only=True,
        goals=dict(score_pct=25.,net_krw=60000000.,min_cycles=42,max_mdd_krw=9350000.,residual=0,shortage_reject=0),
        tolerances=dict(score_pp=1e-8,money_krw=.01),raw_status="INPUT_NOT_REMOTELY_REPRODUCIBLE",
        execution="Next contiguous observed OPEN; 17 contracts / 170000USDT; no adds; fixed2bp/leg",
        selector="Lagged overlapping cost-adjusted hedge probes; proxy not investable shadow returns; previous observations only; one actual account.")
    write_json(ROOT/"preregistration"/f"batch_{number:04d}.json",record)
    print(json.dumps(dict(status="PREREGISTERED",batch=number,allocation=counts,duplicates=rejected)))

if __name__=="__main__":main()
