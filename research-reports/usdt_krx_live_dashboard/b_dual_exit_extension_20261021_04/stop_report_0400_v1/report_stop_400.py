# /// script
# requires-python = "==3.12.0"
# dependencies = ["numpy==2.2.6"]
# ///
# Run: python -B code/bootstrap.py ../operations/report_stop_400.py
import csv,gzip,hashlib,json,shutil
from pathlib import Path
from runner import ROOT,SOURCE_HASH,MARGIN_HASH,canonical,table,write_json
from package_B import manifest
from rules import signature

out=ROOT/'publish_payloads/stop_report_0400_v1';assert not out.exists();out.mkdir(parents=True)
rows=[];audits=[];rules={};seen=set();registry=json.loads((ROOT/'baseline/registry.json').read_text())
for src in registry['previous_rule_sources']:
    p=Path(src['path']);assert hashlib.sha256(p.read_bytes()).hexdigest()==src['sha256'];seen.update(signature(r) for r in json.loads(p.read_text()).values())
for i in range(1,9):
    reg=json.loads((ROOT/'preregistration'/f'batch_{i:04d}.json').read_text())
    assert len(reg['conditions'])==50 and hashlib.sha256(canonical(reg['conditions'])).hexdigest()==reg['grid_sha256']
    assert reg['source_sha256']==SOURCE_HASH and reg['margin_sha256']==MARGIN_HASH
    for f,h in reg['code_sha256'].items():assert hashlib.sha256((ROOT/'code'/f).read_bytes()).hexdigest()==h
    for c in reg['conditions']:
        key=signature(c['rule']);assert key not in seen;seen.add(key);rules[c['candidate_id']]=c['rule']
for p in sorted((ROOT/'batches').glob('batch_*/candidates/*/result.json')):
    r=json.loads(p.read_text());a=json.loads((p.parent/'audit.json').read_text());assert a['status']=='PASS' and a['vector_replay']['cumulative_mdd_nondecreasing']
    with gzip.open(p.parent/'cycles.csv.gz','rt',encoding='utf8',newline='') as stream:cycles=list(csv.DictReader(stream))
    assert len(cycles)==r['cycles'] and all(float(x['contracts'])==17 and float(x['spot_quantity'])==170000 for x in cycles)
    score=sum(float(x['net'])/abs(float(x['spot_entry_notional']))*100 for x in cycles);net=sum(float(x['net']) for x in cycles)
    assert abs(score-r['score_pct'])<1e-9 and abs(net-r['net_realized'])<.01
    gain=sum(max(float(x['net']),0) for x in cycles);loss=-sum(min(float(x['net']),0) for x in cycles)
    if loss:assert r['profit_factor_status']=='FINITE' and abs(gain/loss-r['profit_factor_krw'])<1e-10
    else:assert r['profit_factor_krw'] is None and r['profit_factor_status']==('INFINITE_NO_LOSSES' if gain else 'UNDEFINED_NO_COMPLETED_PNL')
    assert r['rule_sha256']==hashlib.sha256(canonical(rules[r['candidate_id']])).hexdigest()
    rows.append(r);audits.append(dict(candidate_id=r['candidate_id'],audit_status='PASS',evaluation_marks=a['vector_replay']['evaluation_marks'],max_account_error_krw=a['max_account_difference_krw']))
assert len(rows)==400 and len(rules)==400
assert not (ROOT/'preregistration/batch_0009.json').exists() and not (ROOT/'batches/batch_0009').exists()
origin=ROOT.parent/'b_focus_20261021_03/batches/batch_0009/candidates/BF-09-027'
for r in registry['baseline_files']:
    assert hashlib.sha256((ROOT/'baseline/B_original'/r['file']).read_bytes()).hexdigest()==r['sha256']==hashlib.sha256((origin/r['file']).read_bytes()).hexdigest()
receipts=[]
for p in sorted((ROOT/'publication').glob('batch_*_results_verified.json')):
    r=json.loads(p.read_text());assert r['status']=='PUBLISHED_VERIFIED';receipts.append(r)
