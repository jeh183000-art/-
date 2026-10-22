from pathlib import Path
import json,csv,hashlib,datetime
ROOT=Path(__file__).resolve().parents[1]
p=ROOT.parent/'b_fixed_2025_validation_20261022_07/data_access/20251211_CM_raw_price_rows.json';o=json.loads(p.read_text());params=o['params'];assert params['FID_INPUT_ISCD']=='175W12' and params['FID_COND_MRKT_DIV_CODE']=='CM'
plan=list(csv.DictReader((ROOT.parent/'b_fixed_2025_validation_20261022_07/night_acquisition/frozen_session_contract_plan.csv').open()))
sel=[x for x in plan if x['start_date']=='2025-12-11' and x['contract_code_kis']=='175W12'];assert len(sel)==1
business=sel[0]['business_date'].replace('-','')
u=list(csv.DictReader((ROOT/'audit/verified_union_copy.csv').open()));look={(r['business_date'],r['timestamp_kst'],r['contract_code'],r['session']):r for r in u};checked=0
for r in o['output2']:
 t=r['stck_cntg_hour'];stamp=datetime.datetime.strptime(r['stck_bsop_date'],'%Y%m%d')+datetime.timedelta(hours=int(t[:2]),minutes=int(t[2:4]),seconds=int(t[4:]));key=(business,stamp.isoformat(sep=' '),'175W12','night');v=look[key]
 for a,b in [('futs_oprc','open'),('futs_hgpr','high'),('futs_lwpr','low'),('futs_prpr','close'),('cntg_vol','volume')]:assert float(r[a])==float(v[b])
 checked+=1
proof=dict(status='PASS_METADATA_ENRICHED_DUPLICATE_SOURCE',path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),contract_source='request FID_INPUT_ISCD verified against existing official session contract plan',business_date=business,rows=checked,all_rows_already_in_verified_union=True,new_rows=0,reason='API price rows do not repeat the contract code; request metadata is required to identify them')
(ROOT/'audit/json_probe_supplement.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps(proof))
