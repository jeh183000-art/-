from __future__ import annotations
from pathlib import Path
import csv,json,time,hashlib,importlib.util,sys,math,platform
ROOT=Path(__file__).resolve().parents[1]
SOURCE=Path(r'D:/Codex_Research/archive/c_drive_migration_20261020/codex_workspace/files-pasted-by-the-user-codex/outputs/usdt_krx_live_dashboard/data/krx_2025_full_1m/krx_2025_month_collector.py')
PLAN=[('20260109','A75601'),('20260212','A75602'),('20260312','A75603'),('20260410','A75604'),('20260514','A75605'),('20260612','A75606'),('20260710','A75607'),('20260813','A75608'),('20260911','A75609')]
ALLOWED=set(PLAN);OUT=ROOT/'trial';OUT.mkdir(exist_ok=True);(OUT/'raw_responses').mkdir(exist_ok=True);(OUT/'daily').mkdir(exist_ok=True)
def save(p,x):
 with p.open('x',encoding='utf8') as f:json.dump(x,f,ensure_ascii=False,indent=2)
def table(p,rows,fields=None):
 with p.open('x',encoding='utf8',newline='') as f:
  w=csv.DictWriter(f,fieldnames=fields or list(rows[0]));w.writeheader();w.writerows(rows)
spec=importlib.util.spec_from_file_location('existing_successful_kis_regular_collector',SOURCE);c=importlib.util.module_from_spec(spec);sys.modules[spec.name]=c;spec.loader.exec_module(c)
source_hash=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
contracts={r['date']:r for r in c.read_csv(SOURCE.parent.parent/'krx_2026_full_1m/contract_selection.csv')}
assert len(PLAN)==9 and len({d for d,_ in PLAN})==9
for d,code in PLAN:assert contracts[d]['contract_code_kis']==code and float(contracts[d]['official_volume'])>0
settings=dict(dates=[dict(date=d,code=code,official_krx_code=contracts[d]['contract_code_krx'],official_name=contracts[d]['contract_name'],official_volume=contracts[d]['official_volume']) for d,code in PLAN],endpoint=c.KIS_URL,tr_id='FHKIF03020200',parameters=dict(FID_COND_MRKT_DIV_CODE='CF',FID_HOUR_CLS_CODE='60',FID_PW_DATA_INCU_YN='Y',FID_FAKE_TICK_INCU_YN='N',initial_cursor='154500'),pagination='existing fetch_day; 102 rows/page; previous minimum timestamp minus1minute; max7pages; repeated cursor guard',source_collector_sha256=source_hash,source_collector_path=str(SOURCE),additional_dates_forbidden=True,orders_forbidden=True,date_adjustment={'20260110':'20260109','reason':'2026-01-10 Saturday; nearest verified trading date is Friday Jan9'},raw_storage='Only output2 rows matching requested day; out-of-scope price rows excluded; output1 identity fields only')
save(OUT/'settings.json',settings)
secrets=[c.KIS_APP_KEY,c.KIS_APP_SECRET];token=None
try:token,auth=c.token()
except Exception as e:auth=dict(success=False,http_status=None,error_code=type(e).__name__,error_description='Token request failed; no confidential details logged')
if token:secrets.append(token)
def red(s):
 for secret in secrets:
  if secret:s=s.replace(secret,'[REDACTED]')
 return s
def redact(obj):
 if isinstance(obj,str):return red(obj)
 if isinstance(obj,list):return [redact(x) for x in obj]
 if isinstance(obj,dict):return {k:('[REDACTED]' if k.lower() in ('access_token','appkey','appsecret','secretkey','authorization','refresh_token') else redact(v)) for k,v in obj.items()}
 return obj
save(OUT/'authentication_status.json',redact(auth))
results=[];request_log=[];last_request=0.;original_get=c.requests.get
if token:
 headers=dict(authorization='Bearer '+token,appkey=c.KIS_APP_KEY,appsecret=c.KIS_APP_SECRET,tr_id='FHKIF03020200',custtype='P',**{'content-type':'application/json; charset=utf-8'})
 def guarded_get(url,**kwargs):
  global last_request
  params=kwargs['params'];day=params['FID_INPUT_DATE_1'];code=params['FID_INPUT_ISCD'];assert url==c.KIS_URL and (day,code) in ALLOWED
  for k,v in [('FID_COND_MRKT_DIV_CODE','CF'),('FID_HOUR_CLS_CODE','60'),('FID_PW_DATA_INCU_YN','Y'),('FID_FAKE_TICK_INCU_YN','N')]:assert params[k]==v
  time.sleep(max(0,1.2-(time.monotonic()-last_request)));last_request=time.monotonic()
  response=original_get(url,**kwargs)
  try:body=response.json()
  except ValueError:body=dict(non_json_response=True)
  raw=body.get('output2') or [];idx=1+sum(x['date']==day for x in request_log)
  record=dict(date=day,contract=code,page=idx,cursor=params['FID_INPUT_HOUR_1'],http_status=response.status_code,rt_cd=body.get('rt_cd'),msg_cd=body.get('msg_cd'),message=red(str(body.get('msg1',''))),output2_rows=len(raw),target_date_rows=sum(str(r.get('stck_bsop_date',''))==day for r in raw))
  saved=dict(body);saved['output2']=[r for r in raw if str(r.get('stck_bsop_date',''))==day]
  if isinstance(saved.get('output1'),dict):saved['output1']={k:v for k,v in saved['output1'].items() if k in ('futs_shrn_iscd','hts_kor_isnm')}
  request_log.append(record);save(OUT/'raw_responses'/f'{day}_page_{idx:02}.json',dict(request_parameters=params,http_status=response.status_code,out_of_scope_rows_excluded=len(raw)-len(saved['output2']),response=redact(saved)))
  return response
 c.requests.get=guarded_get
