# /// script
# requires-python = "==3.12.0"
# dependencies = ["numpy==2.2.6"]
# ///
# Run: python -B code/bootstrap.py shared_packet.py
import json,shutil,sys
from runner import ROOT,SOURCE_HASH,MARGIN_HASH,table,write_json
from package_B import manifest

out=ROOT/'publish_payloads/shared_code_v1';assert not out.exists();out.mkdir(parents=True)
registry=json.loads((ROOT/'baseline/registry.json').read_text());audit=json.loads((ROOT/'baseline_audit/validation.json').read_text())
assert audit['status']=='PASS' and json.loads((ROOT/'metric_tests.json').read_text())['status']=='PASS'
shutil.copytree(ROOT/'code',out/'code',ignore=shutil.ignore_patterns('__pycache__'))
shutil.copytree(ROOT/'baseline_audit',out/'baseline_audit')
for name in ('metric_tests.json','drawdown_tests_v2.json'):shutil.copy2(ROOT/name,out/name)
write_json(out/'settings.json',registry)
write_json(out/'strategy_code_ref.json',dict(new_modules='code/',common_engine=dict(commit='7198d4f47ea458580fb522f3b9ebf37e10ea178c',path='research-reports/usdt_krx_live_dashboard/lump17_sweep_20261021_01/shared/repair_v2/code',engine_sha256='530dff2f478e2383d26e86847e032c40a77b061f8ed083b8ca4497574963f383',auditor_sha256='87694798f65bb88632a0bf1bfe8ceade3b06afbe55f2c8e9c3cd46aa4a14fd16'),source_sha256=SOURCE_HASH,margin_sha256=MARGIN_HASH))
write_json(out/'original_parent_archive_ref.json',dict(commit=registry['remote_baseline_inventory_commit'],path='research-reports/usdt_krx_live_dashboard/b_focus_20261021_03/batches/batch_0009_results_v1',candidate='BF-09-027',files=registry['baseline_files'],unchanged_baseline=True))
table(out/'results.csv',[dict(candidate_id='BF-09-027',cycles=audit['cycles'],score_pct=audit['score_pct'],net=audit['net'],mdd=audit['mdd'],profit_factor_krw=audit['profit_factor_krw'],profit_factor_status=audit['profit_factor_status'],new_market_runs=0)])
table(out/'fills.csv',[dict(status='UNCHANGED_BASELINE_FULL_RAW_LEDGER_REFERENCED',remote='original_parent_archive_ref.json')])
table(out/'costs.csv',[dict(spot_fee_per_side=.0005,futures_fixed_per_contract=600,clearing_rate=.000003157,slippage_bp_per_leg_side=2,roll='BOTH_LEGS',borrow='UNVERIFIED_NOT_INCLUDED',funding='NOT_APPLICABLE')])
write_json(out/'environment.json',dict(python=sys.version,numpy='2.2.6',numba='0.61.2',pandas='3.0.1',storage='D_ONLY',mode='EXPLORATORY_PAPER',environment_changed=False,static_type_checker='not installed; preserved frozen runtime; numeric/ledger/runtime checks used'))
write_json(out/'provenance.json',dict(baseline_commit=registry['baseline_commit'],approved_source_sha256=SOURCE_HASH,margin_sha256=MARGIN_HASH,scope='Approved KRX business dates2026-01-01..2026-10-15 plus necessary night calendar boundaries',raw_data='INPUT_NOT_REMOTELY_REPRODUCIBLE',common_engine_unchanged=True,protected_final_oos_access=False,prior_conditions_recomputed=False))
write_json(out/'checkpoint.json',dict(status='BASELINE_AUDIT_PASSED_NEW_STUDY_PREREG_PENDING',new_conditions=0,next_batch=1,maximum_new_conditions=500))
(out/'REPORT_KO.md').write_text('# B 개선형 추가 연구 기준 검산·공통 코드\n\nBF-09-027 원본9파일을 기존 원격 원장 해시와 대조하고 저장된42사이클·체결·현금·정산·롤오버·증거금 원장을 두 방식으로 재검산했습니다. 기준 점수16.7054302006977%, 순이익41,295,918.91원, MDD935만원, 잔여0을 확인했습니다. 기존 전략을 다시 시뮬레이션하지 않았습니다.\n\n신규 PF 합성5검사와 기존 누적 MDD 합성검사를 통과했습니다. PF는 비용차감 완료사이클 원화이익합/손실합 절대값이며 손실이 없으면∞ 상태로 기록하고 미완료 손익은 포함하지 않습니다. 이 코드 묶음과 입력·매매 엔진의 버전/해시를 매 배치에서 참조합니다. 기존1500조건 및 신규 배치와 중복을 제외하고, 초반2배치는 회복0.6%p OR 순손익0.7% 익절을 유지한 진입선만 넓게 비교합니다. 이후 회복폭·익절·조합·비대칭·반전·위험 가설을 단계별 비교합니다.\n\n모든 실행은17계약·170000 USDT, 추가진입없음, 선물초기현금3천만원, 추가입금/자동이체없음입니다. 승인된 탐색자료만 사용하며 기존 A/B/C/D·BF-09-027·보호Final OOS·Gateway·OpenClaw·예약작업·다른 연구는 변경하지 않습니다. 역배 차입/비용, 과거호가 및17계약 체결 가능성, 증거금일정 추론의 한계는 유지합니다. 원시자료는D:전용이며 INPUT_NOT_REMOTELY_REPRODUCIBLE입니다. 신규 시장시뮬레이션은 아직0건입니다.\n',encoding='utf8')
manifest(out);print(str(out),flush=True)
