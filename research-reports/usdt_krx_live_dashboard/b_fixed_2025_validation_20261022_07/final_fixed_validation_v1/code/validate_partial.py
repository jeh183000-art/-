from pathlib import Path
import hashlib,json,importlib.util,csv,gzip,datetime
import numpy as np
import pandas as pd
import runner
ROOT=Path(__file__).resolve().parents[1];PROJECT=ROOT.parents[1]
ARCH=Path(r'D:/Codex_Research/archive/c_drive_migration_20261020/codex_workspace/files-pasted-by-the-user-codex/outputs/usdt_krx_live_dashboard')
OUT=ROOT/'validation_2025_partial';OUT.mkdir()
reg=json.loads((ROOT/'preregistration/fixed_variants.json').read_text())
policy=json.loads((ROOT/'preregistration/partial_validation_policy.json').read_text())
assert policy['partial_scope']==['2025-11-03','2025-12-30']
freeze=json.loads((ROOT/'preregistration/validation_execution_hashes.json').read_text())
for name,h in freeze['code_sha256'].items():assert hashlib.sha256((ROOT/'code'/name).read_bytes()).hexdigest()==h
for name,h in freeze['inputs_sha256'].items():assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==h
read=lambda p:pd.read_csv(p,dtype=str).fillna('')
regular=read(ARCH/'data/krx_2025_full_1m/KRX_USD_1m_2025_01_01_to_2025_12_31.csv')
selection=read(ARCH/'data/krx_2025_full_1m/contract_selection.csv')
expiry=selection.drop_duplicates('contract_month').set_index('contract_month').expiry_date.to_dict()
regular=regular[(regular.trade_date>='20251103')&(regular.trade_date<='20251230')].copy()
regular['timestamp_kst']=pd.to_datetime(regular.trade_date+regular.time_kst.str.zfill(6),format='%Y%m%d%H%M%S')
regular['business_date']=regular.trade_date;regular['session']='regular'
regular['contract_roll']=False;regular['roll_old_open']=np.nan;regular['roll_old_kis']='';regular['roll_old_krx']=''
rollaudit=json.loads((ROOT/'roll_quotes/audit.json').read_text())
assert all(x['has_required_open'] for x in rollaudit),'EXACT_ROLL_OPEN_MISSING'
daily=read(ARCH/'data/archive_2025_2026/krx_daily/krx_usd_futures_daily_2025_2026.csv');daily=daily[(daily.business_date>='2025-11-03')&(daily.business_date<='2025-12-30')&(daily.session=='정규')].copy();daily['business_date']=daily.business_date.str.replace('-','',regex=False)
rollchecks=[]
for p in policy['rolls']:
 old=regular[(regular.trade_date==p['date'])&(regular.contract_code_kis==p['old'])&(regular.time_kst=='084500')]
 assert len(old)==1,'OLD_CONTRACT_ROLL_OPEN_MISSING'
 new=read(ROOT/'roll_quotes'/(p['date']+'_'+p['next']+'.csv'))
 month='202512' if p['next']=='175W12' else '202601';code='175WC000' if month=='202512' else 'A7561000'
 official=daily[(daily.business_date==p['date'])&(daily.contract_code==code)]
 assert len(official)==1,'ROLL_OFFICIAL_IDENTITY_MISSING'
 d=official.iloc[0]
 assert abs(float(new.iloc[-1].close)-float(d.close))<1e-7,'ROLL_CLOSE_MISMATCH'
 new['business_date']=p['date'];new['session']='regular';new['contract_month']=month;new['contract_code_krx']=code
 new['timestamp_kst']=pd.to_datetime(new.trade_date+new.time_kst,format='%Y%m%d%H%M%S');new['contract_roll']=new.time_kst=='084500'
 new['roll_old_open']=np.where(new.contract_roll,float(old.iloc[0].open),np.nan);new['roll_old_kis']=np.where(new.contract_roll,p['old'],'');new['roll_old_krx']=np.where(new.contract_roll,old.iloc[0].contract_code_krx,'')
 regular=regular[regular.trade_date!=p['date']];regular=pd.concat([regular,new],ignore_index=True)
 rollchecks.append(dict(**p,new_krx_code=code,new_open=float(new[new.contract_roll].iloc[0].open),old_open=float(old.iloc[0].open),official_close_match=True,volume_match=float(new.volume.astype(float).sum())==float(d.volume)))
