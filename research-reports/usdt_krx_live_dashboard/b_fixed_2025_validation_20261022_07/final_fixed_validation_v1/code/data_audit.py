from pathlib import Path
import csv,json,hashlib,collections,datetime
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
ARCH=Path(r'D:/Codex_Research/archive/c_drive_migration_20261020/codex_workspace/files-pasted-by-the-user-codex/outputs/usdt_krx_live_dashboard')
OUT=ROOT/'data_audit';OUT.mkdir(exist_ok=True)
inputs=[]
def read(p):
 b=p.read_bytes();inputs.append(dict(path=str(p),bytes=len(b),sha256=hashlib.sha256(b).hexdigest()));return pd.read_csv(p,dtype=str).fillna('')
def save(n,x):(OUT/n).write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding='utf8')
reg=json.loads((ROOT/'preregistration/fixed_variants.json').read_text());assert len(reg['conditions'])==2
bars=read(ARCH/'data/krx_2025_full_1m/KRX_USD_1m_2025_01_01_to_2025_12_31.csv')
contracts=read(ARCH/'data/krx_2025_full_1m/contract_selection.csv')
# The merged daily file includes already authorized 2026 dates; select 2025 immediately and do not compute other periods.
daily=read(ARCH/'data/archive_2025_2026/krx_daily/krx_usd_futures_daily_2025_2026.csv');daily=daily[daily.business_date.str.startswith('2025')]
quality=read(ARCH/'data/krx_2025_full_1m/data_quality_report.csv')
upbits=[];upmeta=[]
for m in range(1,13):
 f=ARCH/f'data/archive_2025_2026/upbit/monthly/upbit_krw_usdt_1m_2025-{m:02}.csv';u=read(f);upbits.append(u)
 upmeta.append(dict(month=f'2025-{m:02}',rows=len(u),first=u.candle_date_time_kst.min(),last=u.candle_date_time_kst.max(),duplicates=int(u.candle_date_time_kst.duplicated().sum())))
u=pd.concat(upbits,ignore_index=True);u['stamp']=pd.to_datetime(u.candle_date_time_kst)
bars['stamp']=pd.to_datetime(bars.trade_date+bars.time_kst,format='%Y%m%d%H%M%S');bars['month']=bars.trade_date.str[:6]
err=lambda z: int(((z.high.astype(float)<z[['open','close']].astype(float).max(axis=1))|(z.low.astype(float)>z[['open','close']].astype(float).min(axis=1))|(z.low.astype(float)>z.high.astype(float))).sum())
monthly=[];dayrows=[]
for m in range(1,13):
 mm=f'2025{m:02}';b=bars[bars.month==mm];q=quality[quality.date.str.startswith(mm)];ds=contracts[contracts.date.str.startswith(mm)];night=daily[(daily.business_date.str[5:7]==f'{m:02}')&(daily.session=='야간')]
 monthly.append(dict(month=f'2025-{m:02}',official_regular_days=len(ds),regular_days=b.trade_date.nunique(),regular_rows=len(b),upbit_rows=upmeta[m-1]['rows'],night_saved_rows=0,official_night_contract_rows=len(night),official_night_unique_business_dates=night.business_date.nunique(),state='MISSING_JAN_SEP' if not len(b) else 'REGULAR_ONLY_PARTIAL_VALIDATION_INPUT',complete_label_not_reconfirmed=True))
for day,b in bars.groupby('trade_date'):
 c=contracts[contracts.date==day].iloc[0];d=daily[(daily.business_date==str(b.stamp.iloc[0].date()))&(daily.contract_code==c.contract_code_krx)&(daily.session=='정규')]
 official=d.iloc[0] if len(d)==1 else None
 expected_volume=float(official.volume) if official is not None else None
 vsum=float(b.volume.astype(float).sum());last=float(b.iloc[-1].close)
 dayrows.append(dict(date=day,contract=c.contract_code_kis,krx_code=c.contract_code_krx,expiry=c.expiry_date,rows=len(b),first=str(b.stamp.min()),last=str(b.stamp.max()),duplicates=int(b[['stamp','contract_code_kis']].duplicated().sum()),ohlc_errors=err(b),last_close=last,official_close=float(official.close) if official is not None else None,close_match=bool(official is not None and abs(last-float(official.close))<1e-7),minute_volume_sum=vsum,official_volume=expected_volume,volume_match=bool(expected_volume==vsum),settlement_available=bool(official is not None and official.settlement!='')))
# Inventory matching only; no strategy return calculation at this stage.
matched=bars.merge(u[['stamp','opening_price','trade_price']],on='stamp',how='inner',validate='many_to_one')
matched[['trade_date','time_kst','contract_code_kis','stamp']].to_csv(OUT/'matched_timestamps_2025.csv',index=False)
pd.DataFrame(monthly).to_csv(OUT/'monthly_coverage.csv',index=False);pd.DataFrame(dayrows).to_csv(OUT/'regular_daily_audit.csv',index=False);pd.DataFrame(upmeta).to_csv(OUT/'upbit_monthly_audit.csv',index=False);pd.DataFrame(inputs).to_csv(OUT/'input_inventory_sha256.csv',index=False)
# Exact official margin schedule is currently absent locally for 2025. Never use the 2026 schedule as a fallback.
summary=dict(upbit_rows=len(u),upbit_duplicates=int(u.stamp.duplicated().sum()),regular_rows=len(bars),regular_days=bars.trade_date.nunique(),regular_ohlc_errors=err(bars),regular_duplicate_keys=int(bars[['stamp','contract_code_kis']].duplicated().sum()),regular_first=str(bars.stamp.min()),regular_last=str(bars.stamp.max()),matched_label_rows=len(matched),official_close_matches=sum(r['close_match'] for r in dayrows),official_volume_matches=sum(r['volume_match'] for r in dayrows),official_days=len(contracts),full_year_input_ready=False,financial_validation_status='BLOCKED_MISSING_HISTORY_NIGHT_MARGIN_AND_ROLL_QUOTES',margin_2025_verified=False,prior_use='2025 daily-validation already used in krx_roll_study_2024_2025/manifest.json; pristine unused data NOT established',no_interpolation=True,protected_oos_read=False)
save('summary.json',summary);print(json.dumps(summary,ensure_ascii=False))
