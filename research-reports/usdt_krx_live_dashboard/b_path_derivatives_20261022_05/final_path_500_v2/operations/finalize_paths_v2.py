# /// script
# requires-python = "==3.12.0"
# dependencies = []
# ///
# Assemble only saved/audited 500-condition results and references.
from __future__ import annotations
import csv,gzip,json,shutil,sys
from collections import defaultdict
from runner import ROOT,SOURCE_HASH,MARGIN_HASH,table,write_json
from package_B import manifest
rules={c['candidate_id']:c['rule'] for c in json.loads((ROOT/'all_500_preregistration.json').read_text())['conditions']}
paths={p.parent.name:p.parent for p in (ROOT/'batches').glob('batch_*/candidates/*/result.json')}
rows=[json.loads((p/'result.json').read_text()) for p in paths.values()]
assert len(rows)==len(rules)==500
for folder in ('actual_mdd_audit','registration_audit','metrics_audit','diagnostics_v2'):
    assert json.loads((ROOT/folder/'validation.json').read_text())['status'].startswith('PASS')
out=ROOT/'publish_payloads/final_path_500_v2'
out.mkdir(parents=True)
eligible=sorted([r for r in rows if r['feasible'] and r['cycles']],key=lambda r:(-r['score_pct'],r['candidate_id']))
rank={r['candidate_id']:i+1 for i,r in enumerate(eligible)}
allranked=sorted(rows,key=lambda r:(not bool(r['cycles']),-r['score_pct'],r['candidate_id']))
table(out/'ranking_all_500.csv',[dict(rank_eligible=rank.get(r['candidate_id']),**r) for r in allranked])
table(out/'results_new_500.csv',rows)
write_json(out/'settings_new_500.json',rules)
table(out/'target_shortfalls.csv',[dict(r,failed_targets=';'.join(k for k in ('beats_B','meets_cycle_count','meets_residual_zero','meets_mdd_limit','margin_shortage_free') if not r[k])) for r in rows if not r['goal_qualified']])
groups={'score_only':eligible,'all_targets':[r for r in eligible if r['goal_qualified']],
        'min42':[r for r in eligible if r['cycles']>=42],'no_residual':[r for r in eligible if not r['residual_contracts']],
        'margin_shortage_free':[r for r in eligible if r['margin_shortage_free']],
        'risk_reduction':[r for r in eligible if r['margin_shortage_free'] and (r['mdd_krw']<9350000-.01 or r['longest_hold_minutes']<41887)]}
groups['risk_reduction_min42_no_residual']=[r for r in groups['risk_reduction'] if r['cycles']>=42 and not r['residual_contracts']]
leaders={}
for key,group in groups.items():
    table(out/f'top20_{key}.csv',group[:20])
    if group:leaders[key]=dict(result=group[0],rule=rules[group[0]['candidate_id']])
for name,items in [('zero_completed',[r for r in rows if not r['cycles']]),('ineligible',[r for r in rows if not r['feasible']]),('open_residuals',[r for r in rows if r['residual_contracts']])]:
    table(out/f'{name}.csv',items)
write_json(out/'best_rules_and_results.json',leaders)
for folder in ('actual_mdd_audit','registration_audit','metrics_audit','diagnostics_v2','baseline_audit'):
    shutil.copytree(ROOT/folder,out/('diagnostics' if folder=='diagnostics_v2' else folder))
for file in ('registry_sources.csv','registry_summary.json','reuse_rules.csv','all_500_preregistration.json',
             'external_dependencies.json','metric_tests.json','path_metric_tests.json','path_tests_v2.json','drawdown_tests_v2.json'):
    shutil.copy2(ROOT/file,out/file)
