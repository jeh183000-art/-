from pathlib import Path
import csv,json,hashlib,shutil,sys,platform,zipfile,datetime,collections
ROOT=Path(__file__).resolve().parents[1];T=ROOT/'trial';OUT=ROOT/'publish_payloads/nine_day_test_v2';OUT.mkdir(parents=True)
EXPECTED=[('20260109','A75601'),('20260212','A75602'),('20260312','A75603'),('20260410','A75604'),('20260514','A75605'),('20260612','A75606'),('20260710','A75607'),('20260813','A75608'),('20260911','A75609')]
def read(p):return list(csv.DictReader(p.open(encoding='utf-8-sig')))
def js(n,x):
 with (OUT/n).open('x',encoding='utf8') as f:json.dump(x,f,ensure_ascii=False,indent=2)
def table(n,rows,fields=None):
 with (OUT/n).open('x',encoding='utf8',newline='') as f:w=csv.DictWriter(f,fieldnames=fields or list(rows[0]));w.writeheader();w.writerows(rows)
def cp(p,n):
 q=OUT/n;q.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,q)
r=read(T/'results.csv');req=read(T/'api_requests.csv');summary=json.loads((T/'summary.json').read_text());settings=json.loads((T/'settings.json').read_text())
assert [(x['query_date'],x['contract_code']) for x in r]==EXPECTED
assert set((x['date'],x['contract']) for x in req)==set(EXPECTED) and summary['other_dates_requested']==0
pages=list((T/'raw_responses').glob('*.json'));assert len(pages)==len(req)
raw_by_day=collections.defaultdict(dict);archive_members=[];excluded=0
with zipfile.ZipFile(OUT/'raw_responses.zip','x',compression=zipfile.ZIP_DEFLATED) as z:
 for p in sorted(pages):
  b=p.read_bytes();o=json.loads(b);params=o['request_parameters'];d=params['FID_INPUT_DATE_1'];c=params['FID_INPUT_ISCD'];assert (d,c) in EXPECTED
  assert params['FID_COND_MRKT_DIV_CODE']=='CF' and params['FID_HOUR_CLS_CODE']=='60' and params['FID_PW_DATA_INCU_YN']=='Y' and params['FID_FAKE_TICK_INCU_YN']=='N'
  excluded+=o['out_of_scope_rows_excluded']
  for x in o['response'].get('output2',[]):
   assert x['stck_bsop_date']==d
   key=x['stck_cntg_hour'];old=raw_by_day[d].get(key)
   if old is not None:assert old==x
   raw_by_day[d][key]=x
  z.writestr(p.name,b);archive_members.append(dict(path=p.name,bytes=len(b),sha256=hashlib.sha256(b).hexdigest()))
with zipfile.ZipFile(OUT/'raw_responses.zip') as z:
 for x in archive_members:assert hashlib.sha256(z.read(x['path'])).hexdigest()==x['sha256']
table('raw_response_members_sha256.csv',archive_members)
quality=[];gaps=[]
contracts_path=Path(r'D:/Codex_Research/archive/c_drive_migration_20261020/codex_workspace/files-pasted-by-the-user-codex/outputs/usdt_krx_live_dashboard/data/krx_2026_full_1m/contract_selection.csv');official={x['date']:x for x in read(contracts_path)}
for x in r:
 d=x['query_date'];c=x['contract_code'];bars=read(T/x['data_file']) if x['data_file'] else [];assert len(bars)==int(x['bars'])==len(raw_by_day[d])
 times=[]
 for b in bars:
  assert b['trade_date']==d and b['contract_code_kis']==c and b['contract_code_krx']==official[d]['contract_code_krx']
  raw=raw_by_day[d][b['time_kst']]
  for a,k in [('open','futs_oprc'),('high','futs_hgpr'),('low','futs_lwpr'),('close','futs_prpr'),('volume','cntg_vol')]:assert float(b[a])==float(raw[k])
  op,hi,lo,cl,vol=[float(b[k]) for k in ['open','high','low','close','volume']];assert hi>=max(op,cl) and lo<=min(op,cl) and hi>=lo and min(op,hi,lo,cl)>0 and vol>=0
  times.append(b['time_kst'])
 assert len(set(times))==len(times) and times==sorted(times)
 if bars:
  assert abs(float(bars[-1]['close'])-float(official[d]['official_close']))<1e-7
  cp(T/x['data_file'],x['data_file'])
 for a,b in zip(times,times[1:]):
  diff=int((datetime.datetime.strptime(b,'%H%M%S')-datetime.datetime.strptime(a,'%H%M%S')).total_seconds()/60)
  if diff>1:gaps.append(dict(date=d,previous=a,next=b,unobserved_labels=diff-1,classification='CLOSING_CALL_AUCTION_LABEL_WINDOW' if (a,b)==('153400','154500') else 'UNOBSERVED_NO_TRADE_VS_API_OMISSION_UNCONFIRMED'))
 volsum=sum(float(b['volume']) for b in bars);ov=float(official[d]['official_volume'])
 quality.append(dict(date=d,contract=c,bars=len(bars),first=times[0] if times else '',last=times[-1] if times else '',ohlc_errors=0,duplicate_keys=0,api_csv_numeric_mismatches=0,official_close_match=bool(bars),minute_volume_sum=volsum,official_daily_volume=ov,volume_match=volsum==ov,completeness='PRICE_ROWS_RECEIVED_NOT_ALL_TRADES_CERTIFIED'))
