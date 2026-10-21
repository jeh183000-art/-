# /// script
# requires-python = "==3.12.0"
# dependencies = ["numpy==2.2.6"]
# ///
# Run: python -B code/bootstrap.py shared_packet.py
import json
import shutil
import sys
from runner import ROOT, SOURCE_HASH, MARGIN_HASH, table, write_json
from package_B import manifest

out=ROOT/'publish_payloads/B_baseline_and_code_v1';assert not out.exists();out.mkdir(parents=True)
shutil.copytree(ROOT/'code',out/'code',ignore=shutil.ignore_patterns('__pycache__'))
shutil.copytree(ROOT/'baseline_audit',out/'baseline_audit')
shutil.copy2(ROOT/'baseline/registry.json',out/'settings.json')
shutil.copy2(ROOT/'baseline/remote_raw_inventory.json',out/'original_B_archive_ref.json')
shutil.copy2(ROOT/'drawdown_tests_v2.json',out/'drawdown_tests_v2.json')
for filename in ('cycles.csv.gz','fills.csv.gz','orders.csv.gz'):
    shutil.copy2(ROOT/'baseline/B_original'/filename,out/filename)
b=json.loads((ROOT/'baseline/B_original/result.json').read_text());table(out/'results.csv',[b])
table(out/'costs.csv',[dict(spot_fee_per_side=.0005,futures_fixed_per_contract=600,clearing_rate=.000003157,slippage_bp_per_leg_side=2,roll='BOTH_LEGS',borrow='UNVERIFIED_NOT_INCLUDED',funding='NOT_APPLICABLE',baseline_fees=b['fees_krw'],baseline_slippage=b['slippage_krw'])])
write_json(out/'environment.json',dict(python=sys.version,numpy='2.2.6',numba='0.61.2',pandas='3.0.1',storage='D_ONLY',existing_environment_preserved=True))
write_json(out/'strategy_code_ref.json',dict(common_commit='7198d4f47ea458580fb522f3b9ebf37e10ea178c',common_path='research-reports/usdt_krx_live_dashboard/lump17_sweep_20261021_01/shared/repair_v2/code',engine_sha256='530dff2f478e2383d26e86847e032c40a77b061f8ed083b8ca4497574963f383',auditor_sha256='87694798f65bb88632a0bf1bfe8ceade3b06afbe55f2c8e9c3cd46aa4a14fd16',unchanged=True))
write_json(out/'provenance.json',dict(baseline_commit='e1254e5141b3201cf594111cbc47b1fdfd6a5e9a',source_sha256=SOURCE_HASH,margin_sha256=MARGIN_HASH,input_scope='Approved exploratory KRX business dates 2026-01-01..10-15 and required night boundaries',raw_input_status='INPUT_NOT_REMOTELY_REPRODUCIBLE',final_oos_access=False,old_1000_recomputed=False,A_C_D_search_enabled=False))
write_json(out/'checkpoint.json',dict(status='BASELINE_LEDGER_REGRESSION_PASS_NO_NEW_CONDITION_EXECUTED',new_conditions=0,budget=500,old_1000_preserved=True))
(out/'REPORT_KO.md').write_text('# B 전략 원장 검산·장기 보유 진단 및 코드 보존\n\nB는 L17-01-013입니다. 기존39사이클·수익률합계14.9513190710%·순이익36,755,589.35원·MDD9,350,000원·잔여0이 저장 원장 독립 검산과 일치했습니다. 기존1,000조건은 재실행하지 않았습니다. B 원본9파일은 원격 archive_inventory SHA와 일치하며 기존 세 후보 A/C/D 집합도 그대로 보존합니다.\n\n진입은 정배 -1% 하향 통과 / 역배 +1% 상향 통과, 청산은 실제 진입 신호봉 괴리율에서 유리하게0.6%p 회복입니다. 최초17계약·170,000 USDT, 추가진입 없음, 선물 초기3,000만원·계좌 간 이체/추가입금 없음, 기존2bp 비용을 유지합니다. 현물 충분조달 및 역배 차입 미검증 가정은 유지합니다.\n\n39회 중25회가 하루 이상,7회가7일 이상 보유되었습니다. 평균4.3083일·중앙값1.4375일·최장26.9028일입니다. 7일 시점의 관측 가능한 미청산7회는 모두 가정 청산비 차감 평가손실 후 나중에 이익 청산됐습니다. 24시간 관측15회 중11회도 평가손실이며10회는 결측으로 별도 표시했습니다. 따라서100% 완료 승률은 중간 손실이 없다는 뜻이 아닙니다. 이 표는 기존 포지션의 관측 평가 진단이며 시간청산 재백테스트나 미래 회복 보장이 아닙니다.\n\n신규 목표는 기준 수익률 초과·39회 이상·미청산0·MDD935만원 이하·진입/롤/초기 및 유지증거금 부족0입니다. 조건 미달도 삭제하지 않습니다. 새 전략은 B의 회복형 규칙에서만 파생하고 기존1,000조건과 설정 중복을 제거합니다. 원시 입력은 D: 전용으로 INPUT_NOT_REMOTELY_REPRODUCIBLE입니다. 보호OOS·Gateway·OpenClaw·예약 작업·수집기는 변경하지 않습니다.\n',encoding='utf8')
manifest(out);print(str(out),flush=True)
