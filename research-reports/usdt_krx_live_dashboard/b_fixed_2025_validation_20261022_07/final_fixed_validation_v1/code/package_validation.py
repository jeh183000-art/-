from pathlib import Path
import csv,gzip,json,hashlib,shutil,platform,sys
import pandas as pd
import numpy as np
import runner
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'publish_payloads/final_fixed_validation_v1';OUT.mkdir(parents=True)
def cp(p,target=None):
 dest=OUT/(target or p.relative_to(ROOT));dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dest)
def js(n,x):runner.write_json(OUT/n,x)
partial=json.loads((ROOT/'validation_2025_partial/results.json').read_text());comparison=json.loads((ROOT/'comparison_2026/comparison.json').read_text());audit=json.loads((ROOT/'data_audit/summary.json').read_text());night=json.loads((ROOT/'night_acquisition/summary.json').read_text());frame=pd.read_csv(ROOT/'validation_2025_partial/matched_simulation_bars.csv',dtype={'business_date':str})
legacy=['meets_cycle_count','meets_residual_zero','meets_mdd_limit','beats_B','goal_qualified','score_delta_B_pp','numerical_tie_to_B']
allresults=[]
for year,rows in [('2026_APPROVED_EXPLORATORY',comparison['variants']),('2025_PARTIAL_NOV_DEC',partial)]:
 for r in rows:allresults.append({**{k:v for k,v in r.items() if k not in legacy},'period_class':year})
runner.table(OUT/'results.csv',allresults)
for p in (ROOT/'preregistration').glob('*.json'):cp(p)
for p in (ROOT/'data_audit').glob('*'):
 if p.name!='matched_timestamps_2025.csv':cp(p)
