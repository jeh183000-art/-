from __future__ import annotations
import csv, gzip, hashlib, importlib.metadata, json, shutil
from pathlib import Path
import numpy as np
from runner import ROOT, SOURCE_HASH, MARGIN_HASH, table, write_json
from package_B import manifest

def main():
 out=ROOT/'publish_payloads/final_B_500_v1'
 assert not out.exists();out.mkdir(parents=True)
 rows=[json.loads(p.read_text()) for p in sorted((ROOT/'batches').glob('batch_*/candidates/*/result.json'))]
 assert len(rows)==500 and len({r['candidate_id'] for r in rows})==500
 rules={r['candidate_id']:r['rule'] for p in sorted((ROOT/'preregistration').glob('batch_*.json')) for r in json.loads(p.read_text())['conditions']}
 assert len(rules)==500
 receipts=[json.loads((ROOT/'publication'/f'batch_{i:04d}_results_verified.json').read_text()) for i in range(1,11)]
 assert all(r['status']=='PUBLISHED_VERIFIED' for r in receipts)
 baseline=json.loads((ROOT/'baseline/B_original/result.json').read_text())
 eligible=sorted([r for r in rows if r['feasible'] and r['cycles']],key=lambda r:r['score_pct'],reverse=True)
 groups={'all_targets':[r for r in eligible if r['goal_qualified']],'score_only':eligible,'min39':[r for r in eligible if r['cycles']>=39],'no_residual':[r for r in eligible if not r['residual_contracts']],'margin_shortage_free':[r for r in eligible if r['margin_shortage_free']]}
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
 shutil.copytree(ROOT/'registration_audit',out/'registration_audit');shutil.copytree(ROOT/'actual_mdd_audit',out/'actual_mdd_audit');shutil.copytree(ROOT/'baseline_audit',out/'baseline_audit')
 inventory=list(csv.DictReader((ROOT/'baseline_audit/original_B_inventory.csv').open(encoding='utf8')))
 origin=ROOT.parent/'lump17_sweep_20261021_01/batches/batch_0001/candidates/L17-01-013'
 for r in inventory:
  assert hashlib.sha256((origin/r['file']).read_bytes()).hexdigest()==r['sha256']
  assert hashlib.sha256((ROOT/'baseline/B_original'/r['file']).read_bytes()).hexdigest()==r['sha256']
 write_json(out/'original_B_preservation.json',dict(status='PASS',files=len(inventory),prior_strategy_resimulated=False,A_C_D_modified=False))
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
 # One-axis holding/stop comparisons are references to saved runs, never repeat the previous 1000.
 baseline_rule=json.loads((ROOT/'baseline/registry.json').read_text())
 write_json(out/'baseline_registry.json',baseline_rule)
 for p in ('code_ref.json',):shutil.copy2(ROOT/'publication'/p,out/'strategy_code_ref.json')
 shutil.copy2(ROOT/'drawdown_tests_v2.json',out/'drawdown_tests_v2.json')
 shutil.copytree(ROOT/'operations',out/'operations',ignore=shutil.ignore_patterns('*.out','*.err','__pycache__'))
 write_json(out/'settings.json',dict(parent='L17-01-013',contracts=17,spot_quantity=170000,futures_cash=30000000,additional_entries=False,simultaneous_opposite=False,external_deposits=False,new_conditions=500,score='sum(unrounded completed cycle net / abs(initial spot entry notional) * 100)',open_pnl_excluded=True,goal_count=len(groups['all_targets'])))
 write_json(out/'environment.json',dict(python='3.12.0',dependencies={n:importlib.metadata.version(n) for n in ('numpy','numba','llvmlite','pandas')},storage='D_ONLY',mode='EXPLORATORY_PAPER'))
 write_json(out/'provenance.json',dict(source_sha256=SOURCE_HASH,margin_sha256=MARGIN_HASH,baseline_commit='e1254e5141b3201cf594111cbc47b1fdfd6a5e9a',raw_input_status='INPUT_NOT_REMOTELY_REPRODUCIBLE',final_oos_access=False,scope='Approved exploratory KRX business dates 2026-01-01..2026-10-15 and necessary night calendar boundaries',limitations=['Next contiguous observed minute OPEN is fill proxy; historical depth absent','Reverse borrowing availability and cost unverified','Jul06-Aug02 margin schedule inferred from adjacent official schedules','MDD excludes unobserved intraminute extremes','Exploratory sample optimisation is not independent validation']))
 report='# B 전략 집중 개선 500조건 결과\n\n'
 report+='기존 A·B·C·D와 1,000조건은 변경·재계산하지 않고 B에서만 신규500조건을 만들었습니다.\n'
 report+='원본 B의39사이클·수익률 합계14.9513190710%·순이익36,755,589.35원·MDD9,350,000원을 저장 원장으로 재검산했습니다.\n'
 report+=f'목표 다섯 가지를 모두 충족한 신규 후보는 {len(groups["all_targets"])}개입니다.\n'
 report+='주 점수는 완료 사이클별 비용 차감 순손익/최초 현물 명목 절대값×100의 반올림 전 단순합계입니다.\n'
 report+='잔여 포지션 손익과 가정 강제청산 점수는 주 점수와 분리했습니다.\n'
 report+='기존B는39회 중25회가 하루 이상,7회가7일 이상 보유했으며 7일에 열린7회는 모두 평가손실이었습니다.\n'
 report+='모든 신규 원장 검산과 누적MDD 검사를 통과했으며 실제 주문과 보호 Final OOS 접근은 없습니다.\n\n'
 report+='|구분|후보|완료|승률%|수익률합계%|순이익 원|MDD 원|최대평가손실 원|최장보유 일|잔여|최소초기증거금여유 원|\n|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|\n'
 for key,x in [('baseline',dict(result=baseline))]+list(leaders.items()):
  r=x['result'];report+=f'|{key}|{r["candidate_id"]}|{r["cycles"]}|{r["win_rate_pct"]:.4f}|{r["score_pct"]:+.10f}|{r["net_realized"]:,.2f}|{r["mdd_krw"]:,.2f}|{r["maximum_open_loss_krw"]:,.2f}|{r["longest_hold_minutes"]/1440:.5f}|{r["residual_contracts"]}|{r["minimum_initial_headroom_krw"]:,.2f}|\n'
 report+='\n정확한 조건은 best_rules_and_results.json, 전체500조건은 settings_new_500.json, 미달 이유는 target_shortfalls.csv에 있습니다. 모든 원장은 batch_publication_index.csv의 불변 폴더 분할TAR에 파일별SHA로 보존합니다. 공통코드와 승인 원시는 중복 저장하지 않습니다.\n\n'
 report+='모든 목표: 점수14.95131907100779% 초과, 완료39회 이상, 잔여0, MDD935만원 이하, 진입 거절·초기/유지증거금 부족·롤 자금부족0. 높은 점수만으로 목표 통과라고 표시하지 않습니다.\n\n'
 report+='100% 승률은 장중 손실이 없었다는 뜻이 아닙니다. 기존B는 시간제한·손절 없이 최장26.9028일 기다렸습니다. 7일 시점에 열린7회는 모두 평가손실 후 최종 익절한 표본으로 미래 회복을 보장하지 않습니다. 진단은 실제 저장원장의 정확한 관측시각만 사용했고 결측은 보간하지 않았으며 기존B를 시간청산으로 재실행한 값은 아닙니다.\n\n'
 report+='현물편도0.05%, 선물 계약당편도600원+청산율0.0003157%, 각레그편도2bp와 롤 양쪽 비용을 유지합니다. 현물조달 충분가정이며 선물3천만원에서 외부입금·자동이체 없이17계약만 주문합니다. 역배 차입/비용 미검증 이론값, 다음 연속 관측분봉 시가 체결대용값, 7월6일~8월2일 증거금일정 추론, 분중손실 미관측 한계가 있습니다. 탐색 결과는 독립 검증 성과가 아닙니다.\n\n'
 report+='실제전략1000개 외 CONTROL1개 때문에 등록기 목록 확인만 수정했습니다. 매매·비용·검산 수식 변경은 없고 수정 전 신규 시장실행은0건이었습니다. 일부 GitHub 텍스트 base64 업로드 내부오류는 UTF-8 재시도 후 원격바이트·SHA를 검증했습니다.\n'
 chosen=leaders.get('all_targets') or leaders.get('score_only')
 if chosen:
  report+='\n선정 후보의 정확한 진입·청산·필터 설정(상대회복은 진입 신호봉 기준):\n'+json.dumps(chosen['rule'],ensure_ascii=False,indent=2)+'\n'
  r=chosen['result'];report+=f'\n종료시점 가정 청산 보조 점수 {r["forced_terminal_score_pct"]:+.10f}%, 잔여 청산비용 차감 평가손익 {r["residual_net_after_exit_cost"]:,.2f}원. 최소 유지증거금 여유 {r["minimum_maintenance_headroom_krw"]:,.2f}원.\n'
 report+='\n순손익 익절 신호는 두 포지션 누적손익에서 이미 낸 비용 및 예상 청산비용을 뺀 금액/최초 현물 명목×100입니다. 거래량 필터는 신호봉 KRX 선물 거래량(계약)이며 17계약 주문의 체결 검증을 뜻하지 않습니다. 시간 상한 신호도 다음 연속 관측 분봉 체결 가능 제약 때문에 실제 보유기간이 더 길어질 수 있습니다. 기존B의 높은 승률과 개선 후보의 긴 보유기간은 별도 위험입니다.\n'
 report+='\n9배치 게시 중 장시간 사용한 Node 도구의 힙 메모리 한도 오류가 발생했습니다. 매매 계산과 원장 검산은 이미 완료되어 D:에 보존됐고, 게시 도구만 초기화하여 같은 패킷을 재업로드했습니다. 전략 재계산이나 Gateway 변경은 없었습니다.\n'
 (out/'REPORT_KO.md').write_text(report,encoding='utf8')
 write_json(out/'checkpoint.json',dict(status='ALL_500_BATCHES_PUBLISHED_VERIFIED_FINAL_PENDING',new_conditions=500,last_batch=10,next_batch=None,workers_running=False,qualified_count=len(groups['all_targets'])))
 manifest(out)
 print(json.dumps(dict(output=str(out),conditions=500,qualified_count=len(groups['all_targets']),leaders=leaders)),flush=True)

if __name__=='__main__':main()