night=read(ROOT/'night_acquisition/night_bars.csv');status=read(ROOT/'night_acquisition/session_status.csv')
valid=set(status[status.status=='COMPLETE'].business_date)
night=night[(night.business_date>='2025-11-03')&(night.business_date<='2025-12-30')&night.business_date.isin(valid)].copy();night['business_date']=night.business_date.str.replace('-','',regex=False);night['timestamp_kst']=pd.to_datetime(night.timestamp_kst);night['session']='night';night['contract_roll']=False;night['roll_old_open']=np.nan;night['roll_old_kis']='';night['roll_old_krx']=''
cols=['business_date','timestamp_kst','session','contract_month','contract_code_kis','contract_code_krx','open','high','low','close','volume','contract_roll','roll_old_open','roll_old_kis','roll_old_krx']
f=pd.concat([regular[cols],night[cols]],ignore_index=True)
f['expiry_date']=f.contract_month.map(expiry)
# January2026 is already listed in the same original 2025 contract master/selection history; verify exact expiry from master metadata.
master=read(ARCH/'data/archive_2025_2026/krx_daily/contract_master.csv')
emap=master.set_index('contract_code_krx').expiry_date.to_dict();f['expiry_date']=f.contract_code_krx.map(emap);assert f.expiry_date.notna().all()
clock=f.timestamp_kst.dt.strftime('%H%M%S');end=np.where(f.business_date=='20251113','163500','153500')
f=f[((f.session=='regular')&(clock<end))|((f.session=='night')&((clock>='180000')|(clock<'055000')))].copy()
for c in ['open','high','low','close','volume']:f['future_'+c]=pd.to_numeric(f[c],errors='raise')
up=pd.concat([read(ARCH/f'data/archive_2025_2026/upbit/monthly/upbit_krw_usdt_1m_2025-{m:02}.csv') for m in (10,11,12)],ignore_index=True)
up['timestamp_kst']=pd.to_datetime(up.candle_date_time_kst)
f=f.merge(up[['timestamp_kst','opening_price','high_price','low_price','trade_price','candle_acc_trade_volume']],on='timestamp_kst',how='inner',validate='many_to_one')
for source,target in [('opening_price','spot_open'),('high_price','spot_high'),('low_price','spot_low'),('trade_price','spot_close'),('candle_acc_trade_volume','spot_volume')]:f[target]=pd.to_numeric(f[source])
f=f.sort_values('timestamp_kst').reset_index(drop=True);assert not f.timestamp_kst.duplicated().any()
f['epoch_minute']=f.timestamp_kst.astype('datetime64[ns]').astype('int64')//60000000000
f['continuous_prev']=(f.epoch_minute.diff()==1)&(f.contract_code_kis==f.contract_code_kis.shift())&~f.contract_roll.astype(bool)
f['raw_gap_close_pct']=(f.spot_close/f.future_close-1)*100
f=f.merge(daily[['business_date','contract_code','settlement']].rename(columns={'contract_code':'contract_code_krx','settlement':'official_daily_settlement'}),on=['business_date','contract_code_krx'],how='left',validate='many_to_one')
f['settlement_due']=False;f['settlement_spot_mark']=np.nan
upmark=up.set_index('timestamp_kst').trade_price
phase=[]
for date,index in f[f.session=='regular'].groupby('business_date').timestamp_kst.idxmax().items():
 closing=pd.Timestamp(date+' 16:45:00' if date=='20251113' else date+' 15:45:00');mark_time=closing-pd.Timedelta(minutes=1)
 assert mark_time in upmark.index
 # SETTLEMENT is a post-close accounting phase, never an earlier executable quote.
 # No executable observation can occur between the attached row and actual close.
 assert index==len(f)-1 or f.iloc[index+1].timestamp_kst>=closing
 assert index==len(f)-1 or not f.iloc[index+1].continuous_prev
 f.at[index,'settlement_due']=True;f.at[index,'settlement_spot_mark']=float(upmark.loc[mark_time])
 assert pd.notna(f.at[index,'official_daily_settlement']) and f.at[index,'official_daily_settlement']!=''
 phase.append(dict(row=int(index),business_date=date,attached_observation_kst=str(f.at[index,'timestamp_kst']),settlement_effective_kst=str(closing),publication_timestamp='NOT_PROVIDED_BY_DAILY_API',no_intervening_executable_observation=True))