cp(ROOT/'data_access/api_results.json')
for name in ['session_status.csv','frozen_session_contract_plan.csv','summary.json']:cp(ROOT/'night_acquisition'/name)
cp(ROOT/'roll_quotes/audit.json');cp(ROOT/'comparison_2026/comparison.json');cp(ROOT/'drawdown_tests_v2.json');cp(ROOT/'validation_2025_partial/input_validation.json');cp(ROOT/'validation_2025_partial/margin_schedule.csv')
codefiles=['access_probe.py','data_audit.py','collect_2025_night.py','collect_roll_quotes.py','compare_2026.py','validate_partial.py','package_validation.py']
for name in codefiles:cp(ROOT/'code'/name)
# Reuse existing public common source; do not upload the same engine again.
ref=json.loads((ROOT.parent/'b_focus_20261021_03/publish_payloads/final_B_500_v1/strategy_code_ref.json').read_text());ref['input_loader']={'commit':'c63352755d43b067b2124e748297efe6cbf6ecbf','path':'research-reports/usdt_krx_live_dashboard/unlimited_revalidation_20261017_01/batch_000_original_control/paper_engine.py','sha256':hashlib.sha256((ROOT.parents[1]/'shared/approved_20261016_01/paper_engine.py').read_bytes()).hexdigest()};js('strategy_code_ref.json',ref)
periods=[];costs=[];directions=[]
for r in partial:
 p=ROOT/'validation_2025_partial'/r['candidate_id'];dst='ledgers_2025/'+r['candidate_id']
 for name in ['cycles.csv.gz','fills.csv.gz','fills_with_accounting_time.csv','orders.csv.gz','residual.csv','audit.json','full_account_ledger.npz','numeric_result.npz']:cp(p/name,dst+'/'+name)
 cycles=pd.read_csv(p/'cycles.csv.gz',dtype={'entry_business_date':str,'exit_business_date':str})
 if len(cycles)==0:
  cycles=pd.DataFrame(columns=[*runner.TRADE_FIELDS,'entry_business_date','exit_business_date','return_pct'])
  cycles.to_csv(OUT/dst/'cycles.csv.gz',index=False,compression='gzip')
 ledger=np.load(p/'full_account_ledger.npz')['ledger'];phase=json.loads((ROOT/'validation_2025_partial/input_validation.json').read_text())['settlements'];effective={x['row']:x['settlement_effective_kst'] for x in phase}
 # Entire account/risk ledger, readable after gzip decompression, including post-close phase timestamp.
 with gzip.open(OUT/dst/'cash_margin_ledger.csv.gz','wt',encoding='utf8',newline='') as stream:
  w=csv.writer(stream);w.writerow(['row','phase','timestamp_kst','business_date',*runner.LEDGER_FIELDS])
  for i in range(len(frame)):
   for ph in range(3):
    x=ledger[i,ph]
    if np.isfinite(x[5]):w.writerow([i,['OPEN','CLOSE','SETTLEMENT'][ph],effective.get(i,frame.iloc[i].timestamp_kst) if ph==2 else frame.iloc[i].timestamp_kst,str(frame.iloc[i].business_date),*x])
 for kind,labels in [('month',['202511','202512']),('quarter',['2025Q4'])]:
  for label in labels:
   mask=frame.business_date.str.startswith(label) if kind=='month' else np.ones(len(frame),dtype=bool)
   cr=cycles[cycles.exit_business_date.str.startswith(label)] if kind=='month' else cycles
   vals=ledger[mask].reshape(-1,11);vals=vals[np.isfinite(vals[:,5])];held=vals[np.abs(vals[:,7])>0];nets=cr.net.to_numpy() if len(cr) else np.array([]);last=vals[-1]
   pnl=vals[:,5]-30000000.;localdd=np.maximum.accumulate(pnl)-pnl
   periods.append(dict(candidate_id=r['candidate_id'],scope='PARTIAL_WINDOW_ONLY',period_type=kind,period=label,cycles=len(cr),wins=int((nets>0).sum()),win_rate_pct=float((nets>0).mean()*100) if len(nets) else None,score_pct=float(cr.return_pct.sum()) if len(cr) else 0,net_realized=float(nets.sum()),profit_factor=float(nets[nets>0].sum()/-nets[nets<0].sum()) if (nets<0).any() else 'INF' if (nets>0).any() else None,mdd_within_observed_period_krw=float(localdd.max()),cumulative_mdd_end_krw=float(last[8]),maximum_open_loss_krw=float(max(0,-held[:,6].min())) if len(held) else 0,mean_hold_minutes=float(cr.hold_minutes.mean()) if len(cr) else None,longest_hold_minutes=float(cr.hold_minutes.max()) if len(cr) else None,residual_contracts_at_period_end=int(abs(last[7])*17),minimum_initial_headroom=float(held[:,9].min()) if len(held) else None,minimum_maintenance_headroom=float(held[:,4].min()) if len(held) else None,maximum_spot_financing_proxy=float(vals[:,10].max()),account_reset=False))
 for direction,name in [(1,'테더롱_선물숏'),(-1,'테더숏_선물롱_차입미검증')]:
  c=cycles[cycles.direction==direction];directions.append(dict(candidate_id=r['candidate_id'],direction=name,cycles=len(c),score_pct=float(c.return_pct.sum()),net_realized=float(c.net.sum())))
 costs.append(dict(candidate_id=r['candidate_id'],spot_side_rate=.0005,future_contract_side_krw=600,future_notional_side_rate=.000003157,slippage_each_leg_side_bp=2,fees_krw=r['fees_krw'],slippage_krw=r['slippage_krw'],borrow_cost='UNVERIFIED_NOT_INCLUDED',funding='NO_PERPETUAL_FUNDING',roll_cost='both future sides included'))
runner.table(OUT/'period_results.csv',periods);runner.table(OUT/'direction_contribution.csv',directions);runner.table(OUT/'costs.csv',costs)
# Unavailable full-year/month/quarter metrics are missing, never zero or a concatenation of reset accounts.
missing=[]
for c in partial:
 for period in ['2025_FULL_YEAR',*[f'2025-{m:02}' for m in range(1,11)],'2025-Q1','2025-Q2','2025-Q3']:
  missing.append(dict(candidate_id=c['candidate_id'],period=period,status='NOT_VALIDATED_MISSING_CONTINUOUS_ANNUAL_HISTORY',cycles=None,score_pct=None,net_realized=None,mdd_krw=None))
runner.table(OUT/'unvalidated_periods.csv',missing)
coverage=pd.read_csv(ROOT/'data_audit/monthly_coverage.csv');ss=pd.read_csv(ROOT/'night_acquisition/session_status.csv')
for i,row in coverage.iterrows():
 n=ss[ss.business_date.str.startswith(row['month'])];coverage.at[i,'night_saved_rows']=int(n.rows.sum());coverage.at[i,'night_verified_sessions']=int((n.status=='COMPLETE').sum())
