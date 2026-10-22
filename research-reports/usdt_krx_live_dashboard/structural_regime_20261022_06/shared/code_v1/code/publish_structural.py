# /// script
# requires-python = "==3.12.0"
# dependencies = ["numpy==2.2.6"]
# ///
# Publish code once; raw market data remain hash-referenced on D:.
from __future__ import annotations
import json,shutil,sys
from runner import ROOT,SOURCE_HASH,MARGIN_HASH,write_json,table
from package_B import manifest
from path_reports import COMMON

def main() -> None:
    out=ROOT/"publish_payloads/shared_code_v1";out.mkdir()
    assert json.loads((ROOT/"control_regression/validation.json").read_text())["status"]=="PASS"
    for name in ("structural_tests.json","trail_integration_tests.json","metric_tests.json","drawdown_tests_v2.json","path_tests_v2.json"):
        assert json.loads((ROOT/name).read_text())["status"]=="PASS"
        shutil.copy2(ROOT/name,out/name)
    shutil.copytree(ROOT/"code",out/"code",ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(ROOT/"baseline_audit",out/"baseline_audit")
    shutil.copytree(ROOT/"diagnosis",out/"diagnosis")
    for name in ("validation.json","validation_saved_arrays.json","preregistration.json"):
        shutil.copy2(ROOT/"control_regression"/name,out/("control_"+name))
    for name in ("audit.json","numeric_result.npz","full_account_ledger.npz","cycles.csv.gz","fills.csv.gz","orders.csv.gz","period_contribution.csv"):
        shutil.copy2(ROOT/"control_regression/CONTROL_B"/name,out/("CONTROL_B_"+name))
    for name in ("registry_sources.csv","registry_summary.json","external_dependencies.json"):
        shutil.copy2(ROOT/name,out/name)
    shutil.copy2(ROOT/"baseline/registry.json",out/"settings.json")
    write_json(out/"strategy_code_ref.json",dict(strategy="code/",financial_engine_source="B path engine, only exit trigger hook added",
        financial_auditor="unchanged original audit.py and validation2.py",dependencies="external_dependencies.json",
        original_B_profit_exit_pct=.7,baseline_commit="c63352755d43b067b2124e748297efe6cbf6ecbf",
        prior_commit="d3faabebf5828cc00db4979dc48b12af63f4a751"))
    table(out/"results.csv",[json.loads((ROOT/"control_regression/validation.json").read_text())])
    shutil.copy2(ROOT/"control_regression/CONTROL_B/fills.csv.gz",out/"fills.csv.gz")
    table(out/"costs.csv",[dict(spot_fee=.0005,future_per_contract=600,clearing=.000003157,slip_bp_each_leg_side=2,
        rollover="both close/open fees and slips",borrowing="UNVERIFIED_NOT_INCLUDED")])
    write_json(out/"environment.json",dict(python=sys.version,numpy="2.2.6",numba="0.61.2",storage="D_ONLY",environment_changed=False))
    write_json(out/"provenance.json",dict(source_sha256=SOURCE_HASH,margin_sha256=MARGIN_HASH,final_oos_access=False,
        scope="approved exploratory 2026 KRX business dates Jan1..Oct15 plus required night calendar boundaries",
        input_status="INPUT_NOT_REMOTELY_REPRODUCIBLE",old_strategy_control_runs=1,new_conditions=0))
    write_json(out/"checkpoint.json",dict(status="CONTROL_AND_CAUSAL_TESTS_PASS_NEW_RUNS_ZERO",next_batch=1))
    report="# 구조 변경 연구 — 원장 진단·코드·CONTROL\n\n"
    report+="기존 B와60분대기형은 비교기준으로 보존. 여섯 새 구조를 비교하고 신규최대500조건. 첫5배치는 넓게, 후반은 이전배치 결과로 구조를 확장하며 매50조건 실행 전에 등록/게시한다. 수량/기간/비용/계좌변경 없음.\n\n"
    report+="저장 원장 감사:42사이클, 수익률16.7054302006977%, 순이익41,295,918.91원, MDD935만원. 비용전이익61,523,000원 중20,227,081.09원(32.8773%) 비용. 평균4.503일/최장29.088일,7일이상6회. 관측분61.795% 보유. 지연비용은 과거호가 부재로 분리확정 불가. 상세 diagnosis/ 및baseline_audit/.\n\n"
    report+="CONTROL을 한 번 실행한 뒤 JSON불리언 출력경계 오류 발생. 매매재계산 없이 저장된8개 배열을 원본과 정확히 비교했고 모든금융/첫청산감사PASS. 출력자료형만 수정. 신규조건은 아직0. 금융검산기는 재작성하지 않음.\n\n"
    report+="기존 합성MDD/정산/롤/현금 변조검사, 양방향17계약 추적청산·신호시점 변조검사, 6구조×2절단의 과거5개신호배열불변PASS. 금융엔진은 기존상태머신과배열ABI 보존을 위해210순수행 단일함수 유지; 새판단은별도 exit_policy.py와signals.py로 분리.\n\n"
    report+="모든 신규가설은 구조 변경이며 단순 임계값미세조정0%. 기존조건표 메타데이터를재조회해중복검사, 동일실제경로는결과에서묶음. 큰개선은25%·6천만원·42회·MDD935만원·잔여0·모든부족/거절0 동시충족만 표시. 허용차1e-8%p/0.01원.\n"+COMMON
    (out/"REPORT_KO.md").write_text(report,encoding="utf8")
    manifest(out)
    print(str(out))

if __name__=="__main__":main()
