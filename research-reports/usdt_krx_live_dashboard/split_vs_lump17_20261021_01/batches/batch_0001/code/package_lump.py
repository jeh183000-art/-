# /// script
# requires-python = "==3.12.0"
# dependencies = []
# ///
from __future__ import annotations
import csv
import difflib
import hashlib
import json
import platform
import shutil
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PROJECT=ROOT.parents[1]
PAYLOAD=ROOT/'publish'

def main() -> None:
    assert not (ROOT/'worker.lock').exists()
    validation=json.loads((ROOT/'independent_validation.json').read_text())
    atomic=json.loads((ROOT/'atomic_quantity_validation.json').read_text())
    assert validation['status']==atomic['status']=='PASS' and len(validation['cases'])==4
    assert atomic['expected_bundle_contracts']==17 and atomic['expected_bundle_usdt']==170000
    PAYLOAD.mkdir()
    for name in ('settings.json','PREREG_COMPARE_KO.md','results.csv','regression.json','checkpoint.json','independent_validation.json','atomic_quantity_validation.json'):
        shutil.copyfile(ROOT/name,PAYLOAD/name)
    shutil.copytree(ROOT/'code',PAYLOAD/'code')
    shutil.copytree(ROOT/'runs',PAYLOAD/'runs')
    with (ROOT/'results.csv').open(encoding='utf8',newline='') as f:rows=list(csv.DictReader(f))
    actual=[r for r in rows if r['case'] in ('A_SPLIT17','B_LUMP17')]
    for name in ('accounts.py','simulation.py'):
        old=PROJECT/'studies/capital_limit_comparison_20261021_01/code'/name
        new=ROOT/'code'/name
        diff=''.join(difflib.unified_diff(old.read_text(encoding='utf8').splitlines(True),new.read_text(encoding='utf8').splitlines(True),fromfile='prior_comparison/'+name,tofile='corrected_v2/'+name))
        (PAYLOAD/(name+'.diff')).write_text(diff,encoding='utf8')
    settings=json.loads((ROOT/'settings.json').read_text())
    refs={'commit':settings['shared_helper_commit'],'path':settings['shared_helper_remote_path'],
          'sha256':settings['shared_helper_sha256'],'functions_used':['load','table','regression'],'legacy_main_executed':False}
    (PAYLOAD/'shared_code_ref.json').write_text(json.dumps(refs,indent=2),encoding='utf8')
    provenance={'preregistration_commit':settings['preregistration_commit'],'source_sha256':settings['source_sha256'],
        'source_access':'D-only original matched bars; INPUT_NOT_REMOTELY_REPRODUCIBLE','rows':184410,
        'classification':'APPROVED_EXPLORATORY_ONLY','preservation':'Prior results, original inputs, Gateway, scheduled tasks and other Final OOS unchanged',
        'reexecution':'Four full observed-bar passes, including two baseline regressions; B executes actual all-or-none 17-set bundles. No result multiplication substitutes for execution.'}
    (PAYLOAD/'provenance.json').write_text(json.dumps(provenance,indent=2),encoding='utf8')
    environment={'python':platform.python_version(),'platform':platform.platform(),'numpy':'2.2.6','numba':'0.61.2','pandas':'3.0.1',
        'changes':'No runtime install/upgrade. Process TEMP/TMP/cache/cwd on D.',
        'commands':['python -B code/bootstrap.py test_atomic.py','python -B code/bootstrap.py run_lump.py','python -B code/bootstrap.py audit_lump.py'],
        'validation':'4 atomic/quantity/cost/deficit tests passed; six execution modules static no-excuse scan passed. basedpyright not installed; no full strict type-check claim.'}
    (PAYLOAD/'environment.json').write_text(json.dumps(environment,indent=2),encoding='utf8')
    with (PAYLOAD/'costs.csv').open('x',encoding='utf8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['case','fees','slippage','funding','borrow_cost']);w.writeheader()
        for r in actual:w.writerow({'case':r['case'],'fees':r['fees'],'slippage':r['slippage'],'funding':'NOT_APPLICABLE','borrow_cost':'UNVERIFIED_NOT_INCLUDED' if r['case']=='B_LUMP17' else 'NOT_APPLICABLE'})
    with (PAYLOAD/'conditions.csv').open('x',encoding='utf8',newline='') as f:
        w=csv.writer(f);w.writerow(['case','strategy','entry_contracts','entry_usdt','additional_spacing_pp','max_contracts','initial_futures_cash','spot_cap'])
        w.writerow(['A_SPLIT17','U-007206-CAP17',1,10000,.2,17,30000000,'UNBOUNDED_ASSUMED_PROCUREMENT'])
        w.writerow(['B_LUMP17','S1-050-LUMP17',17,170000,'NONE',17,30000000,'UNBOUNDED_ASSUMED_PROCUREMENT'])
    lines=['# 정정 v2: 분할 진입 대 최초 17계약 일괄 진입','','기준 문서는 커밋 1322cbf8e6db0ee97d22f558a694b44df5373bb5입니다. 앞선 1계약 비교는 보존하며 이번 주 비교 결과와 혼합하지 않습니다. 승인 탐색 2026-01-01~10-15 KRX 거래일 및 필요한 야간 경계만 사용했습니다.','','|항목|A 분할 진입|B 17계약 일괄|','|---|---:|---:|']
    a,b=actual
    labels=[('완료 사이클','completed_cycles'),('비용 차감 수익률 단순 합계(%)','score_pct'),('원화 순실현손익','net_realized'),
        ('MDD(원)','mdd'),('최대 평가손실(원)','max_open_evaluation_loss'),('최대 계약수','max_contracts'),
        ('평균 관측 계약수','average_observed_contracts'),('평균 관측 현물 명목','average_observed_spot_notional'),
        ('관측 경로의 필요 현물 조달액(담보 가정 포함)','required_spot_financing_on_observed_path'),
        ('정배 보유의 필요 현물 순조달액','required_long_spot_financing_on_observed_path'),
        ('단일 현물 매수 주문 최대 지출(비용 포함)','max_long_order_spot_outlay'),
        ('초기증거금 여유 최저(원)','minimum_initial_margin_headroom'),('유지증거금 여유 최저(원)','minimum_maintenance_headroom'),
        ('선물계좌 현금 최저(원)','minimum_futures_cash'),('진입 거절 주문','rejected_orders'),('거절 계약','rejected_contracts'),
        ('유지증거금 부족 구간 수','maintenance_deficit_episodes'),('유지증거금 부족 평가 건수','maintenance_deficit_marks'),
        ('미청산 계약','residual_sets'),('미청산 청산비용 차감 평가손익','residual_net_after_close'),('최장 보유(분)','longest_hold_minutes')]
    for label,key in labels:
        values=[f'{float(r[key]):,.6f}' if '.' in r[key] else r[key] for r in (a,b)]
        lines.append('|'+label+'|'+'|'.join(values)+'|')
    accepted=[o for o in atomic['orders'] if o['filled_contracts']]
    lines+=['','## 실제 수량 검증', '',f"B의 최초 주문 {len(atomic['orders'])}건을 검사했습니다. 승인 {len(accepted)}건, 각 승인 최초 수량은 모두17계약·170,000 USDT이며 분할 체결 축소는 없습니다. ENTRY 원장에 계약당1개씩 별도 현금·비용 전기를 기록하고 동일 order_id로17개를 묶었습니다. 원본 가격을 순회하여 직접 체결·정산했으며 기존 원화 결과에17을 곱해 대체하지 않았습니다.", '',
        'A의 각 진입 주문은1계약·10,000 USDT이고 최대17계약입니다. B는 최초17계약을 한 번에 보유하고 청산 전 다른 방향 신규 진입을 하지 않습니다. 1계약은 가능하지만17계약 초기증거금이 부족한 합성 테스트에서 전량 거절·체결0개를 확인했습니다.', '',
        '## 비용·자금·해석', '', '양쪽 선물 초기현금은3,000만원이며 외부 추가입금과 현물에서의 자동이체는 없습니다. 현물은 충분한 조달능력을 가정하고 초기자금 숫자나3,000만원 상한을 정하지 않았습니다. 현물 원장의0은 순현금흐름의 기준점이며 현물0원 제한을 뜻하지 않습니다. 음의 현물 흐름은 필요한 조달액을 나타냅니다.', '',
        '현물 필요 조달액은 이미 실현된 현물계좌 손익을 재사용하는 관측 경로의 최대 순소요액입니다. 단일 매수 주문의 총지출, 정배 순조달액, 최대 현물 명목을 구분했습니다. 역배는170,000 USDT 차입 가용성·비용이 미검증입니다. 매도대금 재사용 제한과 현재 현물 명목100% 담보는 조달액 보고용 가정일 뿐 실제 대차 규정이 아닙니다. B 전체를 차입 미검증 이론값으로 분류합니다.', '',
        '현물 편도0.05%, 선물 계약당 편도600원+명목0.0003157%, 각 레그 편도2bp 슬리피지입니다. 17계약은 수수료·슬리피지·구월물 청산/신월물 진입 비용도17계약분입니다. 실제 개인 계좌 청구 수수료가 아닌 기존 승인 비용 가정입니다. 펀딩은 해당하지 않으며 차입비용은 미검증·미반영입니다.', '',
        '주 점수는 각 완료 사이클 순손익/그 사이클 최초·추가 현물 진입명목 절대값 합계×100의 반올림 전 단순 합계입니다. 초기 투자금이나 증거금으로 분모를 바꾸지 않았습니다. A/B는 진입선·청산선·방향·평균 노출이 달라 추가매수 여부 하나의 인과 효과로 단정할 수 없습니다. 동일 총자본 비교가 아닙니다.', '',
        '## 독립 검증·위험 한계', '', '원래 U-007206 59사이클과1계약 S1-050 45사이클을 먼저 재현해 기존 체결별 비용·가격·손익과 대조했습니다. 이후 A/B 각각 원본 분봉을 다시 순회했습니다. 독립 검산기는 엔진을 import하지 않고 원본 CSV·증거금 일정·주문/전기 원장으로 수량, 원화 현금, 증거금, MDD, 최대 평가손실, 수익률을 재계산했습니다. atomic_quantity_validation.json은 모든 최초17계약 주문의 검사 기록입니다.', '',
        '증권사 반대매매 절차가 미지정이므로 임의 강제청산을 만들지 않습니다. 최초 유지증거금 부족이나 롤오버 초기증거금 부족을 기록하고 이후 경로는 가상 지속으로 분류합니다. 이런 부족이 있으면 이후 수익을 실행가능 성과로 합격 처리하지 않습니다. margin_deficits.csv와 feasibility를 함께 확인해야 합니다.', '',
        '7월6일~8월2일 증거금률은 기존 인접 공식자료 추론값입니다. 현물·선물 모두 다음 연속 관측1분 시가를 체결 대용으로 쓰므로 실제 호가·17계약 체결 가능성은 검증되지 않았습니다. MDD·평가손실은 관측 시가·종가·정산가 기준입니다. 평균 노출은 관측 분봉 종가 표본의 평균이며 미관측 시간은 보간하지 않았습니다. 이번은 독립 Final OOS 성과가 아닌 승인 탐색입니다.', '',
        '## B 통합 실행 원장의 방향별 기여', '', '|방향|완료 사이클|순손익(원)|수익률 합계(%)|','|---|---:|---:|---:|']
    with (ROOT/'runs/B_LUMP17/direction_contribution.csv').open(encoding='utf8',newline='') as f:
        for r in csv.DictReader(f):lines.append(f"|{'정배' if r['direction']=='1' else '역배'}|{r['cycles']}|{float(r['net']):,.2f}|{float(r['score_pct']):.10f}|")
    lines+=['','방향별 수치는 하나의 통합 실행 원장에서 분리했으며 별도 단방향 실험을 합산하지 않았습니다.','','## 보존·재현','','기존 결과와 원본은 수정하지 않았습니다. settings.json에 정정 커밋·실행 전 코드·자료 해시를 고정했습니다. 공통 자료 로더/회귀 대조 함수만 shared_code_ref.json의 기존 버전을 참조하며 이전 비교 main은 호출하지 않았습니다. 원본 시장자료는 D에만 있어 INPUT_NOT_REMOTELY_REPRODUCIBLE입니다. 전체 코드는 code/, 전 체결·현금·증거금·주문·부족 원장은 runs/에 있습니다. A/B 외 새 가설·민감도 스윕·실제 주문은 미실행입니다. 실행 워커는 종료했습니다.']
    (PAYLOAD/'REPORT_KO.md').write_text('\n'.join(lines)+'\n',encoding='utf8')
    roles={'code/accounts.py':'strategy_code','settings.json':'settings','results.csv':'results_csv','costs.csv':'costs','REPORT_KO.md':'statistics_report','environment.json':'environment','runs/B_LUMP17/events.csv':'fills'}
    inventory=[]
    for p in sorted(PAYLOAD.rglob('*')):
        if p.is_file():
            rel=p.relative_to(PAYLOAD).as_posix();inventory.append(dict(path=rel,role=roles.get(rel,'supporting'),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
    with (PAYLOAD/'manifest.csv').open('x',encoding='utf8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['path','role','bytes','sha256']);w.writeheader();w.writerows(inventory)
    print(json.dumps({'files':len(inventory)+1,'bytes':sum(r['bytes'] for r in inventory),'status':'LOCAL_VALIDATED'}))

if __name__=='__main__':main()