shutil.copy2(ROOT/'publication/code_ref.json',out/'strategy_code_ref.json')
shutil.copy2(ROOT/'control_regression/validation.json',out/'control_regression_validation.json')
shutil.copytree(ROOT/'operations',out/'operations',ignore=shutil.ignore_patterns('__pycache__'))
for cid in {x['result']['candidate_id'] for x in leaders.values()}:
    for name in ('cycles','fills','orders'):
        with gzip.open(paths[cid]/f'{name}.csv.gz','rb') as source,(out/f'{cid}_{name}.csv').open('xb') as target:
            shutil.copyfileobj(source,target)
    shutil.copy2(paths[cid]/'exit_attribution.csv',out/f'{cid}_exit_attribution.csv')
    shutil.copy2(paths[cid]/'period_contribution.csv',out/f'{cid}_period_contribution.csv')
receipts=[json.loads((ROOT/'publication'/f'batch_{n:04d}_results_verified.json').read_text()) for n in range(1,11)]
assert all(r['status']=='PUBLISHED_VERIFIED' for r in receipts)
table(out/'batch_publication_index.csv',[dict(batch=i+1,**r) for i,r in enumerate(receipts)])
audits=[dict(candidate_id=p.name,**json.loads((p/'audit.json').read_text())) for p in paths.values()]
assert all(r['status']=='PASS' for r in audits)
write_json(out/'validation_all_500.json',dict(status='PASS',conditions=500,
    financial_replay=True,independent_vector_replay=True,independent_entry_gates=True,strict_exit_cause_diagnostics=True,
    max_account_error_krw=max(r['max_account_difference_krw'] for r in audits),exact_baseline_control=True))
table(out/'costs.csv',[{k:r[k] for k in ('candidate_id','fees_krw','slippage_krw','borrow_unverified')} for r in rows])
write_json(out/'settings.json',dict(parent='BF-09-027',baseline_profit_target_pct=.7,contracts=17,spot_quantity=170000,
    futures_initial_cash=30000000,additional_entries=False,new_conditions=500,score_tolerance_pp=1e-8,
    score='sum unrounded completed cost-net cycle returns',unfinished_excluded_from_primary_score=True))
write_json(out/'environment.json',dict(python=sys.version,numpy='2.2.6',numba='0.61.2',pandas='3.0.1',changed=False,storage='D_ONLY'))
write_json(out/'provenance.json',dict(source_sha256=SOURCE_HASH,margin_sha256=MARGIN_HASH,
    baseline_commit='c63352755d43b067b2124e748297efe6cbf6ecbf',prior_commit='8a33d1d495ddcb8b3ce0c3b13e2bf31abfd95c43',
    scope='Approved exploratory KRX business dates2026-01-01..10-15 plus necessary night boundaries',
    raw_input_status='INPUT_NOT_REMOTELY_REPRODUCIBLE',final_oos_access=False,
    gateway_openclaw_schedules_or_other_collectors_changed=False,control_runs_not_new=1))
report='# B 개선형 경로 파생500조건 최종 결과\n\n'
report+='기존 B의 −0.97%/+0.85% 진입, 신호봉 대비0.6%p 회복 또는 순손익0.7% 익절은 그대로 보존했습니다.\n'
report+='기준 CONTROL만 한 번 실행했고 체결·비용·현금·증거금·평가곡선 등8개 배열이 원본과 정확히 같았습니다.\n'
report+='다섯 방향을100조건씩, 전체500조건과 코드 해시를 먼저 등록하고50조건씩 실행했습니다.\n'
report+=f'완료500조건 중 우선 합격 {len(groups["all_targets"])}개, 기존B 점수보다1e-8%p 이상 높은 후보 {sum(r["beats_B"] for r in rows)}개입니다.\n'
report+='주 점수는 각 완료사이클의 비용차감 수익률을 반올림 전에 단순합산했으며 미청산 손익은 분리했습니다.\n'
report+='같은 체결·계좌 경로는 묶고, 월별 성과·인접조건·상위 거래 집중도·청산 단독/동시 발동을 따로 검증했습니다.\n'
report+='탐색자료 내 결과이며 역배 차입과 실제17계약 호가 체결은 미검증입니다. 보호Final OOS와 기존 환경은 변경하지 않았습니다.\n\n'
report+='|구분|후보|완료|승률%|수익률합계%|실현 순이익 원|MDD 원|최대평가손실 원|잔여|\n|---|---|---:|---:|---:|---:|---:|---:|---:|\n'
for name,x in leaders.items():
    name={'score_only':'전체 점수 최고','all_targets':'모든 합격조건 충족','min42':'42사이클 이상','no_residual':'미청산 없음','margin_shortage_free':'증거금 부족·거절 없음','risk_reduction':'일부 위험지표 개선','risk_reduction_min42_no_residual':'위험 개선·42회 이상·미청산 없음'}[name]
    r=x['result']
    report+=f'|{name}|{r["candidate_id"]}|{r["cycles"]}|{r["win_rate_pct"]:.4f}|{r["score_pct"]:+.10f}|{r["net_realized"]:,.2f}|{r["mdd_krw"]:,.2f}|{r["maximum_open_loss_krw"]:,.2f}|{r["residual_contracts"]}|\n'
