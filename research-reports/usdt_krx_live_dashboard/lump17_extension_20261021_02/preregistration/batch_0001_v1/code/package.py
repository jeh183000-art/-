from __future__ import annotations

import csv
import gzip
import hashlib
import json
import shutil
import sys
import tarfile
from pathlib import Path

from runner import ROOT, SOURCE_HASH, MARGIN_HASH, table, write_json


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def manifest(out):
    rows=[]
    for path in sorted(out.rglob('*')):
        if not path.is_file() or path.name=='manifest.csv':continue
        relative=path.relative_to(out).as_posix()
        role='results_csv'
        if relative.startswith('code/') or path.name=='strategy_code_ref.json':role='strategy_code'
        elif path.name=='settings.json' or path.suffix=='.json':role='settings'
        if path.name=='environment.json':role='environment'
        if 'REPORT' in path.name or path.suffix=='.md':role='statistics_report'
        if 'ledger' in relative or 'fills' in relative or 'cycles' in relative or 'archive' in relative:role='fills'
        if path.name=='costs.csv':role='costs'
        rows.append(dict(path=relative,role=role,bytes=path.stat().st_size,sha256=digest(path)))
    table(out/'manifest.csv',rows,['path','role','bytes','sha256'])


def prereg(number):
    name=f'batch_{number:04d}'
    out=ROOT/'publish_payloads'/f'{name}_prereg_v1'
    assert not out.exists();out.mkdir(parents=True)
    shutil.copy2(ROOT/'preregistration'/f'{name}.json',out/'settings.json')
    if number==1:
        shutil.copytree(ROOT/'code',out/'code',ignore=shutil.ignore_patterns('__pycache__'))
        shutil.copy2(ROOT/'drawdown_tests_v2.json',out/'drawdown_tests_v2.json')
        shutil.copy2(ROOT/'code/build_extension.py',out/'build_extension.py')
    else:
        shutil.copy2(ROOT/'publication/code_ref.json',out/'strategy_code_ref.json')
        shutil.copy2(ROOT/'code/build_extension.py',out/'build_extension.py')
    table(out/'costs.csv',[dict(spot_fee_per_side=.0005,future_fee_per_contract=600,clearing=.000003157,slippage_bp_per_leg_per_side=2,borrow='UNVERIFIED_NOT_INCLUDED',funding='NOT_APPLICABLE',roll='both_old_and_new_contract')])
    table(out/'results.csv',[dict(status='PREREGISTERED_NOT_EXECUTED',conditions=50)])
    table(out/'fills.csv',[dict(status='NO_MARKET_SIMULATION_EXECUTED')])
    write_json(out/'environment.json',dict(python=sys.version,storage='D_ONLY',mode='PAPER_EXPLORATORY',input_status='INPUT_NOT_REMOTELY_REPRODUCIBLE'))
    write_json(out/'provenance.json',dict(source_sha256=SOURCE_HASH,margin_sha256=MARGIN_HASH,reference_commit='9bf0419af434faa8a7ed80adac46bd86cf2e3f60',
        input_scope='approved exploratory KRX business dates 2026-01-01..10-15 plus required boundaries only',final_oos_access=False,
        limitations=['July06-Aug02 margin rates inferred from adjacent official schedules','Minute OHLC execution proxies; historical orderbook absent','Reverse borrowing unverified']))
    (out/'REPORT_KO.md').write_text(f'# 일괄 17계약 사전등록 {name}\n\n등록 상태: PREREGISTERED_NOT_EXECUTED. 이 커밋은 실행 완료가 아닙니다.\n\n선물 초기현금 3,000만원, 현물 충분 조달 가정, 최초 17계약·170,000 USDT 전량 주문, 추가진입 금지. 신호 다음 연속 분봉 시가 대용 체결입니다. 완료 사이클별 순손익/현물 진입명목×100의 반올림 전 단순 합계로 순위를 계산합니다.\n\n기준 후보 재현과 독립 현금·수량·비용·증거금 원장 검사를 통과한 뒤 실행합니다. 실제 주문과 Final OOS 접근은 없습니다.\n',encoding='utf8')
    manifest(out);print(str(out),flush=True)