for n in ['results.csv','api_requests.csv','summary.json','settings.json','authentication_status.json']:cp(T/n,n)
for name in ['probe_nine_days.py','package_probe_2026.py']:cp(ROOT/'code'/name,'code/'+name)
table('quality.csv',quality);table('unobserved_labels.csv',gaps,['date','previous','next','unobserved_labels','classification'])
js('validation.json',dict(status='PASS_TARGET_DATE_SCOPE_RAW_CSV_OHLCV_DUPLICATE_CLOSE_AUDIT',dates_queried=9,successful_dates=summary['successful_dates'],bars=summary['total_bars'],raw_response_pages=len(pages),out_of_scope_response_rows_excluded_from_storage=excluded,all_requests_within_allowlist=True,no_additional_query_dates=True,raw_archive_member_hashes_verified=True,volume_matches=sum(q['volume_match'] for q in quality),official_close_matches=sum(q['official_close_match'] for q in quality),ohlc_errors=0,duplicates=0,no_strategy_execution=True,no_orders=True,protected_oos_files_accessed=False))
js('environment.json',dict(python=sys.version,platform=platform.platform(),storage_root=str(ROOT),temporary_cache='D process-scoped runtime directories',packages_changed=False))
js('provenance.json',dict(provider='KIS official production quote API',source_collector_sha256=settings['source_collector_sha256'],contract_metadata_sha256=hashlib.sha256(contracts_path.read_bytes()).hexdigest(),date_adjustment=settings['date_adjustment'],scope='Regular session only,9specified2026dates; no full-year inference',credentials_or_token_published=False,raw='Parsed/redacted API responses; retain only requested-date output2 price rows and output1 identity. Archive is lossless for saved page JSON.',previous_2025_probe_commit='2d255cece9f357e6bf1667dabb004805b02af430',protected_oos_accessed=False,existing_files_modified=False))
js('strategy_code_ref.json',dict(mode='DATA_PROBE_NO_STRATEGY',existing_collector=dict(commit='2d255cece9f357e6bf1667dabb004805b02af430',path='research-reports/usdt_krx_live_dashboard/krx_2025_nine_day_probe_20261022_09/nine_day_test_v1/code/existing_collector_snapshot.py',sha256=settings['source_collector_sha256']),bootstrap=dict(commit='2d255cece9f357e6bf1667dabb004805b02af430',path='research-reports/usdt_krx_live_dashboard/krx_2025_nine_day_probe_20261022_09/nine_day_test_v1/code/bootstrap.py'),guarded_entrypoint='code/probe_nine_days.py'))
js('checkpoint.json',dict(status='LOCAL_COMPLETE_PENDING_REMOTE_VERIFICATION',dates_complete=9,successful_dates=summary['successful_dates'],bars=summary['total_bars'],next_date=None,worker_running=False))
table('fills.csv',[],['status','reason']);table('costs.csv',[dict(status='NOT_APPLICABLE',reason='Market data probe only; no orders or backtest')])
text=['# 2026년1~9월 월별 하루·총9거래일 KIS 분봉 다운로드 시험','',
'앞선2025년 시험과 같은 방식으로2026년1~9월을 월별 하루씩 조회했습니다.',
'1월10일은 토요일이라 가장 가까운 공식 거래일1월9일을 사용했습니다.',
'나머지는 앞선 시험과 같은 월·일을 유지하고 당시 실제 A756xx 월물을 확인했습니다.',
f"실제 분봉 수집 성공은{summary['successful_dates']}/9거래일, 총{summary['total_bars']:,}봉입니다.",
'HTTP 성공 여부와 실제 가격 수신·OHLCV 검증을 분리했습니다.',
'지정일 밖 가격이 API 응답에 섞인 경우 행 수만 기록하고 해당 가격은 저장하지 않았습니다.',
'전체 연도 수집·전략 분석·백테스트·실제 주문·Gateway 변경은 하지 않았습니다.','',
'|월|조회일|종목|HTTP/rt_cd/msg_cd|분봉|최초|마지막|수집|','|---|---|---|---|---:|---|---|---|']
for x in r:
 d=x['query_date'];text.append('|'+x['month']+'|'+d[:4]+'-'+d[4:6]+'-'+d[6:]+'|'+x['contract_code']+'|'+x['http_status']+'/'+x['rt_cd']+'/'+x['msg_cd']+'|'+x['bars']+'|'+x['first_time']+'|'+x['last_time']+'|'+x['status']+'|')
