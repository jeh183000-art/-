import csv
import gzip
import hashlib
import json
import shutil
from pathlib import Path

from runner import ROOT, table, write_json, SOURCE_HASH, MARGIN_HASH


def main():
    prior=ROOT.parent/'lump17_sweep_20261021_01'
    source=prior/'publish_payloads/final_500_audit_v1'
    out=ROOT/'publish_payloads/checker_stop_anchor_audit_v1'
    assert not out.exists();out.mkdir(parents=True)
    shutil.copytree(ROOT/'code',out/'code',ignore=shutil.ignore_patterns('__pycache__'))
    shutil.copytree(ROOT/'anchor_audit',out/'anchor_audit')
    shutil.copy2(ROOT/'vector_unit_tests.json',out/'vector_unit_tests.json')
    anchors=json.loads((ROOT/'anchor_audit/anchor_validation.json').read_text())['anchors']
    with (source/'results_all_500.csv').open(encoding='utf8',newline='') as stream:
        old=list(csv.DictReader(stream))
    rules={r['candidate_id']:r['rule'] for r in json.loads((source/'settings_all_500.json').read_text())['conditions']}
    eligible=[r for r in old if r['feasible']=='True' and int(r['cycles'])>0]
    groups={'전체 최고(계좌조건 통과)':eligible,'완료10회 이상':[r for r in eligible if int(r['cycles'])>=10],
        '미청산0계약':[r for r in eligible if int(r['residual_contracts'])==0],
        '정배 전용':[r for r in eligible if rules[r['candidate_id']].get('allowed_direction',0)==1],
        '역배 전용':[r for r in eligible if rules[r['candidate_id']].get('allowed_direction',0)==-1],
        '유지증거금 부족0':[r for r in old if int(r['cycles'])>0 and int(r['maintenance_breach_marks'])==0]}
    rank=[]
    for name,rows in groups.items():
        rows.sort(key=lambda r:float(r['score_pct']),reverse=True)
        rank.append(dict(category=name,candidate_id=rows[0]['candidate_id'] if rows else 'NOT_TESTED',
            cycles=rows[0]['cycles'] if rows else '',score_pct=rows[0]['score_pct'] if rows else '',
            account_feasible=rows[0]['feasible'] if rows else '',source='EXISTING_500_FROM_BASELINE_COMMIT_NOT_NEW_RESULTS'))
    table(out/'existing_500_six_rankings.csv',rank)
    table(out/'results.csv',[{k:v for k,v in row.items() if k!='rule'} for row in anchors])
    table(out/'costs.csv',[dict(candidate_id=a['candidate_id'],fees_krw=a['fees'],slippage_krw=a['slippage'],terminal_exit_cost=a['terminal_exit_cost'],borrow='UNVERIFIED_NOT_INCLUDED') for a in anchors])
    for cid,batch in [('L17-07-004',7),('L17-01-013',1)]:
        folder=prior/'batches'/f'batch_{batch:04d}'/'candidates'/cid
        for name in ('fills','cycles','orders'):
            with gzip.open(folder/f'{name}.csv.gz','rb') as inp,(out/f'{cid}_{name}.csv').open('xb') as dest:shutil.copyfileobj(inp,dest)
    checkpoint=dict(status='STOPPED_NEW_SWEEP_AFTER_CHECKER_DEVELOPMENT_ERROR',new_conditions_registered=0,new_conditions_executed=0,
        maximum_new_conditions=500,existing_results_modified=False,anchor_ledger_revalidation='PASS_AFTER_NEW_CHECKER_DEFINITION_FIX',
        old_trading_engine_changed=False,workers_running=False,final_oos_access=False,
        remaining_work=['Preregister diverse new50 conditions','Run and verify batches only after explicit resumption of stopped work'])
    write_json(out/'checkpoint.json',checkpoint)
    write_json(ROOT/'checkpoint.json',checkpoint)
    write_json(out/'settings.json',dict(anchors=[dict(candidate_id=a['candidate_id'],rule=a['rule']) for a in anchors],
        frozen_controls=dict(contracts=17,spot_quantity=170000,futures_initial_cash=30000000,spot_cap=None,additional_entries=False,
            simultaneous_opposite=False,external_deposits=False,automatic_account_transfers=False,slippage_bp=2),new_conditions=[]))
    diagnostic=dict(initial_synthetic_error_krw=227317.1660000123,
        cause='New vector checker compared instantaneous drawdown with the original ledger running maximum drawdown.',
        definition_fix='drawdown = cumulative_peak - equity; MDD = cumulative_max(drawdown)',
        fields_already_matching_before_fix=['spot_cash','futures_cash','unrealized','margin','total_equity','open_net','direction','financing'],
        validation_scope='Synthetic fixture then read-only saved anchors; no market strategy simulation or new condition executed',
        preexisting_engine_or_result_changed=False,corrected_synthetic_tests='PASS',saved_anchor_replays='PASS',
        stop_reason='User instruction: stop immediately on checker error and report cause')
    write_json(out/'diagnostic.json',diagnostic)
    write_json(out/'environment.json',dict(python='3.12.0',numpy='2.2.6',numba='0.61.2',storage='D_ONLY',mode='PAPER_READ_ONLY_ANCHOR_AUDIT'))
    write_json(out/'strategy_code_ref.json',dict(commit='7198d4f47ea458580fb522f3b9ebf37e10ea178c',
        prefix='research-reports/usdt_krx_live_dashboard/lump17_sweep_20261021_01/shared/repair_v2/code',
        engine_sha256=hashlib.sha256((prior/'code/engine.py').read_bytes()).hexdigest(),auditor_sha256=hashlib.sha256((prior/'code/audit.py').read_bytes()).hexdigest(),unchanged=True))
    write_json(out/'provenance.json',dict(baseline_commit='88bfd36584e92892aa01e3f1136da8f1cdb7f1b8',source_sha256=SOURCE_HASH,margin_sha256=MARGIN_HASH,
        raw_input_status='INPUT_NOT_REMOTELY_REPRODUCIBLE',anchor_source_inventory_remote_hashes_verified=True,
        full_account_archives='Original immutable batch0001 and batch0007 archive_parts.json/archive_inventory.csv; no duplicate account or market inputs uploaded',
        protected_oos_access=False))
    a,b=anchors
    report=f'''# 일괄 17계약 후속 연구 — 검산기 오류로 신규 스윕 중단

신규 조건 사전등록·실행은 **0/500조건**입니다. 이번 연구는 완료되지 않았습니다.
새 독립 검산기의 합성 검사에서 MDD 정의 오류가 발생하여 사용자의 즉시 중단 규칙을 적용했습니다.
오류는 기존 매매 엔진이 아닌 이번에 새로 만든 검산기의 현재 낙폭과 누적 최대낙폭 혼동입니다.
새 검산기만 수정하여 합성 검사와 두 기존 후보의 저장 원장을 진단 목적으로 대조했습니다.
기존 거래를 재계산하거나 기존 결과·신호·비용·원본·Final OOS를 변경하지 않았습니다.
기존 두 후보의 원격 원장 해시, 체결·정산·롤오버·비용·현금·증거금과 수익률은 모두 일치했습니다.
새 50조건은 실행하지 않고 중단 상태와 재현 코드를 보존했습니다.

|항목|L17-07-004|L17-01-013|
|---|---:|---:|
|완료 사이클|{a['cycles']}|{b['cycles']}|
|비용 차감 사이클 수익률 합계|{a['score_pct']:.10f}%|{b['score_pct']:.10f}%|
|완료 거래 순이익|{a['net_realized']:,.2f}원|{b['net_realized']:,.2f}원|
|MDD|{a['mdd']:,.2f}원|{b['mdd']:,.2f}원|
|잔여 계약|17|0|
|최장 보유|{a['longest_hold_minutes']/1440:.5f}일|{b['longest_hold_minutes']/1440:.5f}일|
|종료 가정청산 보조 점수|{a['terminal_assumed_score_pct']:.10f}%|{b['terminal_assumed_score_pct']:.10f}%|
|종료 가정청산 총순손익|{a['terminal_assumed_net']:,.2f}원|{b['terminal_assumed_net']:,.2f}원|
|최소 초기증거금 여유|{a['minimum_initial_headroom']:,.2f}원|{b['minimum_initial_headroom']:,.2f}원|
|최소 유지증거금 여유|{a['minimum_maintenance_headroom']:,.2f}원|{b['minimum_maintenance_headroom']:,.2f}원|

## 정확한 기존 규칙

L17-07-004: 정배 -1.7% 하향 통과 진입 → +1.5% 이상 청산; 역배 +1.7% 상향 통과 진입 → -1.5% 이하 청산. 추가진입·손절·시간청산 없음.

L17-01-013: 정배 -1.0% 하향 통과 / 역배 +1.0% 상향 통과 진입. 실제 **진입 신호봉 괴리율**에서 각각 0.6%p 유리하게 회복하면 청산. 절대 청산선으로 바꾸지 않습니다. 추가진입·손절·시간청산 없음.

모든 매매는 최초17계약·170,000 USDT, 선물 초기3,000만원, 한 방향 한 묶음, 외부 입금·계좌 간 자동이체 없음, 현물 충분 조달 가정과 기존 수수료·각 레그 편도2bp·롤오버 양쪽 비용입니다. 종료 가정청산을 제외한 신호 체결은 다음 연속 관측 1분봉 시가 대용값입니다.

## L17-07-004 미청산 위험

미청산은 2026-10-07 11:02 KST 진입한 역배17계약 한 묶음입니다. 마지막 공통 관측은 {a['last_timestamp_kst']} KST, USDT/KRW {a['last_spot_close']:,.1f}원, 선물 {a['last_future_close']:,.1f}원(A75610)입니다. 공식 장마감 종가나 현재 호가로 오인하지 않습니다.

잔여 보유시간은 {a['residual_hold_minutes']/1440:.5f}일, 보유 중 최대 관측 평가손실은 2,428,750.27원(현물 최초 진입명목 대비1.04741688%)입니다. 마지막 두 종가로 청산한다고 가정하면 추가 청산비용 {a['terminal_exit_cost']:,.2f}원 차감 후 잔여 순손익은 {a['residual_net_after_exit_cost']:+,.2f}원입니다. 종료 가정청산 MDD는 {a['terminal_assumed_mdd']:,.2f}원으로 기존 MDD와 같습니다.

따라서 이번 마지막 관측시점에는 손실 포지션을 미청산으로 숨겨 주 점수가 높아졌다는 증거는 없습니다. 다만 완료6사이클의 적은 표본, 최장105.46일 자금 묶임, 잔여 약8.19일 보유와 약243만원 중간 평가손실은 별도 위험입니다. 잔여 손익은 주 점수에 넣지 않았습니다.

마지막 공통 관측 뒤의 연속 봉, 당시 실제 호가·잔량·17계약 체결·170,000 USDT 차입 및 상환 가능성을 확인하지 못했습니다. **가정 청산은 실제 청산 가능성 입증이 아니며 역배는 차입 가능성·비용 미검증 이론값입니다.** 호가·분중 손실 미관측, 7월6일~8월2일 증거금 일정 추론 한계도 유지합니다. 현물 조달은 충분하다는 가정이며 실제 사용자 잔액을 확인한 결과가 아닙니다.

## 이번 중단과 다음 단계

합성 검사 최초 차이는227,317.166원이며 오직MDD 필드에서 발생했습니다. 현금·가격·손익·증거금은 일치했습니다. 수정은 현재낙폭 배열에 누적 최댓값을 한 번 더 적용하는 것입니다. 합성 회귀 검사 후 원본 저장 원장을 대조한 최대 계좌 차이는 L17-07-004 {a['independent_vector_max_difference']:.12f}원, L17-01-013 {b['independent_vector_max_difference']:.12f}원입니다. 기존 결과를 수정하거나 허용차를 완화하지 않았습니다.

사용자의 검산기 오류 시 즉시 중단 지시에 따라 새 스윕을 재개하지 않았습니다. 신규 진입·청산 가설과50조건 사전등록 및 이후 배치 실행은 미실행입니다. 기존500조건 기준의6종 순위 조회만 existing_500_six_rankings.csv에 분리했으며, 역배 전용17계약 전략은 기존500조건에 없어 NOT_TESTED입니다. 이를 신규 최고 발견으로 보고하지 않습니다.

원본 계좌 원장은 기준 커밋의 batch0001·batch0007 압축 보관본과 SHA로 참조하고 중복 업로드하지 않았습니다. 두 후보의 전체 체결·사이클·주문 원장, 독립 검산 소스, 상세 위험 CSV, 진단·환경·설정·체크포인트를 이 폴더에 보존합니다. 원시 시세는 D: 전용으로 INPUT_NOT_REMOTELY_REPRODUCIBLE입니다. Gateway·예약 작업·다른 연구·수집기·보호 Final OOS는 변경하지 않았습니다.
'''
    (out/'REPORT_KO.md').write_text(report,encoding='utf8')
    rows=[]
    for path in sorted(out.rglob('*')):
        if not path.is_file():continue
        relative=path.relative_to(out).as_posix();role='results_csv'
        if relative.startswith('code/') or path.name=='strategy_code_ref.json':role='strategy_code'
        elif path.suffix=='.json':role='settings'
        if path.name=='environment.json':role='environment'
        if 'fills' in path.name or 'cycles' in path.name:role='fills'
        if path.name=='costs.csv':role='costs'
        if path.suffix=='.md':role='statistics_report'
        rows.append(dict(path=relative,role=role,bytes=path.stat().st_size,sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    table(out/'manifest.csv',rows,['path','role','bytes','sha256'])
    print(json.dumps(dict(status=checkpoint['status'],output=str(out),files=len(rows)+1)),flush=True)


if __name__=='__main__':main()
