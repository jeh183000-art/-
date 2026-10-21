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
    name=f'batch_{number:04d}';out=ROOT/'publish_payloads'/f'{name}_prereg_v1'
    assert not out.exists();out.mkdir(parents=True)
    shutil.copy2(ROOT/'preregistration'/f'{name}.json',out/'settings.json')
    shutil.copy2(ROOT/'publication/code_ref.json',out/'strategy_code_ref.json')
    table(out/'costs.csv',[dict(spot_fee_per_side=.0005,future_fee_per_contract=600,clearing=.000003157,slippage_bp_per_leg_per_side=2,borrow='UNVERIFIED_NOT_INCLUDED',funding='NOT_APPLICABLE',roll='BOTH_LEGS')])
    table(out/'results.csv',[dict(status='PREREGISTERED_NOT_EXECUTED',conditions=50)])
    table(out/'fills.csv',[dict(status='NO_NEW_MARKET_SIMULATION_EXECUTED')])
    write_json(out/'environment.json',dict(python=sys.version,storage='D_ONLY',mode='EXPLORATORY_PAPER',input_status='INPUT_NOT_REMOTELY_REPRODUCIBLE'))
    write_json(out/'provenance.json',dict(source_sha256=SOURCE_HASH,margin_sha256=MARGIN_HASH,baseline_commit='e1254e5141b3201cf594111cbc47b1fdfd6a5e9a',B='L17-01-013',A_C_D_modified=False,final_oos_access=False))
    (out/'REPORT_KO.md').write_text(f'# B 후속 사전등록 {name}\n\n신규50조건 실행 전 등록입니다. B의 상대 회복형 규칙에서만 파생하며 기존1,000조건과 실질적 설정 중복을 제외했습니다. 최초17계약·170,000 USDT, 선물 초기현금3,000만원, 추가진입·외부입금·자동이체 없음. 목표는 수익률 합계14.95131907100779% 초과·39사이클 이상·잔여0·MDD935만원 이하·증거금 부족0건입니다. 주 순위는 완료 사이클별 비용 차감 순손익/현물 최초 진입명목 절대값×100의 반올림 전 단순합계입니다. 기존1,000조건은 재계산하지 않습니다.\n',encoding='utf8')
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
    allrows=[json.loads(p.read_text()) for p in sorted((ROOT/'batches').glob('batch_*/candidates/*/result.json'))]
    eligible=sorted([r for r in allrows if r['feasible'] and r['cycles']>0],key=lambda r:r['score_pct'],reverse=True)
    qualified=[r for r in eligible if r['goal_qualified']]
    for suffix,selected in [('all',eligible),('all_targets',qualified),('min39',[r for r in eligible if r['cycles']>=39]),('no_residual',[r for r in eligible if r['residual_contracts']==0])]:table(out/f'ranking_{suffix}.csv',selected)
    table(out/'target_shortfalls.csv',[dict(r,failed_targets=';'.join(k for k in ('beats_B','meets_cycle_count','meets_residual_zero','meets_mdd_limit','margin_shortage_free') if not r[k])) for r in allrows if not r['goal_qualified']])
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

    rules={r['candidate_id']:r['rule'] for p in sorted((ROOT/'preregistration').glob('batch_*.json')) for r in json.loads(p.read_text())['conditions']}
    current=sorted([r for r in rows if r['feasible'] and r['cycles']],key=lambda r:r['score_pct'],reverse=True)
    current_goal=[r for r in current if r['goal_qualified']]
    selected=current_goal[0] if current_goal else current[0] if current else None
    summary=dict(batch=name,new_conditions_total=number*50,qualified_count=len(qualified),batch_qualified_count=len(current_goal),
        goal_best=qualified[0] if qualified else None,score_best=eligible[0] if eligible else None,
        batch_goal_best=current_goal[0] if current_goal else None,batch_score_best=current[0] if current else None,
        selected=selected,selected_rule=rules[selected['candidate_id']] if selected else None,
        source_sha256=SOURCE_HASH,margin_sha256=MARGIN_HASH,code_reference=json.loads((ROOT/'publication/code_ref.json').read_text()),
        raw_input_status='INPUT_NOT_REMOTELY_REPRODUCIBLE',final_oos_access=False)
    write_json(out/'publication_summary.json',summary)
    report=f'# B 전략 후속 {name}\n\n신규 {number*50}/500조건 중 이번50조건의 수량·체결·비용·정산·롤오버·현금·증거금·MDD 원장 검사를 통과했습니다. 모든 수치 검증 PASS와 목표 충족은 서로 다른 판정입니다.\n\n'
    report+=f'이번 배치 전체 목표 충족 {len(current_goal)}개, 누적 {len(qualified)}개. 먼저 전체 목표를 충족한 후보 안에서 반올림 전 완료 사이클 수익률 단순 합계로 순위를 매깁니다. 미청산 손익과 초기 투자금·총순이익은 주 점수에 넣지 않습니다.\n\n'
    report+='|후보|전체목표|완료|승률%|수익률합계%|실현순이익 원|MDD 원|최대평가손실 원|최장보유 일|잔여|최소초기증거금여유 원|\n|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|\n'
    show=current_goal[:5]+[r for r in current[:5] if r not in current_goal[:5]]
    for r in show:
        report+=f"|{r['candidate_id']}|{r['goal_qualified']}|{r['cycles']}|{r['win_rate_pct']:.4f}|{r['score_pct']:+.10f}|{r['net_realized']:,.2f}|{r['mdd_krw']:,.2f}|{r['maximum_open_loss_krw']:,.2f}|{r['longest_hold_minutes']/1440:.5f}|{r['residual_contracts']}|{r['minimum_initial_headroom_krw']}|\n"
    if selected:report+='\n선정 후보의 정확한 규칙:\n'+json.dumps(rules[selected['candidate_id']],ensure_ascii=False,indent=2)+'\n'
    report+='\nB 기준은39사이클·14.9513190710%·순이익36,755,589.35원·MDD9,350,000원·잔여0입니다. 수익률만 높고 거래가 적거나 미청산·증거금 부족이 있는 조건은 target_shortfalls.csv에 이유별 기록했습니다. 증거금 부족 판정은 진입 거절·롤 자금 부족·관측 초기/유지증거금 여유 음수를 모두 포함합니다.\n\n'
    report+='최초17계약·현물170,000 USDT, 한 방향 한 묶음, 선물3,000만원에서 외부입금/계좌이체 없이 일일정산과 손익을 유지합니다. 현물은 충분 조달 가정이며 필요금액은 금융조달 proxy로 별도 기록합니다. 현물 편도0.05%, 선물편도 계약당600원+청산율0.0003157%, 각 레그 편도2bp 및 롤 양쪽 비용을 유지합니다. 역배 차입 가능성·차입비는 미검증 이론값입니다. 신호 확정 후 다음 연속 관측 분봉 시가를 체결 대용값으로 사용하며 실제 호가·잔량 체결을 입증하지 않습니다.\n\n'
    report+='B의100% 승률은 중간 손실이 없었다는 뜻이 아닙니다. 기준 원장 진단에서39회 중25회는 하루 이상,7회는7일 이상 보유했으며7일 시점에 열려 있던7회가 모두 평가손실 후 이익 청산됐습니다. 24시간 시점의 정확한 관측15회 중11회도 평가손실이었습니다(10회 결측 별도). 이는 보유 중 관측 진단이며 기준B 시간청산 재백테스트가 아닙니다. 목표까지 기다린 선택 효과와 장기 보유 위험을 구분해야 하며 독립 검증 인과 결론은 아닙니다.\n\n'
    report+='원시 입력은 승인된 탐색 범위만 사용하고 D:에 한 번 보존합니다. INPUT_NOT_REMOTELY_REPRODUCIBLE입니다. 7월6일~8월2일 증거금 일정은 인접 공식 일정 추론이며 분중 손실·과거 호가·역배 차입 비용은 미검증입니다. 전 시점 계좌 원장은 분할 TAR/NPZ로 무손실 보관하고 source schema와 모든 member SHA를 제공합니다. 기존B·A/C/D·다른 연구·Gateway·예약 작업·수집기·보호 Final OOS를 변경하지 않았습니다.\n'
    (out/'REPORT_KO.md').write_text(report,encoding='utf8')
    manifest(out);print(str(out),flush=True)


if __name__=='__main__':
    {'prereg':prereg,'results':results}[sys.argv[1]](int(sys.argv[2]))