f.to_csv(OUT/'matched_simulation_bars.csv',index=False)
margin=[dict(effective_from='2025-11-03',effective_to='2025-11-30',customer_initial_margin_pct='4.170',maintenance_margin_pct='2.780',source_status='OFFICIAL'),dict(effective_from='2025-12-01',effective_to='2025-12-30',customer_initial_margin_pct='4.170',maintenance_margin_pct='2.780',source_status='OFFICIAL')]
pd.DataFrame(margin).to_csv(OUT/'margin_schedule.csv',index=False)
spec=importlib.util.spec_from_file_location('fixed_2025_input_adapter',PROJECT/'shared/approved_20261016_01/paper_engine.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);module.INPUT=OUT/'matched_simulation_bars.csv';module.MARGINS=OUT/'margin_schedule.csv'
a=module.load_arrays();v=tuple(a[k] for k in runner.NAMES)
runner.write_json(OUT/'input_validation.json',dict(status='PASS_WITH_COVERAGE_LIMITATIONS',rows=len(f),first=str(f.timestamp_kst.min()),last=str(f.timestamp_kst.max()),regular_rows=int((f.session=='regular').sum()),night_rows=int((f.session=='night').sum()),rolls=rollchecks,settlements=phase,account_starts_flat_once=True,no_monthly_account_reset=True,full_year=False,price_interval='same KIS/Upbit minute label convention as approved engine; intraminute order fills unverified',source_sha256=hashlib.sha256((OUT/'matched_simulation_bars.csv').read_bytes()).hexdigest()))
results=[]
for candidate in reg['conditions']:
 r=runner.calculate(candidate,v,f,a['contract_codes'],OUT/candidate['candidate_id']);r['period_class']='PARTIAL_WINDOW_2025_NOV_DEC_NOT_FULL_YEAR';r['profit_factor']='INF' if r['cycles'] and r['win_rate_pct']==100 else None
 results.append(r)
 # Correct event accounting timestamps: post-close settlement is not the earlier attached observation timestamp.
 p=OUT/candidate['candidate_id'];event=pd.read_csv(p/'fills.csv.gz');effective={x['row']:x['settlement_effective_kst'] for x in phase};event['accounting_effective_kst']=[effective[int(row)] if int(kind)==5 else stamp for row,kind,stamp in zip(event.row,event.event_code,event.timestamp_kst)];event.to_csv(p/'fills_with_accounting_time.csv',index=False)
 cycles=pd.read_csv(p/'cycles.csv.gz');net=cycles.net.to_numpy() if len(cycles) else np.array([]);r['profit_factor']=float(net[net>0].sum()/-net[net<0].sum()) if (net<0).any() else 'INF' if (net>0).any() else None
 print(json.dumps(r,ensure_ascii=False),flush=True)
runner.table(OUT/'results.csv',results);runner.write_json(OUT/'results.json',results)
