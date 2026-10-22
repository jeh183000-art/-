from pathlib import Path
import csv,json,hashlib,shutil,sys,platform
ROOT=Path(__file__).resolve().parents[1];TRIAL=ROOT/'trial';OUT=ROOT/'publish_payloads/nine_day_test_v1';OUT.mkdir(parents=True)
EXPECTED=[('20250110','175W01'),('20250212','175W02'),('20250312','175W03'),('20250410','175W04'),('20250514','175W05'),('20250612','175W06'),('20250710','175W07'),('20250813','175W08'),('20250911','175W09')]
def read(n):return list(csv.DictReader((TRIAL/n).open(encoding='utf8')))
def js(n,x):
 with (OUT/n).open('x',encoding='utf8') as f:json.dump(x,f,ensure_ascii=False,indent=2)
def cp(p,target):
 q=OUT/target;q.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,q)
def table(n,rows,fields):
 with (OUT/n).open('x',encoding='utf8',newline='') as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
results=read('results.csv');requests=read('api_requests.csv');summary=json.loads((TRIAL/'summary.json').read_text());settings=json.loads((TRIAL/'settings.json').read_text())
assert [(r['query_date'],r['contract_code']) for r in results]==EXPECTED
assert summary['queried_dates']==9 and summary['other_dates_requested']==0 and summary['minute_api_calls']==len(requests)
assert set((r['date'],r['contract']) for r in requests)==set(EXPECTED)
assert summary['auth_success'] and all(r['status']=='EMPTY_RESPONSE' and r['bars']=='0' and r['http_status']=='200' and r['rt_cd']=='0' and r['msg_cd']=='MCA00000' for r in results)
rawfiles=sorted((TRIAL/'raw_responses').glob('*.json'));assert len(rawfiles)==9
for p in rawfiles:
 obj=json.loads(p.read_text());params=obj['request_parameters'];assert (params['FID_INPUT_DATE_1'],params['FID_INPUT_ISCD']) in EXPECTED
 assert params['FID_COND_MRKT_DIV_CODE']=='CF' and params['FID_HOUR_CLS_CODE']=='60' and params['FID_PW_DATA_INCU_YN']=='Y' and params['FID_FAKE_TICK_INCU_YN']=='N'
 assert obj['response']['output2']==[]
 assert not {'authorization','appkey','appsecret'}&set(obj)
 cp(p,'raw_responses/'+p.name)
for n in ['results.csv','api_requests.csv','summary.json','settings.json','authentication_status.json']:cp(TRIAL/n,n)
cp(ROOT/'code/probe_nine_days.py','code/probe_nine_days.py');cp(ROOT/'code/package_probe.py','code/package_probe.py');cp(ROOT/'code/bootstrap.py','code/bootstrap.py')
source=Path(settings['source_collector_path']);assert hashlib.sha256(source.read_bytes()).hexdigest()==settings['source_collector_sha256'];cp(source,'code/existing_collector_snapshot.py')
js('validation.json',dict(status='PASS_RESPONSE_AND_SCOPE_AUDIT',requested_dates=9,queried_dates=9,successful_price_days=0,returned_bars=0,all_requests_within_allowlist=True,raw_response_counts_match_results=True,raw_response_files=9,ohlcv_checks='NOT_APPLICABLE_NO_ROWS',duplicate_bar_checks='NOT_APPLICABLE_NO_ROWS',source_collector_sha256_unchanged=True,market_requests_outside_allowlist=0,no_backtest=True,no_orders=True,no_protected_oos_access=True))
js('provenance.json',dict(mode='EXACTLY_NINE_DAY_KIS_REGULAR_MINUTE_PROBE',source='KIS official production quotation API',token_material_published=False,credentials_published=False,official_contract_validation='Existing KRX per-day contract_selection.csv: requested code matches, official volume positive',input_data_reused=False,other_dates_requested=0,old_results_overwritten=False,source_collector_sha256=settings['source_collector_sha256'],request_parameters_comparison='Existing successful CF/60/Y/N/154500 collector reused unchanged through guarded requests.get',network_scope='one REST authentication plus9minute-quote requests; no other market date requested'))
js('environment.json',dict(python=sys.version,platform=platform.platform(),storage_root=str(ROOT),temporary_and_cache='process-scoped D runtime directories',packages_changed=False))
js('checkpoint.json',dict(status='LOCAL_COMPLETE_PENDING_REMOTE_VERIFICATION',requested_dates=9,finished_dates=9,successful_days=0,total_bars=0,next_date=None,worker_running=False))
js('strategy_code_ref.json',dict(task='DATA_PROBE_ONLY_NO_STRATEGY',entrypoint='code/probe_nine_days.py',existing_collector_snapshot='code/existing_collector_snapshot.py',snapshot_sha256=settings['source_collector_sha256'],instruction='Only run the guarded probe entrypoint. Snapshot is evidence of the existing collector, not an instruction to run its full-year main.'))
table('fills.csv',[],['status','reason']);table('costs.csv',[dict(status='NOT_APPLICABLE',reason='No orders or backtest executed; quote API test only')],['status','reason'])
text=['# 2025년 KRX 미국달러선물 월별 지정1일·총9일 시험 조회','',
'기존 KIS 실전 REST 인증은 성공했습니다.',
'사용자가 지정한1~9월의9거래일만 정확히 조회했습니다.',
'9일 모두 HTTP200·rt_cd0·MCA00000 정상처리 응답입니다.',
'하지만9일 모두 output2가 비어 실제 확보한1분봉은0개입니다.',
'첫 페이지가 비어 있으므로 이전 날짜로 넘어가거나 임의로 가격을 만들지 않았습니다.',
'이9일의 빈 응답으로 해당 월 전체 또는 모든 KIS 과거자료가 불가능하다고 단정하지 않습니다.',
'백테스트·전략 스윕·실제 주문·Gateway 변경·보호 Final OOS 접근은 없습니다.','',
'|월|조회 날짜|KIS 코드|HTTP/rt_cd/msg_cd|수집 봉|최초|마지막|가격 수집 성공|',
'|---|---|---|---|---:|---|---|---|']
for r in results:
 d=r['query_date'];date=d[:4]+'-'+d[4:6]+'-'+d[6:];text.append('|'+r['month']+'|'+date+'|'+r['contract_code']+'|'+r['http_status']+'/'+r['rt_cd']+'/'+r['msg_cd']+'|'+r['bars']+'|—|—|아니오: EMPTY_RESPONSE|')
