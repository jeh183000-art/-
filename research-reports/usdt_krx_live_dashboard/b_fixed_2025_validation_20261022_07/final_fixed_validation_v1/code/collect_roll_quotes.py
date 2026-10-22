from pathlib import Path
import csv,json,time,sys,datetime
import requests
ROOT=Path(__file__).resolve().parents[1]
ARCH=Path(r'D:/Codex_Research/archive/c_drive_migration_20261020/codex_workspace/files-pasted-by-the-user-codex/outputs/usdt_krx_live_dashboard')
sys.path.insert(0,str(ARCH))
from krx_live.config import KIS_APP_KEY,KIS_APP_SECRET
OUT=ROOT/'roll_quotes';OUT.mkdir(exist_ok=True)
BASE='https://openapi.koreainvestment.com:9443'
r=requests.post(BASE+'/oauth2/tokenP',json={'grant_type':'client_credentials','appkey':KIS_APP_KEY,'appsecret':KIS_APP_SECRET},timeout=25);j=r.json();token=j.get('access_token');assert token,'AUTH_FAILED'
headers={'authorization':'Bearer '+token,'appkey':KIS_APP_KEY,'appsecret':KIS_APP_SECRET,'tr_id':'FHKIF03020200','custtype':'P','content-type':'application/json; charset=utf-8'}
plan=json.loads((ROOT/'preregistration/partial_validation_policy.json').read_text())['rolls'];audit=[]
for p in plan:
 day=p['date'];code=p['next'];cursor='154500';allrows={};calls=[]
 for page in range(7):
  time.sleep(1.2)
  params={'FID_COND_MRKT_DIV_CODE':'CF','FID_INPUT_ISCD':code,'FID_HOUR_CLS_CODE':'60','FID_PW_DATA_INCU_YN':'Y','FID_FAKE_TICK_INCU_YN':'N','FID_INPUT_DATE_1':day,'FID_INPUT_HOUR_1':cursor}
  r=requests.get(BASE+'/uapi/domestic-futureoption/v1/quotations/inquire-time-fuopchartprice',headers=headers,params=params,timeout=25);j=r.json();rows=j.get('output2') or []
  calls.append(dict(cursor=cursor,http=r.status_code,rt_cd=j.get('rt_cd'),msg_cd=j.get('msg_cd'),rows=len(rows)))
  if r.status_code!=200 or j.get('rt_cd')!='0':break
  times=[]
  for x in rows:
   if x.get('stck_bsop_date')==day:
    t=x['stck_cntg_hour'];allrows[t]=dict(trade_date=day,time_kst=t,contract_code_kis=code,open=x['futs_oprc'],high=x['futs_hgpr'],low=x['futs_lwpr'],close=x['futs_prpr'],volume=x['cntg_vol']);times.append(t)
  if not times or min(times)<='084500':break
  cursor=(datetime.datetime.strptime(min(times),'%H%M%S')-datetime.timedelta(minutes=1)).strftime('%H%M%S')
 bars=[allrows[k] for k in sorted(allrows)]
 if bars:
  with (OUT/(day+'_'+code+'.csv')).open('w',encoding='utf8',newline='') as f:w=csv.DictWriter(f,fieldnames=list(bars[0]));w.writeheader();w.writerows(bars)
 audit.append(dict(**p,rows=len(bars),has_required_open=p['time'] in allrows,first=bars[0]['time_kst'] if bars else None,calls=calls))
(OUT/'audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps(audit))