for day,code in PLAN:
 contract=contracts[day];bars=[];meta=dict(calls=[],error='');exception=''
 if token:
  try:bars,meta=c.fetch_day(contract,headers)
  except Exception as e:exception=type(e).__name__
 pages=[r for r in request_log if r['date']==day]
 raw_target_rows=sum(r['target_date_rows'] for r in pages)
 bad=0;negative_volume=0
 for r in bars:
  prices=[float(r[k]) for k in ['open','high','low','close']];op,hi,lo,cl=prices
  bad+=not all(map(math.isfinite,prices)) or hi<max(op,cl) or lo>min(op,cl) or hi<lo or min(prices)<=0
  negative_volume+=float(r['volume'])<0
  assert r['trade_date']==day and r['contract_code_kis']==code
 unique=len({(r['trade_date'],r['time_kst'],r['contract_code_kis']) for r in bars})
 api_ok=bool(pages) and all(r['http_status']==200 and str(r['rt_cd'])=='0' for r in pages)
 count=len(bars);success=bool(count and api_ok and bad==0 and negative_volume==0 and unique==count and not meta.get('error') and not exception)
 status='DATA_READY' if success else 'PARTIAL_OR_INVALID' if count else 'EMPTY_RESPONSE' if api_ok and not meta.get('error') and not exception else 'AUTH_REQUIRED_OR_FAILED' if not token else 'ERROR'
 r=dict(month=day[:4]+'-'+day[4:6],query_date=day,contract_code=code,krx_code=contract['contract_code_krx'],http_status=pages[-1]['http_status'] if pages else auth.get('http_status'),rt_cd=pages[-1]['rt_cd'] if pages else '',msg_cd=pages[-1]['msg_cd'] if pages else auth.get('error_code',''),message=pages[-1]['message'] if pages else red(str(auth.get('error_description',''))),api_normal=api_ok,raw_response_rows=sum(x['output2_rows'] for x in pages),raw_target_rows=raw_target_rows,bars=count,first_time=bars[0]['time_kst'] if count else '',last_time=bars[-1]['time_kst'] if count else '',first_close=bars[0]['close'] if count else '',last_close=bars[-1]['close'] if count else '',official_close=contract['official_close'],official_close_match=abs(float(bars[-1]['close'])-float(contract['official_close']))<1e-7 if count else None,duplicate_rows_removed=raw_target_rows-count,remaining_duplicate_keys=count-unique,ohlc_errors=bad,negative_volume_rows=negative_volume,pages=len(pages),success=success,status=status,error=red(meta.get('error','') or exception),data_file=f'daily/{day}_{code}_regular_1m.csv' if count else '')
 if count:table(OUT/r['data_file'],bars,c.BAR_FIELDS)
 save(OUT/'daily'/f'{day}_validation.json',r);results.append(r);print(json.dumps(r,ensure_ascii=False),flush=True)
 table(OUT/f'checkpoint_after_{day}.csv',results)
assert all((r['date'],r['contract']) in ALLOWED for r in request_log)
assert hashlib.sha256(SOURCE.read_bytes()).hexdigest()==source_hash
save(OUT/'summary.json',dict(requested_dates=9,queried_dates=len({r['date'] for r in request_log}),successful_dates=sum(r['success'] for r in results),total_bars=sum(r['bars'] for r in results),minute_api_calls=len(request_log),auth_success=bool(token),other_dates_requested=0,source_collector_unchanged=True,scope='Only9specifiedtradingdays; no conclusions on entire-month availability',strategy_executions=0,protected_oos_accessed=False))
table(OUT/'results.csv',results);table(OUT/'api_requests.csv',request_log,['date','contract','page','cursor','http_status','rt_cd','msg_cd','message','output2_rows','target_date_rows']);print('NINE_DAY_TEST_COMPLETE',flush=True)