coverage.to_csv(OUT/'monthly_coverage_final.csv',index=False)
js('environment.json',dict(python=sys.version,numpy=np.__version__,pandas=pd.__version__,platform=platform.platform(),mode='FIXED_RULE_PARTIAL_VALIDATION_BORROW_UNVERIFIED_PAPER',storage='D:/Codex_Research',packages_changed=False))
js('provenance.json',dict(reference_commit='c63352755d43b067b2124e748297efe6cbf6ecbf',full_year_validation=False,partial_business_dates=['2025-11-03','2025-12-30'],start_flat_partial_window=True,account_never_reset=True,input_reproduction='INPUT_NOT_REMOTELY_REPRODUCIBLE: raw market inputs retained on D; immutable hashes and API acquisition code provided',prior_use='2025 daily validation had been analyzed before this task; unused independent status not established',boundary='2026 approved source contains497 calendar2025 rows belonging to20260102; excluded from2025 KRX business-date validation',protected_oos_accessed=False,orders=False,sweep=False,source_audit=audit,night_acquisition=night,legacy_goal_flags='Ignored; runner legacy optimization labels are not evaluation criteria in this fixed validation'))
js('checkpoint.json',dict(status='LOCAL_AUDITED_READY_FOR_REMOTE_VERIFICATION',conditions_frozen=2,conditions_2025_partial_executed=2,full_year_status='BLOCKED_MISSING_JAN_SEP_HISTORY',next_action='Acquire missing official minute history; do not optimize',worker_running=False))
js('validation.json',dict(status='PASS_FOR_RECORDED_PARTIAL_INPUT_ONLY',original_2026_regression='PASS',independent_cash_settlement_rollover_margin_mdd='PASS',full_year='NOT_VALIDATED',no_monthly_resets=True,raw_sources_preserved=True,protected_oos_accessed=False,orders=False,borrowing_verified=False,partial_risk='Unobserved periods can hide adverse price paths and signals; observed PAPER result is not full-market execution validation'))
lines=['# B 고정 규칙 — 2025년 검증 결과와 자료 한계','',
'2025년 전체 연속 검증은 1~9월 실제 분봉이 없어 완료하지 못했습니다.',
'규칙을 바꾸지 않은 두 버전을 2025년 성적 확인 전에 고정했습니다.',
'2026년 원본 대조는 42사이클·+16.7054302007%·41,295,918.91원으로 재현됐습니다.',
'주 검증인 회복 청산 단독형도 2026년에는 같은 체결·계좌 경로였습니다.',
'2025년 11월3일~12월30일만 한 계좌로 이어 계산한 부분기간 PAPER를 별도로 제시합니다.',
'이 부분기간은 처음에 무포지션·선물현금3천만원을 가정하므로 1월부터의 계좌 재현이 아닙니다.',
'역배 차입 미검증, 결측·호가·분중 위험 때문에 실거래 검증 또는 독립 미사용 OOS 성과가 아닙니다.','',
'|기간|청산 규칙|완료|수익률 합계 %|실현 순이익 원|MDD 원|잔여 계약|',
'|---|---|---:|---:|---:|---:|---:|']
for r in allresults:lines.append(f"|{r['period_class']}|{r['candidate_id']}|{r['cycles']}|{r['score_pct']:.10f}|{r['net_realized']:,.2f}|{r['mdd_krw']:,.2f}|{r['residual_contracts']}|")
lines+=['','2025년 전체 연도·미관측 월의 거래수와 수익은 0이 아니라 미검증(NA)입니다. unvalidated_periods.csv를 보십시오.','',
'고정 규칙: −0.97% 하향 통과 테더롱/선물숏, +0.85% 상향 통과 테더숏/선물롱. 최초17계약·170,000USDT만, 추가진입·부분청산·양방향 동시보유 없음. 주 검증은 신호봉 대비0.6%p 회복만, 원본 대조군만 비용차감 평가수익률+0.7% OR 청산을 추가합니다. 별도 손절·시간상한·대기 없음. 보유 중 신규신호 무시.','',
'주 점수는 각 완료 사이클 비용차감 순손익/최초 현물 진입명목 절대값×100의 반올림 전 단순합계입니다. 잔여 청산비용 차감 손익과 종료 가정청산 점수는 results.csv에 별도로 있습니다. 정배·역배 기여는 direction_contribution.csv, 월·분기 수치는 period_results.csv에 있습니다. 월·분기 계좌를 리셋하지 않았으며 월별 MDD와 누적 MDD는 구분했습니다.','',
'자료 감사: 업비트523,532개, KRX정규장59일23,149개, 라벨 교집합23,149개. 중복과 OHLC 오류0, 종가59/59일 일치, 거래량0/59일 일치. 거래량 차이를 분봉에 배분하거나 보간하지 않았고 종가 일치만으로 완전성을 확정하지 않았습니다. 신규 야간 확보 내역은 monthly_coverage_final.csv 및 night_acquisition/session_status.csv에 있습니다.','',
'2025년 6월9일 이전에는 KRX 자체 야간시장이 열리지 않았습니다. Eurex 연계거래를 동일한 미국달러선물 야간 자료로 합치지 않았습니다. 6~9월은 월 양끝 대표 요청이 빈 응답인 관측이며 모든 날짜를 요청했다고 주장하지 않습니다. 2025-09-30 CF/CM 재조회도 HTTP200/rt_cd0/MCA00000/0행입니다. 공식 보관기간 제한을 단정하지 않습니다.','',
'11~12월 부분 검증: KRX 공식 종가·거래량이 모두 맞는 야간 세션만 사용했습니다. 정규장 거래량 잔차와 11월13일 수능일 관측 누락은 남아 있습니다. 11월17일/12월15일08:45에 기존월물·다음월물 실제 시가를 대조해 롤오버 양쪽 비용을 반영했습니다. 당일 총거래량으로 신호를 만들지 않았습니다.','',
'정산은 마지막 관측행의 SETTLEMENT 회계 단계에 연결하되 실제 시장종료시각으로 표시합니다. 해당 행부터 종료시각 사이에 실행 가능한 관측이 없고 다음 행도 연속분봉이 아닌지 검사했습니다. 정산가격으로 봉을 만들거나 체결하지 않았습니다. 일별 API에 공시 타임스탬프는 없으며 정확한 증권사 계좌 반영시각은 검증하지 못했습니다. 2025-11-13 종료16:45와 그날16:44업비트 종가를 사용했습니다.','',
'증거금은 2025년11월3일부터 초기4.170%·유지2.780%,12월1일 동일 유지라는 당시 공식 공지 기준입니다. 현물편도0.05%, 선물계약당편도600원+명목0.0003157%, 각 레그편도2bp, 롤 양쪽 비용 유지. 역배 차입비용을 0원으로 확인한 것이 아니며 미포함·미검증입니다.','',
'2026년은 1월2일~10월15일의 승인된 탐색 자료이며, 2025년은 전체 연도가 아닌11~12월 부분기간입니다. 2026년 첫 야간497행의 실제 달력날짜가2025년12월30~31일이지만 거래일은20260102라2025년 검증에서는 제외했습니다. 기존2025년 일봉 연구 이력이 있어2025년 전체가 미사용이었다고 단정하지 않습니다.','',
'기존 원본·전략·Gateway·OpenClaw·예약 작업·수집기·Final OOS를 수정하지 않았고 실제 주문은 없습니다. 신규 스윕이나 최적화도 하지 않았습니다.','',
'공식 근거: [KIS 분봉 API](https://github.com/koreainvestment/open-trading-api/tree/main/examples_llm/domestic_futureoption/inquire_time_fuopchartprice), [2025년11월 증거금](https://www.next-securities.com/board/boardDetail.do?bbsCategory=NT01&bbsId=BBSMSTR_000000000240&content=4000383&nttId=12140), [2025년 수능일 시간변경](https://kind.krx.co.kr/external/2025/10/30/000120/20251028001558/70869.htm).','',
'공통 원본·엔진은 반복 업로드하지 않고 strategy_code_ref.json으로 버전과 해시를 참조합니다. 원시 시장 자료는 D에 보존하므로 GitHub 자료만으로 원시가격 재수집 없이 완전 재현할 수 있다고 주장하지 않습니다.']
(OUT/'REPORT_KO.md').write_text('\n'.join(lines)+'\n',encoding='utf8')
(OUT/'README_KO.md').write_text('D 전용 새 연구폴더에서 공통 코드는 strategy_code_ref.json의 고정 커밋·SHA로 가져옵니다. 고정 조건은 preregistration/fixed_variants.json. 기존 원본 경로는 data_audit/input_inventory_sha256.csv. 먼저 data_audit.py, compare_2026.py로 기준 대조, collect_2025_night.py와 collect_roll_quotes.py로 가격을 확보합니다. validate_partial.py는 코드·입력 해시를 확인하며 두 고정 규칙만 한 번 실행합니다. 기존 출력이 있으면 새 폴더에서 수행하십시오. bootstrap.py는 공유 코드 버전을 사용해 TEMP/TMP/캐시를 D로 고정합니다. API 인증정보는 로컬 .env에서만 로딩하고 게시하지 않습니다. 이번 결과는 2025년 전체 검증이 아닙니다.\n',encoding='utf8')
print(json.dumps(dict(status='PACKAGE_READY',files=sum(p.is_file() for p in OUT.rglob('*')),partial=partial),ensure_ascii=False))
