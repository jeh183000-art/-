from pathlib import Path
import json, csv, hashlib, sys, time
import requests
ROOT=Path(__file__).resolve().parents[1]
ARCH=Path(r'D:/Codex_Research/archive/c_drive_migration_20261020/codex_workspace/files-pasted-by-the-user-codex/outputs/usdt_krx_live_dashboard')
sys.path.insert(0,str(ARCH))
from krx_live.config import KIS_APP_KEY,KIS_APP_SECRET
OUT=ROOT/'data_access';OUT.mkdir(exist_ok=True)
BASE='https://openapi.koreainvestment.com:9443'
def save(n,x):(OUT/n).write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding='utf8')
if not KIS_APP_KEY or not KIS_APP_SECRET:
 save('api_results.json',{'status':'AUTH_REQUIRED','queries':[]});sys.exit(0)
r=requests.post(BASE+'/oauth2/tokenP',json={'grant_type':'client_credentials','appkey':KIS_APP_KEY,'appsecret':KIS_APP_SECRET},timeout=25)
b=r.json();token=b.get('access_token')
auth={'http':r.status_code,'success':bool(token),'error_code':b.get('error_code','')}
if not token:save('api_results.json',{'status':'AUTH_FAILED','auth':auth,'queries':[]});print(json.dumps(auth));sys.exit(0)
headers={'authorization':'Bearer '+token,'appkey':KIS_APP_KEY,'appsecret':KIS_APP_SECRET,'tr_id':'FHKIF03020200','custtype':'P','content-type':'application/json; charset=utf-8'}
# Frozen representative availability probes only. Contracts already verified against official daily master.
queries=[('20250930','175W10','CF','154500'),('20250930','175W10','CM','300000'),('20251001','175W10','CM','300000'),('20251211','175W12','CM','300000')]
results=[]
for day,code,market,cursor in queries:
 time.sleep(1.2)
 params={'FID_COND_MRKT_DIV_CODE':market,'FID_INPUT_ISCD':code,'FID_HOUR_CLS_CODE':'60','FID_PW_DATA_INCU_YN':'Y','FID_FAKE_TICK_INCU_YN':'N','FID_INPUT_DATE_1':day,'FID_INPUT_HOUR_1':cursor}
 try:
  r=requests.get(BASE+'/uapi/domestic-futureoption/v1/quotations/inquire-time-fuopchartprice',headers=headers,params=params,timeout=25);b=r.json();rows=b.get('output2') or []
  dates=sorted({str(x.get('stck_bsop_date','')) for x in rows});identity=b.get('output1') or {}
  item={'date':day,'contract':code,'market':market,'cursor':cursor,'http':r.status_code,'rt_cd':b.get('rt_cd'),'msg_cd':b.get('msg_cd'),'response_rows':len(rows),'response_dates':dates,'output_code':identity.get('futs_shrn_iscd'),'output_name':identity.get('hts_kor_isnm'),'status':'DATA_ROWS' if rows else 'EMPTY_RESPONSE' if r.status_code==200 and b.get('rt_cd')=='0' else 'API_ERROR'}
  if rows: save(day+'_'+market+'_raw_price_rows.json',{'params':params,'output1':identity,'output2':rows})
 except requests.RequestException as e:item={'date':day,'market':market,'status':'NETWORK_ERROR','exception_type':type(e).__name__}
 results.append(item);print(json.dumps(item,ensure_ascii=False),flush=True)
save('api_results.json',{'auth':auth,'queries':results,'tokens_saved':False,'no_orders':True})
