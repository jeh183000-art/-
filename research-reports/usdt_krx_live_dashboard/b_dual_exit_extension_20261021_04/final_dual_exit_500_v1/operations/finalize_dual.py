from __future__ import annotations
import csv, gzip, hashlib, importlib.metadata, json, shutil
from pathlib import Path
import numpy as np
from runner import ROOT, SOURCE_HASH, MARGIN_HASH, table, write_json
from package_B import manifest

def main():
 out=ROOT/'publish_payloads/final_dual_exit_500_v1'
 assert not out.exists();out.mkdir(parents=True)
 rows=[json.loads(p.read_text()) for p in sorted((ROOT/'batches').glob('batch_*/candidates/*/result.json'))]
 assert len(rows)==500 and len({r['candidate_id'] for r in rows})==500
 rules={r['candidate_id']:r['rule'] for p in sorted((ROOT/'preregistration').glob('batch_*.json')) for r in json.loads(p.read_text())['conditions']}
 assert len(rules)==500
 receipts=[json.loads((ROOT/'publication'/f'batch_{i:04d}_results_verified.json').read_text()) for i in range(1,11)]
 assert all(r['status']=='PUBLISHED_VERIFIED' for r in receipts)
 baseline=json.loads((ROOT/'baseline/B_original/result.json').read_text());ba=json.loads((ROOT/'baseline_audit/validation.json').read_text());baseline.update({k:ba[k] for k in ('profit_factor_krw','profit_factor_status')})
 eligible=sorted([r for r in rows if r['feasible'] and r['cycles']],key=lambda r:r['score_pct'],reverse=True)
 groups={'all_targets':[r for r in eligible if r['goal_qualified']],'score_only':eligible,'min42':[r for r in eligible if r['cycles']>=42],'no_residual':[r for r in eligible if not r['residual_contracts']],'margin_shortage_free':[r for r in eligible if r['margin_shortage_free']]}
 leaders={}
 for key,items in groups.items():
  table(out/f'top20_{key}.csv',items[:20])
  if items:leaders[key]={'result':items[0],'rule':rules[items[0]['candidate_id']]}
 table(out/'results_new_500.csv',rows);write_json(out/'settings_new_500.json',rules)
 write_json(out/'baseline_B_result.json',baseline)
 table(out/'target_shortfalls.csv',[dict(r,failed_targets=';'.join(k for k in ('beats_B','meets_cycle_count','meets_residual_zero','meets_mdd_limit','margin_shortage_free') if not r[k])) for r in rows if not r['goal_qualified']])
 table(out/'zero_completed.csv',[r for r in rows if not r['cycles']])
 table(out/'ineligible.csv',[r for r in rows if not r['feasible']])
 table(out/'open_residuals.csv',[r for r in rows if r['residual_contracts']])
 audits=[]
 for p in sorted((ROOT/'batches').glob('batch_*/candidates/*/audit.json')):
  r=json.loads(p.read_text());assert r['status']=='PASS' and r['vector_replay']['cumulative_mdd_nondecreasing']
  audits.append(dict(candidate_id=p.parent.name,account_audit_status=r['status'],**r['vector_replay']))
 assert len(audits)==500;table(out/'validation_all_500.csv',audits)
 actual=json.loads((ROOT/'actual_mdd_audit/validation.json').read_text());assert actual['status']=='PASS_ACTUAL_RECORDED_MDD_NONDECREASING'
 shutil.copytree(ROOT/'metrics_audit',out/'metrics_audit');shutil.copytree(ROOT/'registration_audit',out/'registration_audit');shutil.copytree(ROOT/'actual_mdd_audit',out/'actual_mdd_audit');shutil.copytree(ROOT/'baseline_audit',out/'baseline_audit')
 inventory=list(csv.DictReader((ROOT/'baseline_audit/original_B_inventory.csv').open(encoding='utf8')))
 origin=ROOT.parent/'b_focus_20261021_03/batches/batch_0009/candidates/BF-09-027'
 for r in inventory:
  assert hashlib.sha256((origin/r['file']).read_bytes()).hexdigest()==r['sha256']
  assert hashlib.sha256((ROOT/'baseline/B_original'/r['file']).read_bytes()).hexdigest()==r['sha256']
 write_json(out/'original_B_preservation.json',dict(status='PASS',files=len(inventory),prior_strategy_resimulated=False,A_C_D_modified=False))
 table(out/'risk_classification.csv',[{k:r[k] for k in ('candidate_id','low_cycle_count','long_holding_risk','longer_than_baseline','open_loss_hidden_risk','residual_contracts','residual_net_after_exit_cost','forced_terminal_score_pct','margin_shortage_free')} for r in rows])
 table(out/'ranking_unrestricted_paper.csv',sorted([r for r in rows if r['cycles']],key=lambda r:r['score_pct'],reverse=True)[:20])
 winners={v['result']['candidate_id'] for v in leaders.values()}
 for cid in winners:
  source=next((ROOT/'batches').glob(f'batch_*/candidates/{cid}'))
  for name in ('cycles','fills','orders'):
   with gzip.open(source/f'{name}.csv.gz','rb') as inp,(out/f'{cid}_{name}.csv').open('xb') as dest:shutil.copyfileobj(inp,dest)
  shutil.copy2(source/'period_contribution.csv',out/f'{cid}_period_contribution.csv')
 write_json(out/'best_rules_and_results.json',leaders)
 table(out/'costs.csv',[{k:r[k] for k in ('candidate_id','fees_krw','slippage_krw','borrow_unverified')} for r in rows])
 table(out/'batch_publication_index.csv',[dict(batch=i+1,commit=r['commit'],remote=r['remote'],files=r['files']) for i,r in enumerate(receipts)])
 summaries=[json.loads((ROOT/'publish_payloads'/f'batch_{i:04d}_results_v1/publication_summary.json').read_text()) for i in range(1,11)]
 batchrows=[dict(batch=i+1,qualified=s['batch_qualified_count'],**s['selected']) for i,s in enumerate(summaries) if s['selected']]
 table(out/'batch_selected.csv',batchrows)
 # Preserve previous research and aggregate only the new 500 saved results.
 baseline_rule=json.loads((ROOT/'baseline/registry.json').read_text())
 write_json(out/'baseline_registry.json',baseline_rule)
 for p in ('code_ref.json',):shutil.copy2(ROOT/'publication'/p,out/'strategy_code_ref.json')
 shutil.copy2(ROOT/'drawdown_tests_v2.json',out/'drawdown_tests_v2.json')
 shutil.copytree(ROOT/'operations',out/'operations',ignore=shutil.ignore_patterns('*.out','*.err','__pycache__'))
 write_json(out/'settings.json',dict(parent='BF-09-027',contracts=17,spot_quantity=170000,futures_cash=30000000,additional_entries=False,simultaneous_opposite=False,external_deposits=False,new_conditions=500,score='sum(unrounded completed cycle net / abs(initial spot entry notional) * 100)',open_pnl_excluded=True,goal_count=len(groups['all_targets'])))
 write_json(out/'environment.json',dict(python='3.12.0',dependencies={n:importlib.metadata.version(n) for n in ('numpy','numba','llvmlite','pandas')},storage='D_ONLY',mode='EXPLORATORY_PAPER'))
 write_json(out/'provenance.json',dict(source_sha256=SOURCE_HASH,margin_sha256=MARGIN_HASH,baseline_commit='c63352755d43b067b2124e748297efe6cbf6ecbf',raw_input_status='INPUT_NOT_REMOTELY_REPRODUCIBLE',final_oos_access=False,scope='Approved exploratory KRX business dates 2026-01-01..2026-10-15 and necessary night calendar boundaries',limitations=['Next contiguous observed minute OPEN is fill proxy; historical depth absent','Reverse borrowing availability and cost unverified','Jul06-Aug02 margin schedule inferred from adjacent official schedules','MDD excludes unobserved intraminute extremes','Exploratory sample optimisation is not independent validation']))
 diagnostic=json.loads((ROOT/'baseline_audit/validation.json').read_text())
 report='# B 개선형 추가500조건 최종 결과\n\n'
 report+='BF-09-027과 기존1,500조건·A/B/C/D를 변경하지 않고 신규500조건만 사전등록·실행했습니다.\n'
 report+='기준42사이클·16.7054302006977%·순이익41,295,918.91원·MDD935만원을 기존 저장원장으로 확인했습니다.\n'
 report+=f'새 목표 다섯 가지를 모두 충족한 후보는 {len(groups["all_targets"])}개입니다.\n'
 report+='주 점수는 비용차감 완료사이클 수익률을 반올림 전에 단순합산하며, 초기자본이나 원화순이익으로 순위를 바꾸지 않았습니다.\n'
 report+='미청산 손익은 주 점수와 분리했고, 잔여·저거래수·7일초과 보유는 별도 분류했습니다.\n'
 report+='체결·PF·정산·롤오버·현금·증거금·누적MDD와 모든 사전등록 코드/입력 해시를 독립 대조했습니다.\n'
 report+='탐색자료 내 결과이며 실제 주문·보호Final OOS·Gateway·OpenClaw·예약작업 변경은 없습니다.\n\n'
 report+='|구분|후보|완료|승률%|수익률합계%|순이익 원|PF|MDD 원|최대평가손실 원|최장보유 일|잔여|최소초기증거금여유 원|\n|---|---|---:|---:|---:|---:|---|---:|---:|---:|---:|---:|\n'
 for key,x in [('baseline',dict(result=baseline))]+list(leaders.items()):
  r=x['result'];pf=f"{r['profit_factor_krw']:.4f}" if r['profit_factor_krw'] is not None else '∞' if r['profit_factor_status']=='INFINITE_NO_LOSSES' else '산출불가'
  report+=f'|{key}|{r["candidate_id"]}|{r["cycles"]}|{r["win_rate_pct"]:.4f}|{r["score_pct"]:+.10f}|{r["net_realized"]:,.2f}|{pf}|{r["mdd_krw"]:,.2f}|{r["maximum_open_loss_krw"]:,.2f}|{r["longest_hold_minutes"]/1440:.5f}|{r["residual_contracts"]}|{r["minimum_initial_headroom_krw"]:,.2f}|\n'
 report+='\n합격 목표는 점수16.7054302006977% 초과·완료42회 이상·잔여0·MDD935만원 이하·증거금 부족 및 진입거절0입니다.\n'
 report+='\n모든 정확한 규칙은 best_rules_and_results.json과 settings_new_500.json, 미달 이유는 target_shortfalls.csv, 배치별 원장과SHA는 batch_publication_index.csv에 있습니다. 결과CSV의PF는 비용차감 완료사이클 원화이익합/손실합 절대값입니다. 손실0 표본의∞는 무위험이나 독립 검증을 의미하지 않습니다.\n\n'
 report+=f'기준 전략은42회 중 {diagnostic["over_1day"]}회가 하루 이상, {diagnostic["over_7days"]}회가7일 이상 보유했고 최장{diagnostic["longest_hold_minutes"]/1440:.5f}일입니다. 높은 승률은 중간 평가손실·장기 보유와 함께 봐야 합니다. 실제 저장원장 진단이며 기준 전략을 시간청산으로 다시 시뮬레이션한 것은 아닙니다. 결측 관측은 보간하지 않았습니다.\n\n'
 exit_diag=json.loads((ROOT/'operations/baseline_exit_rule_diagnostic.json').read_text())
 report+=f'기준42사이클은 모두 괴리회복 조건을 충족해 청산했고, 순손익0.7% 조건은1회 같은 봉에서 동시충족했습니다. 순손익 조건의 단독 청산은 {exit_diag["pnl_rule"]-exit_diag["both"]}회입니다. 이는 관측된 완료 원장의 사실이며 미관측 분중 움직임을 추정한 결과가 아닙니다.\n\n'
 report+='현물편도0.05%, 선물 계약당편도600원+청산율0.0003157%, 각레그편도2bp와 롤양쪽 비용을 유지합니다. 최초17계약·170000 USDT 한묶음, 추가진입없음, 선물초기현금3천만원, 외부입금·자동이체없음입니다. 현물조달 충분 가정의 필요액은 spot_financing_proxy_krw로 별도 기록합니다. 역배 차입 가능성·차입비용과17계약 실제호가 체결은 미검증입니다. 신호 후 다음 연속 관측분봉 시가 체결대용값이며, 시간상한도 거래/관측 공백 때문에 실제 보유기간이 길어질 수 있습니다. 7월6일~8월2일 증거금 일정은 인접 공식 일정 추론이고 분중 손실은 관측되지 않았습니다.\n\n'
 report+='서로 다른 조건이 같은 저장 계좌원장 해시를 만든 경우는 metrics_audit/account_path_groups.csv에 구분했습니다. 서로 다른 규칙500개를 독립적인500개 통계표본으로 해석하지 않습니다.\n\n'
 report+='초기2배치는 기존회복0.6%p OR 순손익0.7% 익절을 그대로 유지한 진입선만 비교했습니다. 이후 회복폭·순손익 익절·조합·비대칭·반전·위험조건을 단계적으로 비교했고, 후반 적응형 비교도 배치 실행 전에 등록했습니다. 기존과 신규 모든 설정의 중복 및 코드/입력 해시를 재검사했습니다. 원시시세는 D:공통 경로에 보존하며 INPUT_NOT_REMOTELY_REPRODUCIBLE입니다. 모든 배치의9파일/후보 전체 원장은 무손실 분할TAR·member SHA·NPZ CRC 검사로 보존했습니다.\n'
 chosen=leaders.get('all_targets') or leaders.get('score_only')
 if chosen:
  report+='\n선정 후보의 정확한 진입·청산·필터 설정:\n'+json.dumps(chosen['rule'],ensure_ascii=False,indent=2)+'\n'
  r=chosen['result'];report+=f'\n종료시점 가정 청산 점수 {r["forced_terminal_score_pct"]:+.10f}%, 잔여 청산비용차감 평가손익 {r["residual_net_after_exit_cost"]:,.2f}원, 최소 유지증거금 여유 {r["minimum_maintenance_headroom_krw"]:,.2f}원입니다. 상대회복은 진입 신호봉 기준, 손익익절은 두포지션 손익과 예상청산비용을 포함한 평가수익률 기준입니다.\n'
 (out/'REPORT_KO.md').write_text(report,encoding='utf8')
 write_json(out/'checkpoint.json',dict(status='ALL_500_BATCHES_PUBLISHED_VERIFIED_FINAL_PENDING',new_conditions=500,last_batch=10,next_batch=None,workers_running=False,qualified_count=len(groups['all_targets'])))
 manifest(out)
 print(json.dumps(dict(output=str(out),conditions=500,qualified_count=len(groups['all_targets']),leaders=leaders)),flush=True)

if __name__=='__main__':main()