assert len(receipts) in (7,8)
qualified=[r for r in rows if r['goal_qualified']]
ranked=sorted([r for r in rows if r['feasible'] and r['cycles']],key=lambda r:r['score_pct'],reverse=True)
best=ranked[0]
table(out/'results_calculated_400.csv',rows);write_json(out/'settings_registered_400.json',rules)
table(out/'top20_score.csv',ranked[:20]);table(out/'qualified_candidates.csv',qualified)
table(out/'target_shortfalls.csv',[dict(r,failed_targets=';'.join(k for k in ('beats_B','meets_cycle_count','meets_residual_zero','meets_mdd_limit','margin_shortage_free') if not r[k])) for r in rows if not r['goal_qualified']])
table(out/'validation_400.csv',audits)
table(out/'costs.csv',[{k:r[k] for k in ('candidate_id','fees_krw','slippage_krw','borrow_unverified')} for r in rows])
table(out/'batch_publication_index.csv',[dict(batch=i+1,commit=r['commit'],remote=r['remote'],files=r['files']) for i,r in enumerate(receipts)])
write_json(out/'best_rule_and_result.json',dict(result=best,rule=rules[best['candidate_id']],comparison='TIE_NOT_IMPROVEMENT' if best['numerical_tie_to_B'] else 'EXPLORATORY_ONLY'))
source=next((ROOT/'batches').glob(f'batch_*/candidates/{best["candidate_id"]}'))
for name in ('cycles','fills','orders'):
    with gzip.open(source/f'{name}.csv.gz','rb') as inp,(out/f'{best["candidate_id"]}_{name}.csv').open('xb') as target:shutil.copyfileobj(inp,target)
