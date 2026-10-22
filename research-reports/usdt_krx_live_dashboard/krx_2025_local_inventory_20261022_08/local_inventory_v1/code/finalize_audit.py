from pathlib import Path
import csv,json,collections,hashlib,shutil,platform,sys
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'publish_payloads/local_inventory_v1';OUT.mkdir(parents=True)
def read(p):return list(csv.DictReader(p.open(encoding='utf-8-sig')))
def table(p,rows,fields=None):
 with p.open('w',encoding='utf8',newline='') as f:w=csv.DictWriter(f,fieldnames=fields or (list(rows[0]) if rows else ['status']));w.writeheader();w.writerows(rows)
def js(n,x):(OUT/n).write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding='utf8')
def copy(p,n=None):
 q=OUT/(n or p.name);q.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,q)
audit=json.loads((ROOT/'audit/summary.json').read_text());inventory=json.loads((ROOT/'inventory/summary.json').read_text());sources=read(ROOT/'audit/file_audit.csv');monthly=read(ROOT/'audit/monthly_union.csv');bars=read(ROOT/'audit/verified_union_copy.csv');actual=[r for r in sources if int(r['rows_2025'])>0]
master=Path(r'D:/Codex_Research/archive/c_drive_migration_20261020/codex_workspace/files-pasted-by-the-user-codex/outputs/usdt_krx_live_dashboard/data/krx_2025_full_1m')
expected=read(master/'contract_selection.csv');observed={r['business_date'] for r in bars if r['session']=='regular'}
coverage=[dict(date=r['date'],contract_code_krx=r['contract_code_krx'],contract_code_kis=r['contract_code_kis'],observed_regular=r['date'] in observed,status='OBSERVED_PARTIAL_OR_UNVERIFIED_COMPLETENESS' if r['date'] in observed else 'NOT_FOUND_IN_LOCAL_SEARCH') for r in expected]
table(OUT/'official_day_coverage.csv',coverage)
groups=collections.defaultdict(list)
for r in actual:groups[r['sha256']].append((r['archive']+'!' if r['archive'] else '')+r['path'])
table(OUT/'identical_file_groups.csv',[dict(sha256=h,files=len(v),paths=json.dumps(v,ensure_ascii=False)) for h,v in groups.items() if len(v)>1])
rows=sorted(bars,key=lambda r:(r['business_date'],r['timestamp_kst'],r['contract_code'],r['session']))
# Validate a new copy without changing any source.
assert audit['conflicts']==0
assert all(float(r['high'])>=max(float(r['open']),float(r['close'])) and float(r['low'])<=min(float(r['open']),float(r['close'])) and float(r['volume'])>=0 for r in rows)
contracts=[]
for code in sorted({r['contract_code'] for r in rows}):
 b=[r for r in rows if r['contract_code']==code];contracts.append(dict(contract=code,first=min(r['timestamp_kst'] for r in b),last=max(r['timestamp_kst'] for r in b),rows=len(b),business_dates=len({r['business_date'] for r in b})))
table(OUT/'contract_coverage.csv',contracts)
copy(ROOT/'audit/file_audit.csv');copy(ROOT/'audit/per_source_monthly.csv');copy(ROOT/'audit/monthly_union.csv','results.csv');copy(ROOT/'audit/unobserved_intervals.csv');copy(ROOT/'audit/unlabelled_date_metadata.csv');copy(ROOT/'inventory/archive_index_summary.csv');copy(ROOT/'inventory/archive_candidates.csv')
for name in ['inventory_files.py','index_archives.py','audit_sources.py','audit_unlabelled_dates.py','finalize_audit.py']:copy(ROOT/'code'/name,'code/'+name)
script=master/'finalize_krx_2025_full.py';lines=script.read_text(encoding='utf8').splitlines();evidence=[]
for i,l in enumerate(lines,1):
 if any(x in l for x in ['all_bars.extend(bars)','KRX_USD_1m_2025_01_01_to_2025_12_31.csv','summary_status == "UNAVAILABLE"','Representative mid-month']):evidence.append(dict(line=i,code=l.strip()))
