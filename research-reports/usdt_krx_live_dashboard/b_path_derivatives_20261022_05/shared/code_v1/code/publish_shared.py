# /// script
# requires-python = "==3.12.0"
# dependencies = ["numpy==2.2.6"]
# ///
# Run after baseline/control audits and all-500 preregistration.
from __future__ import annotations
import json,shutil,sys
from runner import ROOT,SOURCE_HASH,MARGIN_HASH,table,write_json
from package_B import manifest

def main() -> None:
    out=ROOT/'publish_payloads/shared_code_v1'
    assert not out.exists()
    control=json.loads((ROOT/'control_regression/validation.json').read_text())
    assert control['status']=='PASS' and control['exact_trade_cost_cash_margin_path_match']
    assert json.loads((ROOT/'baseline_audit/validation.json').read_text())['status']=='PASS'
    assert json.loads((ROOT/'path_tests_v2.json').read_text())['status']=='PASS'
    out.mkdir(parents=True)
    for name in ('code','baseline_audit','control_regression'):
        shutil.copytree(ROOT/name,out/name,ignore=shutil.ignore_patterns('__pycache__','result.json'))
    shutil.copy2(ROOT/'control_regression/CONTROL_B/result_repaired.json',out/'control_regression/CONTROL_B/result.json')
    for name in ('all_500_preregistration.json','registry_sources.csv','registry_summary.json',
                 'reuse_rules.csv','metric_tests.json','path_tests_v2.json','drawdown_tests_v2.json','path_metric_tests.json'):
        shutil.copy2(ROOT/name,out/name)
    shutil.copy2(ROOT/'baseline/registry.json',out/'settings.json')
    write_json(out/'strategy_code_ref.json',dict(new_modules='code/',modified_engine='code/engine_path.py',
        original_financial_engine=dict(commit='7198d4f47ea458580fb522f3b9ebf37e10ea178c',
        path='research-reports/usdt_krx_live_dashboard/lump17_sweep_20261021_01/shared/repair_v2/code',
        engine_sha256='530dff2f478e2383d26e86847e032c40a77b061f8ed083b8ca4497574963f383',
        auditor_sha256='87694798f65bb88632a0bf1bfe8ceade3b06afbe55f2c8e9c3cd46aa4a14fd16'),
        input_loader=dict(commit='e1254e5141b3201cf594111cbc47b1fdfd6a5e9a',
        path='research-reports/usdt_krx_live_dashboard/lump17_extension_20261021_02/final_1000_comparison_v2/code/input_loader_frozen.py'),
        source_sha256=SOURCE_HASH,margin_sha256=MARGIN_HASH))
    table(out/'results.csv',[control])
    shutil.copy2(ROOT/'control_regression/CONTROL_B/fills.csv.gz',out/'fills.csv.gz')
    table(out/'costs.csv',[dict(spot_fee_per_side=.0005,future_fee_per_contract=600,clearing_rate=.000003157,
        slippage_bp_per_leg_side=2,roll='BOTH_LEGS',borrow='UNVERIFIED_NOT_INCLUDED',funding='NOT_APPLICABLE')])
    write_json(out/'environment.json',dict(python=sys.version,numpy='2.2.6',numba='0.61.2',pandas='3.0.1',
        storage='D_ONLY',execution='EXPLORATORY_PAPER',environment_changed=False,raw_input_status='INPUT_NOT_REMOTELY_REPRODUCIBLE'))
    write_json(out/'provenance.json',dict(baseline_commit='c63352755d43b067b2124e748297efe6cbf6ecbf',
        previous_final_commit='8a33d1d495ddcb8b3ce0c3b13e2bf31abfd95c43',
        source_sha256=SOURCE_HASH,margin_sha256=MARGIN_HASH,
        scope='Approved exploratory KRX business dates2026-01-01..10-15 and required night calendar boundaries',
        final_oos_access=False,old_strategy_simulations=1,control_excluded_from_500=True))
    write_json(out/'checkpoint.json',dict(status='CONTROL_VERIFIED_ALL_500_PREREGISTERED_NEW_RUNS_ZERO',new_conditions=0,next_batch=1))
    report='# B 개선형 경로 파생500조건 — 코드·사전등록·CONTROL\n\n'
    report+='기준 BF-09-027의 익절0.7%를 그대로 보존했습니다. 기존 저장원장을 재검산하고, 별도 확장 엔진으로 기준 B CONTROL만 한 번 실행했습니다. 체결·비용·정산·롤오버·현금·증거금·위험·잔여·평가곡선 배열이 모두 원본과 정확히 동일합니다. CONTROL은 신규500조건에 포함하지 않습니다.\n\n'
    report+='42사이클·점수16.7054302006977%·순이익41,295,918.91원·MDD935만원·잔여0을 확인했습니다. 이전 전략의 조건이나 원장은 변경하지 않았습니다.\n\n'
    report+='전체500개 순서와 코드·입력 해시를 신규 실행 전에 고정했습니다. 방향별 진입/회복100, 동일 진입 청산효과100, 확인·재진입100, 과거시장상태100, 장기보유·위험100조건입니다. 기존 규칙과 중복인 제안은 제외하고 재사용 목록에 남겼습니다. 동일 시세를 본 후의 탐색 가설이며 독립 검증이 아닙니다.\n\n'
    report+='PF 합성5검사, 기존 MDD·SETTLE·롤·현금 변조 검출검사, 신규 경로7검사와 미래변경시 과거특징 불변 검사를 통과했습니다. 초기 테스트 연결의 엔진 인자 차이는 새 사본의 import만 수정했고, 금융 검산기는 재작성하지 않았습니다.\n\n'
    report+='현재 신규 매매는0조건입니다. 이후 각50조건 게시·원격 바이트와SHA 검증을 마쳐야 다음 배치를 실행합니다. 역배 차입/비용과 실제17계약 호가 체결은 미검증이며 원시가격은 D:에만 보존합니다. 보호Final OOS·Gateway·예약작업·수집기는 변경하지 않습니다.\n'
    (out/'REPORT_KO.md').write_text(report,encoding='utf8')
    manifest(out)
    print(str(out),flush=True)

if __name__=='__main__':main()
