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
    audit=json.loads((ROOT/'independent_validation.json').read_text())
    assert audit['status']=='PASS' and len(audit['cases'])==9
    fill_audit=json.loads((ROOT/'independent_fill_validation.json').read_text())
    assert fill_audit['status']=='PASS' and len(fill_audit['cases'])==9
    PAYLOAD.mkdir()
    with (ROOT/'results.csv').open(encoding='utf8',newline='') as f:rows=list(csv.DictReader(f))
    actual=[r for r in rows if r['scenario']!='REGRESSION']
    for name in ('settings.json','PREREG_COMPARE_KO.md','QUALITY_NOTES.md','results.csv','regression.json','independent_validation.json','independent_fill_validation.json','checkpoint.json','monthly_risk_and_returns.csv','risks.csv','rejection_summary.csv','stress_summary.csv'):
        shutil.copyfile(ROOT/name,PAYLOAD/name)
    shutil.copytree(ROOT/'code',PAYLOAD/'code')
    for scenario in ('A','B'):
        shutil.copytree(ROOT/'runs'/scenario,PAYLOAD/'runs'/scenario)
    source=PROJECT/'shared/approved_20261016_01'
    original=source/'paper_engine.py'
    current=ROOT/'code/simulation.py'
    diff=''.join(difflib.unified_diff(original.read_text(encoding='utf8').splitlines(True),current.read_text(encoding='utf8').splitlines(True),fromfile='original_shared_paper_engine.py',tofile='comparison/code/simulation.py'))
    (PAYLOAD/'engine_change.diff').write_text(diff,encoding='utf8')
    provenance={'preregistration_commit':'3904dcc936d3d11f9010a414b57036649db7ece5','input_storage':'D-only shared approved input; INPUT_NOT_REMOTELY_REPRODUCIBLE','classification':'EXPLORATORY, not independent Final OOS','input_rows':184410,'source_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (source/'matched_simulation_bars.csv',source/'paper_engine.py',source/'margin_schedule.csv')},'reused_originals':'Read-only original prices, loader and margin schedule; no raw price duplication','code_change':'Separate accounting implementation; frozen trade-by-trade regression anchors reconcile. Diff is architectural, not an in-place patch. Admission is performed BEFORE cash mutation; no cross-account transfers; active funding limits and rejection ledger.'}
    (PAYLOAD/'provenance.json').write_text(json.dumps(provenance,indent=2),encoding='utf8')
    environment={'python':platform.python_version(),'platform':platform.platform(),'numpy':'2.2.6','numba':'0.61.2','pandas':'3.0.1','dependencies':'Existing runtime only; no installs or upgrades','temporary_storage':'Process-scoped D runtime only','run':'python -B code/bootstrap.py test_accounts.py; python -B code/bootstrap.py test_forced_paths.py; python -B code/bootstrap.py run_compare.py; python -B code/bootstrap.py audit_compare.py; python -B code/bootstrap.py risk_summary.py','independent_validation':'Separate raw CSV/margin schedule replay with no account or simulation imports; not independent unseen-period validation','tests':'6 admission/settlement tests plus 2 forced maintenance/roll path tests passed'}
    (PAYLOAD/'environment.json').write_text(json.dumps(environment,indent=2),encoding='utf8')
    with (PAYLOAD/'costs.csv').open('x',encoding='utf8',newline='') as f:
        fields=['scenario','strategy','fees','slippage','funding','borrow']
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
        for r in actual:w.writerow({k:r[k] for k in fields[:4]}|{'funding':'NOT_APPLICABLE','borrow':'UNVERIFIED_NOT_INCLUDED' if r['strategy']=='S1-050' else 'NOT_APPLICABLE'})
    lines=['# 동일 자금 제한 A·B 비교 결과','','승인 탐색 자료 2026-01-01~10-15 KRX 거래일 및 필요한 야간 경계만 사용했습니다. 기존 Final OOS와 연구 파일은 변경하지 않았습니다. 실제 주문이 아닌 1분봉 시가 체결 대용 PAPER 실험입니다.','','|시나리오|전략|완료 사이클|수익률 단순 합계|순실현손익|최대 계약|진입 거절|MDD|잔여 순평가|','|---|---|---:|---:|---:|---:|---:|---:|---:|']
    for r in actual:
        lines.append(f"|{r['scenario']}|{r['strategy']}|{r['cycles']}|{float(r['score_pct']):.6f}%|{float(r['net_realized']):,.0f}원|{r['max_sets']}|{r['rejected']}|{float(r['mdd']):,.0f}원|{float(r['residual_net']):,.0f}원|")
    lines+=['','A는 선물 현금3,000만원, 현물은 충분한 가정액2억5,000만원입니다. 실제 사용자 잔액이 아닙니다. B는 양쪽 모두 현물3,000만원+선물3,000만원입니다. U-007206은 최대17계약, S1-050과 S1-037은 최대1세트입니다. A를 총자본 효율의 공정 비교로 해석하지 않습니다.','','## 신호·비용·현금 처리','','U-007206: −0.8% 하향 통과 및 −1.0/−1.2… 단계별0.2%p 추가 진입, −0.5% 이상에서 전량 청산. S1-050: −1.0% 하향/ +1.0% 상향 통과에 정배/역배 한 세트, 신호 대비0.5%p 회복 청산. S1-037: −1.0% 도달 뒤 저점에서0.1%p 반등 확인 후 정배, 확인 신호 대비0.5%p 회복 청산. 모두 종가 신호 다음 연속 관측분 시가 대용입니다.','','현물 편도0.05%, 선물 편도600원+명목금액0.0003157%, 각 레그 편도2bp 슬리피지입니다. 롤오버 구·신월물 양쪽 비용을 차감합니다. 펀딩은 해당하지 않습니다. 수수료는 기존 승인 가정이며 실제 개인 계좌 청구서 검증이 아닙니다.','','현물 원금·비용 검사와 선물 운용현금·초기/유지증거금 검사를 주문 전에 수행했습니다. 정산 손익은 선물 현금에만 반영하며 계좌 간 자동 이체나 추가 입금은 없습니다. 미실현 선물 손익은 증거금 평가에 반영하되 거래비용 지출용 현금은 별도로 검사했습니다.','','역배는 차입 가능성·차입비용 미검증 이론형입니다. 매도대금은 재사용하지 못하도록 제한하고 현재 현물 명목100%의 별도 담보 가정을 적용했습니다. 실제 대차·증권사 담보 규정으로 검증한 것은 아닙니다.','','유지증거금 또는 가정상 현물담보가 부족하면 신규진입을 막고 다음 연속 관측분 시가에 전량 정리하는 연구 규칙입니다. 롤오버 후 신규증거금이 부족하면 새 월물을 열지 않고 구월물과 현물을 정리합니다. 실제 증권사 반대매매 시점·현금 이체 시각은 미검증입니다.7월6일~8월2일 증거금률은 기존 인접 공식자료 추론값을 그대로 사용했습니다.','','## 독립 검증','','무제한 기준 U-007206 59사이클 +13.5278104950%, S1-050 45사이클 +13.1522166079%, S1-037 23사이클 +7.3452526353%를 기존 체결별 가격·순손익·수수료·슬리피지와 대조했습니다. 이후 A/B를 원본 가격으로 각각 재실행했습니다. 요약 금액 비례 환산이 아닙니다.','','독립 검산기는 시뮬레이터를 import하지 않습니다. 원본 CSV 가격·독립적으로 읽은 증거금 일정·체결 및 정산 이벤트로 두 계좌를 재구성하고, 모든 시가·종가·정산 평가의 현금·초기/유지증거금·MDD와 주문 거절 사유를 검산했습니다. 이는 원장 독립 재계산이며 독립 검증기간 성과가 아닙니다.','','## 스트레스와 한계','','각 계약수별 가장 불리한 관측 상태에서 선물만 추가5%·7%·10% 불리하게 움직이고 현물은 그대로인 스트레스를 별도 저장했습니다. 선물계좌 손실과 유지증거금 부족을 평가하며 현물 수익의 자동 이전을 가정하지 않습니다. 9.6%를 안전 청산 한계로 채택하지 않았습니다.','','원화 MDD는 관측 시가·종가·정산가 기준이며 분중 극값이나 미관측 구간 손실을 보장하지 않습니다. 완료 사이클 점수는 순손익/해당 사이클 실제 현물 진입명목 절대값×100의 반올림 전 단순 합계입니다. 계좌 수익률이 아닙니다. 미청산 순평가는 별도입니다.','','## 재현·파일','','settings.json에 실행 전 코드 해시와 정책을 고정했습니다. runs/A 및 runs/B에 전 체결·계좌평가·거절·사이클·잔여·스트레스 CSV를 저장했습니다. 계좌평가는 gzip 무손실 CSV입니다. provenance.json은 원본 해시를 기록합니다. 공유 원본은 D에 보관되어 GitHub만으로 전체 가격 재현은 불가능합니다. 원본을 가진 동일 폴더 배치에서 environment.json의 명령으로 재현할 수 있습니다. 기존 완료 폴더는 덮어쓰지 않습니다.','','A/B와 회귀 대조만 수행하고 종료했습니다. 자금 민감도·추가 전략 스윕·실거래는 수행하지 않았습니다.']
    (PAYLOAD/'REPORT_KO.md').write_text('\n'.join(lines)+'\n',encoding='utf8')
    with (PAYLOAD/'REPORT_KO.md').open('a',encoding='utf8') as f:
        f.write('\n## 비교 결론과 계좌 분리\n\n')
        b=[r for r in actual if r['scenario']=='B']
        winner=max(b,key=lambda r:float(r['score_pct']))
        f.write(f"동일 자금 B의 사전등록 주 점수 최고는 {winner['strategy']} / {float(winner['score_pct']):.10f}%입니다. 원화 순이익 순위와 다를 수 있으며 원화 금액으로 주 순위를 바꾸지 않았습니다. 역배가 포함된 S1-050은 이론형입니다.\n\n")
        f.write('|B 전략|현물계좌 최종현금|선물계좌 최종현금|최장 보유|유지증거금 부족 관측|\n|---|---:|---:|---:|---:|\n')
        for r in b:
            f.write(f"|{r['strategy']}|{float(r['spot_cash_end']):,.2f}원|{float(r['future_cash_end']):,.2f}원|{float(r['longest_hold_minutes'])/1440:.3f}일|{r['breach_marks']}|\n")
        with (ROOT/'rejection_summary.csv').open(encoding='utf8',newline='') as s:
            rejected=list(csv.DictReader(s))
        f.write('\n진입 거절 집계는 조건을 다시 통과한 개별 시도 횟수이며 고유 사이클 수나 미체결 계약 수를 뜻하지 않습니다.\n\n')
        for r in rejected:f.write(f"- {r['scenario']} / {r['strategy']}: {r['reason']} {r['count']}건\n")
        with (ROOT/'stress_summary.csv').open(encoding='utf8',newline='') as s:
            shocks=[r for r in csv.DictReader(s) if r['scenario']=='A' and r['strategy']=='U-007206']
        f.write('\n|A 추가매수 전략 선물 단독 불리한 충격|해당 계약수|충격 후 유지증거금 여유|\n|---|---:|---:|\n')
        for r in shocks:f.write(f"|{float(r['shock_pct']):.0f}%|{r['contracts']}|{float(r['headroom_after_shock']):,.2f}원|\n")
        f.write('\n음수 여유는 이 가정에서 유지증거금 부족을 뜻합니다. 동시 현물 수익을 선물계좌로 자동 이전하지 않았습니다. 월별 평가손익·완료 수익률·MDD는 monthly_risk_and_returns.csv에 KRX 거래월 기준으로 보관했습니다.\n')
    roles={'code/accounts.py':'strategy_code','settings.json':'settings','results.csv':'results_csv','costs.csv':'costs','REPORT_KO.md':'statistics_report','environment.json':'environment','runs/B/U-007206/events.csv':'fills'}
    inventory=[]
    for p in sorted(PAYLOAD.rglob('*')):
        if p.is_file():
            rel=p.relative_to(PAYLOAD).as_posix()
            inventory.append(dict(path=rel,role=roles.get(rel,'supporting'),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
    with (PAYLOAD/'manifest.csv').open('x',encoding='utf8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['path','role','bytes','sha256']);w.writeheader();w.writerows(inventory)
    print(json.dumps({'status':'LOCAL_VALIDATED','files':len(inventory)+1,'bytes':sum(r['bytes'] for r in inventory)}))

if __name__=='__main__':main()