report+='\n基準B:42사이클,16.7054302006977%,41,295,918.91원,MDD9,350,000원,잔여0. 합격은점수초과·완료42이상·잔여0·MDD기준이하·초기/유지/롤 자금부족 및진입거절0이며 승률100%를 요구하지 않습니다.\n\n'.replace('基準','기준')
report+='월별 기여는 청산 거래일 기준입니다. 이월 포지션의 미청산 평가는 주 점수에서 제외하며 종료가정 청산 점수는 별도입니다. 시간제한은 관측공백·시장휴장 때문에 실제 보유시간이 더 길어질 수 있습니다. 회복 정체는마지막0.01%p 이상 유리한진전 후 달력분입니다. 평균보유는완료사이클,최장은잔여를포함합니다.\n\n'
report+='회복·순손익의 단독/동시 및 손절·시간·정체와의 동시발동은 diagnostics/all_exit_causes.csv에 있습니다. 기존두주요조건간 배타성 지표와 전 조건의 단독 발동을 혼동하지 않습니다. 상위3/5거래 집중도는양의수익률합과순수익률합을분모로각각제공합니다. 인접조건 표는같은가설그룹과상태모드의파라미터거리이며독립검증이아닙니다.\n\n'
report+='현물편도0.05%, 선물계약당편도600원+청산율0.0003157%, 각레그편도2bp, 롤양쪽비용을유지합니다. 선물초기현금3천만원에서 손익누적, 추가입금/자동이체/물타기/수량축소가없습니다. 현물 충분조달 필요액은별도기록합니다. 역배차입가능성과비용, 과거호가, 분중극값은미검증이며7월6일~8월2일증거금일정은인접공식일정추론입니다. 원시가격은D:에만있어 INPUT_NOT_REMOTELY_REPRODUCIBLE입니다.\n\n'
report+='전체 순위 ranking_all_500.csv, 정확한 규칙 settings_new_500.json, 코드 strategy_code_ref.json, 배치별 전체 원장 archive와SHA는 batch_publication_index.csv를 참조합니다. 최고후보의작은비압축 cycles/fills/orders/exit_attribution CSV도별도제공합니다.\n'
report+='\n위험 개선 분류는 MDD 또는 최장 보유기간이 줄어든 경우로, 모든 위험지표가 함께 개선됐다는 뜻은 아닙니다. 청산 발동은 신호봉 종가 관측 기준이며 실제 다음 시가 대용 체결의 손익과 구분합니다.\n'
(out/'REPORT_KO.md').write_text(report,encoding='utf8')
write_json(out/'checkpoint.json',dict(status='ALL_500_BATCHES_PUBLISHED_VERIFIED_FINAL_PENDING',new_conditions=500,last_batch=10,next_batch=None,workers_running=False))
manifest(out)
print(json.dumps(dict(conditions=500,qualified=len(groups['all_targets']),leaders=leaders)),flush=True)