js('filename_cause_evidence.json',dict(file=str(script),sha256=hashlib.sha256(script.read_bytes()).hexdigest(),evidence=evidence,conclusion='The year-range filename is hard-coded; rows are only concatenated from existing monthly results. Empty Jan-Sep months are not synthesized or a guarantee of successful collection.'))
# Publish status logs/summary evidence; never publish raw logs or credentials.
copy(master/'monthly_results.csv','original_collection_monthly_status.csv');copy(master/'annual_summary.json','original_collection_annual_summary.json')
copy(master/'investigation_sep_oct_2025/date_by_date_results.csv','original_api_date_probe_status.csv')
unionpath=ROOT/'audit/verified_union_copy.csv'
js('provenance.json',dict(search_roots=inventory['roots'],source_audit=audit,archive_members=439713,archives=72,unlabelled_file_date_checks=207,unique_content_bar_files=len(groups),full_year_continuity=False,downloads=False,raw_source_files_modified=False,protected_oos_contents_read=False,private_metadata='all_file_metadata.csv and archive_member_metadata.csv remain D-only; names in system backups and unrelated projects are not published',input_reproduction='INPUT_NOT_REMOTELY_REPRODUCIBLE: raw merged market data stays D-only',new_verified_union=dict(path=str(unionpath),bytes=unionpath.stat().st_size,sha256=hashlib.sha256(unionpath.read_bytes()).hexdigest()),strategy='No B validation run: full-year continuity prerequisite not satisfied'))
js('settings.json',dict(task='LOCAL_FILE_AUDIT_ONLY',no_download=True,no_delete=True,no_overwrite_originals=True,protected_oos_excluded=True,merge_key=['business_date','timestamp_kst','contract_code','session'],ohlcv_conflicts='STOP_NOT_AUTO_RESOLVE',backtest_gate='Full 2025 continuity required; gate not passed'))
js('environment.json',dict(python=sys.version,platform=platform.platform(),storage_root=str(ROOT),network_market_requests=0,packages_changed=False))
js('checkpoint.json',dict(status='LOCAL_AUDIT_COMPLETE_PENDING_REMOTE_VERIFICATION',missing_months=['2025-'+str(m).zfill(2) for m in range(1,10)],full_year_backtest_started=False,worker_running=False))
js('strategy_code_ref.json',dict(task='NO_STRATEGY_EXECUTION',source='code/*.py contains this audit only',fixed_B_preserved_commit='c63352755d43b067b2124e748297efe6cbf6ecbf',fixed_variant_registration_commit='25d0945bc68a1c7fbc2be72741f9749885e1df5d'))
table(OUT/'fills.csv',[],['status','reason']);table(OUT/'costs.csv',[dict(status='NOT_APPLICABLE',reason='No strategy executed; local audit only')])
js('validation.json',dict(status='PASS_LOCAL_SOURCE_INVENTORY',full_year_continuity='NOT_CONFIRMED',ohlcv_conflicts=0,downloads=0,original_mutations=0,backtest_executions=0,actual_bar_sources=len(actual),files_with_ohlc_errors=sum(int(r['ohlc_errors'])>0 for r in actual),protected_price_files_opened=0))
regular=[r for r in bars if r['session']=='regular'];night=[r for r in bars if r['session']=='night']
text=['# 2025 KRX 미국달러선물 원본 전수 검색 결과','',
'지정한 D 연구 루트와 C 기존 연구 폴더의90,671개 파일을 메타데이터로 조사했습니다.',
'ZIP·TAR72개 내부439,713개 항목을 목록으로 확인했으며 원본을 추출·변경하지 않았습니다.',
'현재 검색 범위에서는2025년1~9월 미국달러선물 실제1분봉을 찾지 못했습니다.',
'전체 연도 파일명은 성공 범위가 아니라 요청 범위를 고정한 이름이었습니다.',
'월별·일별 원본과 앱 사본을 대조했고, 추가로 다음 월물 롤오버 가격822봉을 확인했습니다.',
'고유 계약별 행을 새 검증 사본으로 저장했지만2025년 전체 연속성은 확인되지 않았습니다.',
'따라서 B를 다시 실행하거나2025년 전체 연도 수익률을 계산하지 않았습니다.','',
'|월|정규장 거래일|정규장 계약별 행|야간 세션|야간 계약별 행|','|---|---:|---:|---:|---:|']
for r in monthly:text.append('|'+r['month']+'|'+r['regular_days']+'|'+r['regular_rows']+'|'+r['night_sessions']+'|'+r['night_rows']+'|')
text+=['',f'총 정규장{len(regular):,} 계약별 행·{len(observed)}거래일, 야간{len(night):,} 계약별 행. 정규장 날짜 기준 공식242일 중183일 자료가 검색되지 않았습니다. 같은 시각에 서로 다른 월물이 있으면 별도 행으로 보존하며, 이를 추가 거래일 또는 같은 계약의 중복으로 세지 않습니다.','',
'주요 위치:','',str(master),'',r'D:\Codex_Research\usdt_krx_live_dashboard\app\data\krx_2025_full_1m','',
'두 폴더의 연간 파일과 월별·일별 파일들은 SHA-256별로 identical_file_groups.csv에서 확인할 수 있습니다. 날짜·계약·OHLCV가 같은 중복 봉은 병합 사본에서 제거했습니다. 상충 OHLCV는0건입니다. 다른 연구의 결과·체결 원장을 시장 원본으로 취급하지 않았습니다.','',
'1~9월 월별 파일은 실제 가격행이 없는 파일도 포함합니다. original_collection_monthly_status.csv는 대표일 요청0행 및 다른 날짜 미요청 상태를 기록합니다. 기존 수집 코드는 UNAVAILABLE 월도 처리한 후 확보된 월별 rows만 all_bars에 추가하고, 연간 출력명을 고정했습니다. 이 때문에 파일명과 실제 보유 범위가 달라졌습니다. filename_cause_evidence.json에 코드 SHA와 줄 번호를 보존했습니다. 이 과거 응답의 원인을 공식 보관기간 제한이라고 확정하지 않습니다.','',
'새 사본의 정규장11월8,288행·12월8,740행에는 기존7,877·8,329행 외에 각411행씩의 다음 월물이 포함됩니다. 이822행은 이전 고정 B 부분검증에 사용한 롤오버용 원본이며 새 다운로드가 아닙니다. 같은 계약의 누락된1~9월 봉을 복구한 것은 아닙니다.','',
'연도가 없는 파일207개는 날짜 열만 점검했습니다. 발견된 달력2025년12월30일 야간 라벨은2026년 첫 거래일 경계 자료이며2025 거래일 자료로 병합하지 않았습니다. Eurex 거래나 USD/KRW 현물환율·업비트 테더·일봉을 미국달러선물1분봉으로 대체하지 않았습니다.','',
'분봉이 없는 구간은 unobserved_intervals.csv에 관측 공백으로 기록했습니다. 장마감 단일가·실제 무거래·API 누락 가능성을 확정적으로 한 종류로 분류하지 않았고 보간하지 않았습니다. 종가 일치만으로 완전성을 확정하지 않습니다.','',
'압축파일 목록과 시스템 백업 내부 파일명 전체는 개인정보 보호를 위해 D에만 보존합니다. GitHub에는 관련 자료별 해시·기간·월별 통계와 압축파일별 목록 조사 결과만 게시합니다. 보호 Final OOS 파일 내용·인증정보·SQLite·WSL 원본은 게시하거나 변경하지 않았습니다.','',
'결과 사본: '+str(unionpath),'',
'현재 범위에서 미발견이라는 결론이며 PC의 다른 미지정 드라이브·폴더 또는 외부 저장소에도 자료가 없다는 뜻은 아닙니다. 전체연도 연속성 조건이 충족되지 않아 B 재검증은 실행하지 않았습니다.']
(OUT/'REPORT_KO.md').write_text('\n'.join(text)+'\n',encoding='utf8')
print(json.dumps(dict(payload=str(OUT),source_files=len(sources),actual_bar_sources=len(actual),unique_bar_file_hashes=len(groups),regular_contract_rows=len(regular),night_contract_rows=len(night),regular_days=len(observed),full_year=False)))