write_json(out/'settings.json',dict(parent='BF-09-027',planned_conditions=500,calculated_conditions=400,not_executed=100,contracts=17,spot_quantity=170000,futures_initial_cash=30000000,additional_entries=False,external_deposits=False,automatic_transfers=False,score='sum unrounded completed cycle net / abs(initial spot entry notional)*100',stopped_on_publication_error=True,next_unexecuted_batch=9))
shutil.copy2(ROOT/'PUBLICATION_RECOVERY_0008.json',out/'PUBLICATION_RECOVERY_0008.json');shutil.copy2(ROOT/'publication/code_ref.json',out/'strategy_code_ref.json');shutil.copy2(ROOT/'PUBLICATION_ERROR_0008.json',out/'PUBLICATION_ERROR_0008.json')
shutil.copytree(ROOT/'baseline_audit',out/'baseline_audit');shutil.copy2(ROOT/'operations/baseline_exit_rule_diagnostic.json',out/'baseline_exit_rule_diagnostic.json');shutil.copy2(ROOT/'operations/report_stop_400.py',out/'report_stop_400.py')
write_json(out/'environment.json',dict(python='3.12.0',numpy='2.2.6',numba='0.61.2',storage='D_ONLY',environment_changed=False,mode='PAPER_EXPLORATORY',c_free_gib=shutil.disk_usage('C:/').free/1024**3,d_free_gib=shutil.disk_usage('D:/').free/1024**3))
write_json(out/'provenance.json',dict(baseline_commit='c63352755d43b067b2124e748297efe6cbf6ecbf',source_sha256=SOURCE_HASH,margin_sha256=MARGIN_HASH,raw_inputs='INPUT_NOT_REMOTELY_REPRODUCIBLE',final_oos_access=False,prior_1500_recomputed=False,original_baseline_files_preserved=9))
state=dict(status='STOPPED_AFTER_PUBLICATION_ERROR',calculated_conditions=400,locally_audited_conditions=400,published_result_conditions=len(receipts)*50,verified_result_batches=len(receipts),new_qualified_candidates=len(qualified),next_unexecuted_batch=9,remaining_conditions=100,no_worker_running=True,no_new_batches=True,planned_full_500_final_audit_run=False)
write_json(out/'checkpoint.json',state)
write_json(out/'validation_summary.json',dict(status='PASS_RECORDED_400_CONDITION_AND_CSV_AUDITS',conditions=400,registered_rule_duplicates=0,code_drift=False,cycle_net_score_and_pf_reconciled=True,evaluation_marks=sum(a['evaluation_marks'] for a in audits),max_account_difference_krw=max(a['max_account_error_krw'] for a in audits),baseline_unchanged=True,full_500_audit_not_run=True))
report='# B 개선형 추가 연구 — 400조건 중단 보고\n\n'
report+='8배치 결과 업로드 중 GitHub RemoteProtocolError: Server disconnected without sending a response가 발생해 지시대로 신규 연구를 중단했습니다. HTTP상태코드는 커넥터가 제공하지 않았습니다. 수치 검산 오류가 아닌 게시 통신 오류입니다.\n'
report+=f'계산·개별 원장 검산400조건, 원격 게시 검증 {len(receipts)*50}조건입니다. 이미 계산한8배치의 같은 파일 게시만 한 번 재시도했고, 신규9·10배치는 실행·등록하지 않았습니다.\n'
report+=f'목표 전체 충족 신규 후보 {len(qualified)}개. 최고 {best["candidate_id"]}는 {best["score_pct"]:+.10f}%로 기준 BF-09-027과 동점이며 개선 성공으로 집계하지 않습니다.\n'
report+='500조건 전체 연구 완료나 독립 검증 성과로 보고하지 않습니다. 남은100조건은 미실행입니다.\n\n'
report+='|구분|후보|완료|승률%|수익률합계%|순이익 원|PF|MDD 원|잔여|\n|---|---|---:|---:|---:|---:|---|---:|---:|\n'
report+=f'|신규 최고(동점)|{best["candidate_id"]}|{best["cycles"]}|{best["win_rate_pct"]:.2f}|{best["score_pct"]:+.10f}|{best["net_realized"]:,.2f}|∞|{best["mdd_krw"]:,.2f}|{best["residual_contracts"]}|\n'
report+='\n최고 규칙은 정배−0.97%/역배+0.85% 돌파 진입, 신호봉 대비0.6%p 회복 OR 비용차감 평가수익률0.55% 익절입니다. 기준0.7%를 바꿨으나 이 표본의 실현 성과는 같았습니다. 모든미달·잔여·저거래수·장기보유·증거금 부족 결과는 원장과 CSV로 남겼습니다.\n\n'
report+='8배치 최고 BD-08-035는 같은 기준 진입/청산에4320분 회복정체 청산을 추가했습니다. 54회·승률79.6296%·점수10.6457069510%·순이익26,189,600.96원·PF2.72011940·MDD5,593,000원·최대평가손실4,689,288.38원·최장9.22639일·잔여0·최소초기증거금여유16,417,657.17원입니다. 위험은 줄었지만 목표 수익률은 미달입니다.\n\n'
report+='원장검산은 두 구현의 체결·정산·롤오버·현금·증거금·MDD 대조입니다. 이번 중단 보고는 저장된400조건 CSV의 사이클수·17계약/170000 USDT·순손익·점수·PF 및 등록코드/입력해시·중복0을 다시 대조했습니다. 예정한500조건 전체 최종감사는 실행하지 않았습니다. 기존B 원본9파일은 SHA로 보존을 재확인했습니다.\n\n'
report+='총자본 수익률이 아닌 완료사이클별 비용차감 순손익/현물최초진입명목 절대값×100의 반올림 전 합계로 순위를 유지했습니다. PF는 완료사이클 원화이익합/손실합 절대값이며∞는 무위험을 뜻하지 않습니다. 신호후 다음 연속 관측1분봉 시가는 체결대용값이며 실제17계약 호가체결·역배차입 가능성과 비용은 미검증입니다. 증거금일정7월6일~8월2일 추론·분중미관측 한계를 유지합니다.\n\n'
report+='기준42사이클은 모두 괴리회복 조건을 충족했고 순손익0.7%는1회 같은 봉에서 동시충족했으며 단독청산은0회였습니다. 42회 중26회는 하루 이상·6회는7일 이상 보유했습니다. 긴 보유와 중간 평가손실을 완전익절의 높은 승률과 구분해야 합니다.\n\n'
report+='계산·결과·체크포인트는 D:에 보존했습니다. 기존 A/B/C/D·BF-09-027·시장원본·Final OOS·Gateway·OpenClaw·예약작업·다른 연구/수집기는 변경하지 않았습니다. 새 연구 워커는 종료했습니다. 전체 원장은 batch_publication_index.csv의 검증된 각 배치 분할TAR에 있으며8배치 게시가 미검증이면 그 원본은 D:의 batches/batch_0008 및 publish_payloads/batch_0008_results_v1에 있습니다. 원시시장자료는D:전용 INPUT_NOT_REMOTELY_REPRODUCIBLE입니다.\n'
(out/'REPORT_KO.md').write_text(report,encoding='utf8');manifest(out)
print(json.dumps(dict(output=str(out),state=state,best=best)),flush=True)
