# /// script
# requires-python = "==3.12.0"
# dependencies = ["numpy==2.2.6"]
# ///
# Run with code/bootstrap.py in this frozen research runtime.
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
    write_json(out/'provenance.json',dict(source_sha256=SOURCE_HASH,margin_sha256=MARGIN_HASH,baseline_commit='c63352755d43b067b2124e748297efe6cbf6ecbf',B='BF-09-027',A_C_D_modified=False,final_oos_access=False))
    (out/'REPORT_KO.md').write_text(f'# B 개선형 추가 사전등록 {name}\n\nBF-09-027을 보존한 신규50조건입니다. 최초17계약·170,000 USDT, 선물3,000만원, 추가진입·외부입금·계좌자동이체 없음. 초기2배치는 회복0.6%p OR 비용차감 평가수익0.7%를 유지하고 진입선만 비교합니다. 이후 회복폭·순손익 익절·비대칭·반전·위험 가설을 단계적으로 비교합니다. 기존1,500조건 및 앞서 등록한 신규조건과 중복을 제외합니다. 목표는 점수16.7054302006977% 초과·완료42회 이상·잔여0·MDD935만원 이하·증거금 부족/진입거절0입니다. 입력·코드 SHA는 settings.json에 있습니다. PF는 비용차감 완료사이클 원화 이익합/손실합 절대값이며 무손실 표본은 무한대로 구분합니다. 탐색용으로 독립 검증 성과가 아닙니다.\n',encoding='utf8')
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
    for suffix,selected in [('all',eligible),('all_targets',qualified),('min42',[r for r in eligible if r['cycles']>=42]),('no_residual',[r for r in eligible if r['residual_contracts']==0])]:table(out/f'ranking_{suffix}.csv',selected)
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
        raw_input_status='INPUT_NOT_REMOTELY_REPRODUCIBLE',final_oos_access=False,c_free_gib=shutil.disk_usage('C:/').free/1024**3,d_free_gib=shutil.disk_usage('D:/').free/1024**3)
    write_json(out/'publication_summary.json',summary)
    table(out/'risk_classification.csv',[dict(candidate_id=r['candidate_id'],low_cycle_count=r['low_cycle_count'],long_holding_risk=r['long_holding_risk'],longer_than_baseline=r['longer_than_baseline'],open_loss_hidden_risk=r['open_loss_hidden_risk'],residual_net_after_exit_cost=r['residual_net_after_exit_cost'],forced_terminal_score_pct=r['forced_terminal_score_pct'],margin_shortage_free=r['margin_shortage_free']) for r in allrows])
    report=f'# B 개선형 추가 연구 {name}\n\n신규 {number*50}/500조건, 이번50조건의 체결·PF·정산·롤오버·현금·증거금·누적MDD 독립 검산을 통과했습니다.\n\n'
    report+=f'이번 전체목표 충족 {len(current_goal)}개, 누적 {len(qualified)}개. 목표 통과 후보를 우선 비교하며 주 점수는 완료사이클별 비용차감 순손익/최초 현물 진입명목 절대값×100의 반올림 전 단순합계입니다. 미청산 손익은 주 점수에서 제외합니다.\n\n'
    report+='|후보|전체목표|완료|승률%|수익률합계%|순이익 원|PF|MDD 원|최대평가손실 원|최장보유 일|잔여|최소초기증거금여유 원|\n|---|---|---:|---:|---:|---:|---|---:|---:|---:|---:|---:|\n'
    show=current_goal[:5]+[r for r in current[:5] if r not in current_goal[:5]]
    for r in show:
        pf=f"{r['profit_factor_krw']:.4f}" if r['profit_factor_krw'] is not None else '∞' if r['profit_factor_status']=='INFINITE_NO_LOSSES' else '산출불가'
        report+=f"|{r['candidate_id']}|{r['goal_qualified']}|{r['cycles']}|{r['win_rate_pct']:.4f}|{r['score_pct']:+.10f}|{r['net_realized']:,.2f}|{pf}|{r['mdd_krw']:,.2f}|{r['maximum_open_loss_krw']:,.2f}|{r['longest_hold_minutes']/1440:.5f}|{r['residual_contracts']}|{r['minimum_initial_headroom_krw']}|\n"
    if selected:report+='\n선정 후보의 정확한 규칙:\n'+json.dumps(rules[selected['candidate_id']],ensure_ascii=False,indent=2)+'\n'
    report+='\nBF-09-027 기준:42사이클·16.7054302006977%·순이익41,295,918.91원·MDD935만원·잔여0. 이보다 점수가 높아도 거래42회 미만, 잔여, 증거금 부족/거절 또는 MDD초과가 있으면 target_shortfalls.csv로 분리합니다. PF는 비용차감 완료사이클 원화 이익합/손실합 절대값이며 손실0 표본의∞는 위험0을 뜻하지 않습니다.\n\n'
    report+='최초17계약·170,000 USDT, 한 방향 한 묶음, 추가진입 없음. 선물초기현금3,000만원에서 외부입금·자동이체 없이 손익과 정산을 처리합니다. 현물 충분조달 가정이며 필요액은 별도 보고합니다. 현물편도0.05%, 선물 계약당편도600원+청산율0.0003157%, 각레그편도2bp와 롤양쪽 비용을 유지합니다. 역배는 차입 가능성·차입비용 미검증 이론값입니다. 신호 후 다음 연속 관측분봉 시가를 체결대용값으로 쓰며 실제 호가/17계약 체결을 입증하지 않습니다.\n\n'
    diagnostic=json.loads((ROOT/'baseline_audit/validation.json').read_text());seven=next(x for x in diagnostic['horizons'] if x['horizon_minutes']==10080)
    report+=f"기준 전략은42회 중 {diagnostic['over_1day']}회가 하루 이상, {diagnostic['over_7days']}회가7일 이상 보유했습니다. 정확한7일 관측에서 열린 {seven['observed_still_open']}회 중 {seven['negative_marks']}회가 평가손실이었습니다. 최장 {diagnostic['longest_hold_minutes']/1440:.5f}일이며, 높은 승률을 장기 보유/회복 선택효과와 구분해야 합니다. 이는 저장원장 진단이며 기존 전략을 시간청산으로 재백테스트한 값이 아닙니다. risk_classification.csv에7일초과·기준보다긴보유·저거래수·잔여 위험을 별도 표시했습니다.\n\n"
    report+='원시는 승인된 탐색자료 D:공통 입력을 사용하며 INPUT_NOT_REMOTELY_REPRODUCIBLE입니다. 7월6일~8월2일 증거금 일정은 인접 공식 일정 추론, 분중 손실과 과거 호가 미관측, 역배 차입 미검증 한계가 있습니다. 체결·정산·롤오버·계좌 전시점 원장을 무손실 분할TAR로 보존하고 member SHA 및NPZ CRC를 검사합니다. 기존 A/B/C/D·BF-09-027·Final OOS·Gateway·OpenClaw·예약작업·다른 수집기는 변경하지 않았습니다.\n'
    report+=f"\nD: 작업폴더 {ROOT}; 저장공간 C:{summary['c_free_gib']:.2f}GiB, D:{summary['d_free_gib']:.2f}GiB. 이번 배치 원격검증 완료 전에는 다음 배치를 시작하지 않습니다.\n"
    (out/'REPORT_KO.md').write_text(report,encoding='utf8')
    manifest(out);print(str(out),flush=True)


if __name__=='__main__':
    {'prereg':prereg,'results':results}[sys.argv[1]](int(sys.argv[2]))