text+=['','실제 가격 수집 성공0/9거래일, 수집0봉. HTTP/API 정상처리9/9와 가격 수집 성공은 구분합니다. 오류 메시지는 모두 “정상처리 되었습니다.”이며 별도 KIS 오류코드는 없습니다. 인증 실패나 접근 거절로 분류하지 않았습니다. 빈 응답의 공식 보관기간 원인은 이번 시험만으로 확정하지 않습니다.','',
'API: /uapi/domestic-futureoption/v1/quotations/inquire-time-fuopchartprice, TR FHKIF03020200. 기존 성공 코드의 CF(상품선물),60(1분),과거포함Y,허봉N,초기커서154500을 그대로 사용했습니다. 기존 수집기의 최소반환시각−1분 페이지네이션과 최대7페이지·반복커서 방지도 유지했습니다. 이번에는 날짜별 첫 페이지가0행이라 실제 시세요청은9회였습니다. 요청 간격은 최소1.2초로 제한하고 토큰은 한 번 발급해 재사용했습니다.','',
'요청 종목은 기존 KRX 공식 거래자료의 해당 날짜 월물·양수 거래량과 대조했습니다. 그 자료의 공식 종가는 결과 CSV에 참고로 기록했지만 KIS 분봉을 받은 것으로 계산하지 않았습니다. 신규 날짜·다른 월물·다른 시장·야간장 요청은 추가하지 않았습니다.','',
'9개의 raw_responses JSON은 실제 API 응답이며 요청 헤더·인증정보·토큰 응답은 포함하지 않습니다. 값이 없는 날짜에는 가짜 가격 CSV를 생성하지 않았습니다. results.csv와 api_requests.csv 및 validation.json을 상호 대조했습니다. OHLCV·중복 검사는 실제 가격행이 없어 검사 대상이 없다고 표시합니다.','',
'재현: 기존 D 환경에서 code/bootstrap.py probe_nine_days.py를 실행합니다. 출력 폴더는 신규 위치여야 하며 기존 파일이 있으면 덮어쓰지 않고 종료합니다. KIS 자격정보는 기존 로컬 설정에서만 읽습니다. code/existing_collector_snapshot.py는 사용한 기존 코드의 해시 일치 증빙이며 전체연도 main을 실행하라는 의미가 아닙니다. 이번 재현 진입점은9일 허용목록을 강제합니다.','',
'출력 경로: '+str(ROOT),'',
'기존 시장자료·연구결과·인증파일은 수정하지 않았습니다. C에 대용량 출력을 만들지 않았습니다. 이번 결과는 지정9일에 한정됩니다.']
(OUT/'REPORT_KO.md').write_text('\n'.join(text)+'\n',encoding='utf8')
print(json.dumps(dict(status='LOCAL_RESPONSE_AUDIT_PASS',dates=9,successful_days=0,minute_bars=0,payload=str(OUT))))