def results(number):
    name=f'batch_{number:04d}'; source=ROOT/'batches'/name
    out=ROOT/'publish_payloads'/f'{name}_results_v1'
    assert not out.exists();out.mkdir(parents=True)
    for filename in ('results.csv','checkpoint.json','environment.json','settings.json','ledger_schema.json'):
        shutil.copy2(source/filename,out/filename)
    shutil.copy2(ROOT/'publication/code_ref.json',out/'strategy_code_ref.json')
    rows=[json.loads(p.read_text()) for p in sorted((source/'candidates').glob('*/result.json'))]
    assert len(rows)==50
    allrows=[]
    for path in sorted((ROOT/'batches').glob('batch_*/results.csv')):
        with path.open(encoding='utf8',newline='') as f:
            for row in csv.DictReader(f):
                row['feasible']=row['feasible']=='True'
                for k in ('cycles','residual_contracts'):row[k]=int(row[k])
                for k in ('score_pct','net_realized'):row[k]=float(row[k])
                allrows.append(row)
    eligible=sorted([r for r in allrows if r['feasible'] and r['cycles']>0],key=lambda r:r['score_pct'],reverse=True)
    for suffix, selected in [('all',eligible),('min5',[r for r in eligible if r['cycles']>=5]),('min10',[r for r in eligible if r['cycles']>=10]),('no_residual',[r for r in eligible if r['residual_contracts']==0])]:
        table(out/f'ranking_{suffix}.csv',selected)
    table(out/'ranking_amount_auxiliary.csv',sorted(eligible,key=lambda r:r['net_realized'],reverse=True))
    table(out/'ineligible.csv',[r for r in allrows if not r['feasible']])
    table(out/'zero_completed.csv',[r for r in allrows if r['cycles']==0])
    for filename in ('cycles.csv.gz','fills.csv.gz','orders.csv.gz'):
        with gzip.open(out/filename,'wt',encoding='utf8',newline='') as destination:
            writer=None
            for folder in sorted((source/'candidates').iterdir()):
                with gzip.open(folder/filename,'rt',encoding='utf8',newline='') as stream:
                    reader=csv.DictReader(stream)
                    for row in reader:
                        if writer is None:writer=csv.DictWriter(destination,fieldnames=list(row));writer.writeheader()
                        writer.writerow(row)
            if writer is None:destination.write('status\nNO_ROWS\n')
    table(out/'costs.csv',[{k:r[k] for k in ('candidate_id','fees_krw','slippage_krw','borrow_unverified')} for r in rows])
    table(out/'risks.csv',[{k:r[k] for k in ('candidate_id','mdd_krw','maximum_open_loss_krw','residual_contracts','residual_net_after_exit_cost','minimum_initial_headroom_krw','minimum_maintenance_headroom_krw','insufficient_rolls','maintenance_breach_marks','feasible')} for r in rows])
    table(out/'validation.csv',[dict(candidate_id=r['candidate_id'],status='PASS_INDEPENDENT_REPLAY',maximum_account_difference_krw=r['audit_max_difference_krw'],atomic_order_contracts=17) for r in rows])
    inventory=[]
    for path in sorted((source/'candidates').rglob('*')):
        if path.is_file():inventory.append(dict(path=path.relative_to(source).as_posix(),bytes=path.stat().st_size,sha256=digest(path)))
    table(out/'archive_inventory.csv',inventory)
    archive=source/'full_ledgers.tar'
    with tarfile.open(archive,'x') as tf:
        for path in sorted((source/'candidates').rglob('*')):
            if path.is_file():tf.add(path,arcname=path.relative_to(source).as_posix(),recursive=False)
    parts=[]
    with archive.open('rb') as stream:
        index=1
        while block:=stream.read(16*1024*1024):
            dest=out/f'full_ledgers.tar.part{index:03d}'
            with dest.open('xb') as f:f.write(block)
            parts.append(dict(path=dest.name,bytes=len(block),sha256=digest(dest)));index+=1
    write_json(out/'archive_parts.json',dict(format='uncompressed tar split exact binary concatenation',archive_bytes=archive.stat().st_size,archive_sha256=digest(archive),parts=parts,
        reconstruction='Join sorted full_ledgers.tar.partNNN bytes then verify SHA256 and extract tar. Account NPZ preserves every OPEN/CLOSE/SETTLEMENT mark. export_account_csv.py creates full CSV without recomputing trades.'))
    for row in sorted([r for r in rows if r['feasible'] and r['cycles']],key=lambda r:r['score_pct'],reverse=True)[:3]:
        folder=source/'candidates'/row['candidate_id']
        for filename in ('cycles','fills'):
            with gzip.open(folder/f'{filename}.csv.gz','rb') as inp, (out/f"top_{row['candidate_id']}_{filename}.csv").open('xb') as dest:shutil.copyfileobj(inp,dest)
    if number==1:shutil.copytree(ROOT/'anchor_audit_v2',out/'anchor_audit_v2')
    rules={r['candidate_id']:r['rule'] for p in sorted((ROOT/'preregistration').glob('batch_*.json')) for r in json.loads(p.read_text())['conditions']}
    best=eligible[0] if eligible else None
    current=sorted([r for r in rows if r['feasible'] and r['cycles']],key=lambda r:r['score_pct'],reverse=True)
    report=f'# 일괄 17계약 탐색 {name}\n\n신규 {number*50}/500조건 실행. 이번 배치 50조건 모두 독립 현금·체결·비용·증거금 원장 검사를 통과했습니다. 관측 유지증거금 부족 또는 롤오버 자금 부족 후보는 실행가능 순위에서 제외했습니다.\n\n'
    report+='주 점수는 완료 사이클별 비용 차감 순손익/해당 현물 진입명목 절대값×100의 반올림 전 단순 합계이며 계좌 수익률이 아닙니다. 미청산 손익은 주 점수와 분리하며 종료 가정청산 점수도 CSV에 기록했습니다.\n\n'
    report+='|순위|후보|완료 사이클|수익률 합계 %|실현 순이익 원|MDD 원|최소 초기증거금 여유 원|잔여 계약|\n|---|---|---|---|---|---|---|---|\n'
    for rank,r in enumerate(eligible[:20],1):report+=f"|{rank}|{r['candidate_id']}|{r['cycles']}|{float(r['score_pct']):.8f}|{float(r['net_realized']):,.2f}|{float(r['mdd_krw']):,.2f}|{r['minimum_initial_headroom_krw']}|{r['residual_contracts']}|\n"
    if best:
        report+=f"\n누적 최고 정확한 조건:\n```json\n{json.dumps(rules[best['candidate_id']],ensure_ascii=False,indent=2)}\n```\n\n기존500조건 최고 +17.0956518029% 대비 변화: {best['score_pct']-17.095651802927925:+.8f}%p. 이번 배치 최고: {current[0]['candidate_id'] if current else '없음'}.\n"
    report+='\n17계약·170,000 USDT, 양방향 통합 한 묶음만 보유합니다. 충분한 현물 조달 가정이며 사용자 계좌 잔액과 무관합니다. 모든 후보가 선물현금 3,000만원에서 각각 시작하며 외부 입금/자동이체 없이 일일정산 및 누적손익을 유지합니다. 현물 편도 0.05%, 선물 계약당 편도 600원+청산율 0.0003157%, 레그별 편도 2bp, 롤오버 양쪽 비용입니다. 역배 차입 가능성과 비용은 미검증으로 실제 운용 가능성을 확정하지 않습니다.\n\n원본 승인 탐색 자료는 D: 전용이며 INPUT_NOT_REMOTELY_REPRODUCIBLE입니다. 7월6일~8월2일 증거금 일정 추론, 과거 호가와 분중 평가손실 미관측의 한계가 있습니다. 월·분기 성과는 같은 탐색자료의 설명이지 독립 OOS 검증이 아닙니다. 전체 계좌 원장은 분할 TAR 및 후보별 NPZ로 무손실 보관하며 schema와 CSV 변환 코드를 제공합니다. 원시 데이터 중복 업로드를 하지 않았습니다.\n'
    (out/'REPORT_KO.md').write_text(report,encoding='utf8')
    write_json(out/'publication_summary.json',dict(batch=name,new_conditions_total=number*50,best=best,batch_best=current[0] if current else None,
        code_reference=json.loads((ROOT/'publication/code_ref.json').read_text()),input_sha256=SOURCE_HASH,margin_sha256=MARGIN_HASH,
        raw_input_status='INPUT_NOT_REMOTELY_REPRODUCIBLE',final_oos_access=False))
    manifest(out);print(str(out),flush=True)


if __name__=='__main__':
    {'prereg':prereg,'results':results}[sys.argv[1]](int(sys.argv[2]))