text+=['',
'기존 CF(상품선물),60(1분),과거포함Y,허봉N,초기154500커서를 유지했습니다. 각 페이지 최소시각−1분 커서로 이어받았으며 반복커서·최대7페이지 방지도 유지했습니다. API 제한을 고려해 요청 간격을 최소1.2초로 제한하고 인증 토큰은 한 번만 발급해 재사용했습니다. 기존 KRX 공식 계약 선택 자료로 월물·만기·양수 거래량을 확인했습니다.','',
f"원본 대상행과 CSV의 OHLCV 수치·날짜·종목·중복을 독립 대조했습니다. 공식 종가 일치{sum(q['official_close_match'] for q in quality)}/9일, 공식 일별 거래량과 분봉 거래량 합계 일치{sum(q['volume_match'] for q in quality)}/9일입니다. 거래량 차이는 quality.csv에 남겼으며 임의 분배하지 않았습니다. 가격행 수신 성공은 전체 체결의 완전성이나 실제 주문 체결 검증을 뜻하지 않습니다.",
'',
'15:34에서15:45로 넘어가는 분 라벨 공백은 장마감 단일가 구간으로 별도 기록했습니다. 그 밖의 공백이 있으면 실제 무거래와 API 누락을 확정하지 않고 그대로 보존합니다. 어떤 분봉도 임의 생성하거나 보간하지 않았습니다.','',
f"조회 요청은9개 날짜에만 제한했습니다. 과거포함Y 때문에 응답에 섞인 범위 밖{excluded}행의 가격은 저장·분석하지 않았습니다. raw_responses.zip에는 대상 날짜로 제한한 페이지 JSON을 원래 저장 바이트 그대로 압축했고, raw_response_members_sha256.csv로 내부 파일을 재검증했습니다. 요청 헤더·앱키·시크릿·토큰은 게시하지 않았습니다.",
'',
'2025년9일 시험의0행과 달리2026년 지정일에서는 실제 가격이 반환되는지 확인하는 자료입니다. 이 결과만으로2026년 모든 날짜의 제공 여부나2025년 미제공 원인·공식 보관기간을 단정하지 않습니다.','',
'원본과 생성 파일은 신규 D 폴더에 보존합니다: '+str(ROOT),'',
'재현은 고정된 bootstrap과 기존 collector를 strategy_code_ref.json의 커밋·해시에서 확인한 뒤 신규 D 폴더에서 guarded probe_nine_days.py만 실행합니다. 원본 collector의 전체연도 main을 실행하지 마십시오. 기존 결과가 있으면 덮어쓰지 않고 중단합니다. 기존 연구·Final OOS 보호·Gateway·수집기는 변경하지 않았습니다.']
(OUT/'REPORT_KO.md').write_text('\n'.join(text)+'\n',encoding='utf8')
print(json.dumps(dict(status='LOCAL_AUDIT_PASS',dates=9,successful=summary['successful_dates'],bars=summary['total_bars'],price_pages=len(pages),volume_matches=sum(q['volume_match'] for q in quality))))
