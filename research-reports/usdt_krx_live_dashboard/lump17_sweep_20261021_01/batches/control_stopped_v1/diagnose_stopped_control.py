from __future__ import annotations

import csv
import gzip
import hashlib
import json
import shutil
from pathlib import Path

import numpy as np

from runner import ROOT, REFERENCE, table, write_json
from package import manifest


def main():
    source=ROOT/'control_reproduction'
    out=ROOT/'publish_payloads/control_stopped_v1'
    assert not out.exists();out.mkdir(parents=True)
    shutil.copytree(source,out/'control_reproduction')
    shutil.copy2(ROOT/'publication/code_ref.json',out/'strategy_code_ref.json')
    shutil.copy2(Path(__file__),out/'diagnose_stopped_control.py')
    numbers=np.load(source/'numeric_result.npz')
    account=np.load(source/'full_account_ledger.npz')['ledger']
    old_events={}
    with (REFERENCE/'events.csv').open(encoding='utf8',newline='') as stream:
        for row in csv.DictReader(stream):
            key=(int(row['row']),row['kind'],int(row['cycle_id']))
            bucket=old_events.setdefault(key,np.zeros(6))
            for at,field in enumerate(('spot_gross','future_segment','spot_fee','future_fee','spot_slippage','future_slippage')):
                bucket[at]+=float(row[field])
    kinds={1:'ENTRY',2:'EXIT',3:'ROLL_CLOSE',4:'ROLL_OPEN',5:'SETTLE'}
    maximum_event_difference=0.
    assert len(numbers['events'])==len(old_events)
    for event in numbers['events']:
        key=(int(event[1]),kinds[int(event[0])],int(event[2]))
        assert key in old_events
        maximum_event_difference=max(maximum_event_difference,float(np.max(np.abs(event[6:12]-old_events.pop(key)))))
    assert not old_events and maximum_event_difference<.01
    differences={name:0. for name in ('spot_cash','future_cash','future_unrealized','initial_required','maintenance_headroom','total_equity','open_net','mdd')}
    field_indices=[0,1,2,3,4,5,6,8]
    count=0
    with gzip.open(REFERENCE/'accounts.csv.gz','rt',encoding='utf8',newline='') as stream:
        for row in csv.DictReader(stream):
            phase={'OPEN':0,'CLOSE':1,'SETTLEMENT':2}[row['phase']]
            i=int(row['row'])
            for name,index in zip(differences,field_indices,strict=True):
                differences[name]=max(differences[name],abs(float(row[name])-account[i,phase,index]))
            count+=1
    assert max(differences.values())<.01
    result=json.loads((source/'result.json').read_text())
    diagnosis=dict(status='STOPPED_BY_REQUESTED_ERROR_GATE',failure_stage='CONTROL_REFERENCE_EVENT_SCHEMA_JOIN',
        original_exception="AssertionError: (9808, 'SETTLEMENT', 3)",
        cause='New regression comparator maps event code 5 to SETTLEMENT; existing event kind is SETTLE. Account phase uses SETTLEMENT separately.',
        frozen_engine_or_rule_changed_after_failure=False,control_recomputed_after_failure=False,
        diagnostic_only=True,diagnostic_normalized_label='SETTLE',
        diagnostic_event_cost_pnl_max_difference_krw=maximum_event_difference,
        diagnostic_reference_account_marks=count,diagnostic_account_max_differences_krw=differences,
        diagnostic_all_comparisons_within_one_cent=True,
        simulation_independent_replay_status='PASS',new_conditions_executed=0,
        first_batch_registered_conditions=50,remaining_new_condition_allowance=500,
        next_condition='L17-01-001',worker_lock_absent=not (ROOT/'worker.lock').exists(),
        next_action='Correct SETTLE event adapter in a new code version, preregister that version, and revalidate saved CONTROL without recomputing it before any new condition.')
    write_json(out/'verification.json',diagnosis)
    table(out/'results.csv',[result])
    table(out/'costs.csv',[dict(candidate_id=result['candidate_id'],fees_krw=result['fees_krw'],slippage_krw=result['slippage_krw'],borrow_cost='UNVERIFIED_NOT_INCLUDED',funding='NOT_APPLICABLE',rollover='BOTH_SIDES_INCLUDED')])
    write_json(out/'settings.json',json.loads((ROOT/'preregistration/batch_0001.json').read_text()))
    write_json(out/'environment.json',dict(python='3.12.0',numpy=np.__version__,mode='PAPER_EXPLORATORY_ONLY',storage='D_ONLY',raw_input_status='INPUT_NOT_REMOTELY_REPRODUCIBLE',gateway_or_schedules_changed=False))
    checkpoint=dict(status='STOPPED_CONTROL_VERIFICATION_ERROR',new_conditions_executed=0,control_computed=1,
                    control_initial_runner_regression_pass=False,post_failure_diagnostic_pass=True,
                    next_batch='batch_0001',next_candidate='L17-01-001',final_oos_access=False)
    write_json(out/'checkpoint.json',checkpoint)
    write_json(ROOT/'checkpoint_stopped.json',checkpoint)
    with gzip.open(source/'cycles.csv.gz','rt',encoding='utf8',newline='') as stream:table(out/'control_cycles.csv',list(csv.DictReader(stream)))
    with gzip.open(source/'fills.csv.gz','rt',encoding='utf8',newline='') as stream:table(out/'control_fills.csv',list(csv.DictReader(stream)))
    report=f'''# 일괄 17계약 후속 탐색: 기준 재현 검사에서 중단

신규 조건은 0/500개 실행했습니다. 첫 50조건은 등록·원격 검증됐지만 실행하지 않았습니다.
기준 S1-050-LUMP17만 새 17계약 엔진으로 실제 재현했습니다.
완료 45사이클, 수익률 합계 +{result['score_pct']:.10f}%, 순이익 {result['net_realized']:,.2f}원으로 기존 결과와 일치했습니다.
MDD는 {result['mdd_krw']:,.2f}원, 최소 초기증거금 여유는 {result['minimum_initial_headroom_krw']:,.2f}원입니다.
신규 회귀 검산기의 정산 이벤트 이름 대응 오류로 최초 검사가 실패했습니다.
오류 후 실제 시뮬레이션을 다시 돌리지 않고 저장 원장만 읽어 추가 대조했습니다.
사용자의 오류 발생 시 중단 규칙에 따라 후속 50조건과 나머지 450조건은 실행하지 않았습니다.

|항목|기준 후보 재현|
|---|---:|
|정배 진입|괴리율 -1.0% 하향 통과|
|역배 진입|괴리율 +1.0% 상향 통과|
|청산|진입 신호봉 괴리율 대비 0.5%p 유리하게 회복, 다음 연속 관측 분봉 시가 대용|
|최초 수량|17계약 + 170,000 USDT|
|완료 사이클|45|
|비용 차감 사이클 수익률 합계|+{result['score_pct']:.10f}%|
|실현 순이익|{result['net_realized']:,.2f}원|
|MDD|{result['mdd_krw']:,.2f}원|
|최대 보유 평가손실|{result['maximum_open_loss_krw']:,.2f}원|
|최소 초기증거금 여유|{result['minimum_initial_headroom_krw']:,.2f}원|
|최소 유지증거금 여유|{result['minimum_maintenance_headroom_krw']:,.2f}원|
|필요 현물 조달 관측경로 추정|{result['spot_financing_proxy_krw']:,.2f}원|
|진입 거절 / 관측 유지증거금 부족 / 잔여 계약|0 / 0 / 0|
|정배 / 역배 완료 기여|24 / 21 사이클|
|정배 / 역배 점수 기여|+{result['long_score_pct']:.10f}% / +{result['reverse_score_pct']:.10f}%|

## 실패 원인과 중단 지점

최초 예외: `AssertionError: (9808, 'SETTLEMENT', 3)`.
게시된 실행 코드 runner.py의 이벤트 코드 5 대응표가 `SETTLEMENT`를 사용했지만 기존 이벤트 CSV의 kind는 `SETTLE`입니다. 기존 계좌 CSV의 phase는 별도로 `SETTLEMENT`를 사용합니다. 두 필드의 명칭을 혼동한 검사 코드 오류입니다. 신규 최고를 발견한 것이 아닙니다.

동결 코드와 기존 결과는 변경하지 않았습니다. 오류 후 검사는 `diagnose_stopped_control.py`에서 이미 저장된 원장만 읽었습니다. 정산 이벤트를 기존 스키마의 `SETTLE`로 대조하면 체결·정산·롤오버 비용/손익 최대 차이는 {maximum_event_difference:.12f}원입니다. 기존 전체 {count:,}개 계좌 평가 기록의 최대 차이는 {max(differences.values()):.12f}원으로 0.01원 허용차 내입니다. 별도 독립 검산기는 모든 17계약 주문·현금·비용·평가 원장에 PASS를 기록했습니다. 이 사후 진단을 최초 실행기 검증 성공으로 바꾸어 기록하지 않습니다.

최초 회귀 프로그램이 끝까지 성공하지 못했으므로 신규 배치는 시작하지 않았습니다. 다음 조건은 L17-01-001입니다. 다음 실행에는 대응표 수정의 별도 코드 버전을 사전 게시하고 기존 저장 CONTROL을 재계산 없이 다시 검증해야 합니다. 현 세션에서는 요청하신 중단 규칙을 지켰습니다.

## 자료와 한계

주 점수는 완료 사이클별 비용 차감 순손익/해당 사이클 현물 진입명목 절대값×100의 반올림 전 단순 합계입니다. 계좌 투자수익률이 아닙니다. 현물 조달은 충분하다고 가정하며 역배 차입 가능성·비용은 미검증입니다. 현물 편도 수수료 0.05%, 선물 계약당 편도 600원과 청산율 0.0003157%, 각 레그 편도 2bp 및 롤오버 양쪽 비용을 반영했습니다. 7월6일~8월2일 증거금 일정 추론값, 호가와 분중 평가손실 미관측 한계를 유지합니다.

원본 입력은 승인된 D: 탐색 사본이고 INPUT_NOT_REMOTELY_REPRODUCIBLE입니다. 신규 원시 시세를 업로드하거나 Final OOS를 열지 않았습니다. 전략/원장/코드 버전은 strategy_code_ref.json, 조건은 settings.json, 정지 체크포인트는 checkpoint.json에 있습니다. full_account_ledger.npz는 OPEN/CLOSE/SETTLEMENT의 전체 계좌 원장을 무손실 보관합니다. 바이트·SHA-256 대조 후 게시 검증 상태를 별도 영수증으로 기록합니다.
'''
    (out/'REPORT_KO.md').write_text(report,encoding='utf8')
    manifest(out)
    print(json.dumps(dict(output=str(out),diagnosis=diagnosis),ensure_ascii=False),flush=True)


if __name__=='__main__':main()
