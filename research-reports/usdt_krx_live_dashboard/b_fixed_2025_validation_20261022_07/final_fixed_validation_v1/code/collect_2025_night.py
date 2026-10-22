from pathlib import Path
import csv,json,time,re,sys,datetime,collections
import requests
ROOT=Path(__file__).resolve().parents[1]
ARCH=Path(r'D:/Codex_Research/archive/c_drive_migration_20261020/codex_workspace/files-pasted-by-the-user-codex/outputs/usdt_krx_live_dashboard')
sys.path.insert(0,str(ARCH))
from krx_live.config import KIS_APP_KEY,KIS_APP_SECRET
OUT=ROOT/'night_acquisition';OUT.mkdir(exist_ok=True);(OUT/'sessions').mkdir(exist_ok=True)
BASE='https://openapi.koreainvestment.com:9443'
def read(p):return list(csv.DictReader(p.open(encoding='utf-8-sig')))
def save(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding='utf8')
def csvout(p,rows):
 if not rows:return
 with p.open('w',encoding='utf8',newline='') as f:w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
daily=[r for r in read(ARCH/'data/archive_2025_2026/krx_daily/krx_usd_futures_daily_2025_2026.csv') if r['business_date'].startswith('2025')]
regular=sorted({r['business_date'] for r in daily if r['session']=='정규'})
prev={regular[i]:regular[i-1] for i in range(1,len(regular))}
byday=collections.defaultdict(list)
for r in daily:
 if r['session']=='야간' and float(r['volume'] or 0)>0:byday[r['business_date']].append(r)
selections=[]
for day,rs in sorted(byday.items()):
 if day not in prev:continue
 r=min(rs,key=lambda r:re.search(r'20[0-9]{4}',r['contract_name']).group())
 month=re.search(r'20[0-9]{4}',r['contract_name']).group();krx=r['contract_code'];code=('175W' if krx.startswith('175W') else 'A756')+month[-2:]
 selections.append(dict(business_date=day,start_date=prev[day],contract_code_kis=code,contract_code_krx=krx,contract_month=month,official_close=float(r['close']),official_volume=float(r['volume'])))
csvout(OUT/'frozen_session_contract_plan.csv',selections)
r=requests.post(BASE+'/oauth2/tokenP',json={'grant_type':'client_credentials','appkey':KIS_APP_KEY,'appsecret':KIS_APP_SECRET},timeout=25);j=r.json();token=j.get('access_token');assert token, 'KIS_AUTH_FAILED_'+str(r.status_code)+'_'+str(j.get('error_code',''))
headers={'authorization':'Bearer '+token,'appkey':KIS_APP_KEY,'appsecret':KIS_APP_SECRET,'tr_id':'FHKIF03020200','custtype':'P','content-type':'application/json; charset=utf-8'}
allstatus=[];allbars=[]
def collect(sel):
 day=sel['start_date'].replace('-','');code=sel['contract_code_kis'];path=OUT/'sessions'/(day+'_'+code+'.json')
 if path.exists():return json.loads(path.read_text())
 cursor='300000';seen=set();unique={};pages=[];error=''
 for page in range(10):
  if cursor in seen:error='CURSOR_REPEAT';break
  seen.add(cursor);time.sleep(1.2)
  params={'FID_COND_MRKT_DIV_CODE':'CM','FID_INPUT_ISCD':code,'FID_HOUR_CLS_CODE':'60','FID_PW_DATA_INCU_YN':'Y','FID_FAKE_TICK_INCU_YN':'N','FID_INPUT_DATE_1':day,'FID_INPUT_HOUR_1':cursor}
  try:r=requests.get(BASE+'/uapi/domestic-futureoption/v1/quotations/inquire-time-fuopchartprice',headers=headers,params=params,timeout=25);j=r.json()
  except requests.RequestException as e:error=type(e).__name__;break
  rows=j.get('output2') or [];pages.append(dict(cursor=cursor,http=r.status_code,rt_cd=j.get('rt_cd'),msg_cd=j.get('msg_cd'),response_rows=len(rows)))
  if r.status_code!=200 or j.get('rt_cd')!='0':error='API_ERROR';break
  labels=[]
  for x in rows:
   label=str(x.get('stck_cntg_hour','')).zfill(6)
   if str(x.get('stck_bsop_date'))!=day or label<'180000' or label>'300000':continue
   h,m,s=int(label[:2]),int(label[2:4]),int(label[4:]);stamp=datetime.datetime.strptime(day,'%Y%m%d')+datetime.timedelta(hours=h,minutes=m,seconds=s)
   unique[label]=dict(**sel,source='KIS_FHKIF03020200_CM',raw_date=day,raw_time=label,timestamp_kst=stamp.isoformat(sep=' '),open=float(x['futs_oprc']),high=float(x['futs_hgpr']),low=float(x['futs_lwpr']),close=float(x['futs_prpr']),volume=float(x.get('cntg_vol') or 0));labels.append(label)
  if not labels or min(labels)<='180000':break
  label=min(labels);mins=int(label[:2])*60+int(label[2:4])-1;h,m=divmod(mins,60);cursor=f'{h:02}{m:02}00'
 bars=[unique[k] for k in sorted(unique)];vol=sum(b['volume'] for b in bars);match=bool(bars and abs(bars[-1]['close']-sel['official_close'])<1e-7 and vol==sel['official_volume'])
 status=dict(**sel,rows=len(bars),first=bars[0]['timestamp_kst'] if bars else '',last=bars[-1]['timestamp_kst'] if bars else '',volume_sum=vol,volume_match=vol==sel['official_volume'] if bars else False,close_match=bool(bars and abs(bars[-1]['close']-sel['official_close'])<1e-7),status='COMPLETE' if match else 'PARTIAL' if bars else 'FAILED' if error else 'EMPTY_RESPONSE',error=error)
 packet=dict(status=status,pages=pages,bars=bars);save(path,packet);return packet
for month in range(6,13):
 ss=[s for s in selections if s['business_date'][5:7]==f'{month:02}'];done={}
 if not ss:continue
 # Sample both ends before requesting all dates in a month known to be empty.
 for s in [ss[0],ss[-1]]:
  p=collect(s);done[s['business_date']]=p
 if any(p['bars'] for p in done.values()):
  for s in ss:
   if s['business_date'] not in done:done[s['business_date']]=collect(s)
 for s in ss:
  p=done.get(s['business_date'])
  if p:allstatus.append(p['status']);allbars.extend(p['bars'])
  else:allstatus.append(dict(**s,rows=0,first='',last='',volume_sum=0,volume_match=False,close_match=False,status='NOT_QUERIED_AFTER_EMPTY_MONTH_PROBES',error=''))
 csvout(OUT/'session_status.csv',allstatus);csvout(OUT/'night_bars.csv',allbars)
 summary=dict(month=f'2025-{month:02}',official_sessions=len(ss),sessions_with_rows=sum(bool(p['bars']) for p in done.values()),rows=sum(len(p['bars']) for p in done.values()),complete=sum(p['status']['status']=='COMPLETE' for p in done.values()),actually_queried=len(done))
 save(OUT/f'month_{month:02}.json',summary);print(json.dumps(summary),flush=True)
 print('',end='',flush=True)
save(OUT/'summary.json',dict(rows=len(allbars),sessions_with_rows=sum(s['rows']>0 for s in allstatus),complete=sum(s['status']=='COMPLETE' for s in allstatus),states=dict(collections.Counter(s['status'] for s in allstatus)),no_strategy_performance=True));print('NIGHT_ACQUISITION_DONE',flush=True)
