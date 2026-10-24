#!/usr/bin/env python3
"""Public Binance V2 data preparation; holdout inspection is structural only.

python data_loader_v2.py --scope both
Existing V1 source files are read-only. No model or performance calculation.
"""
from __future__ import annotations
import argparse, concurrent.futures, hashlib, io, json, time, urllib.error, urllib.request, zipfile
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
WORKSPACE = ROOT.parent
BASE = 'https://data.binance.vision/data/futures/um/monthly/klines'
COLUMNS = ['open_time','open','high','low','close','volume','close_time','quote_volume','trades','taker_buy_volume','taker_buy_quote_volume','ignore']
STEPS = {'15m':900_000,'4h':14_400_000}
EXISTING = {
    '4h': WORKSPACE/'btc4h_nextcandle/data/BTCUSDT_4h_2022-01_2025-12.csv.gz',
    '15m': WORKSPACE/'btc15_nextcandle/data/BTCUSDT_15m_2022-01_2025-12.csv.gz',
}
EXISTING_SHA = {
    '4h':'39c0471ee1052d5ab8d77ab099b88cb6d12fc72e0a5eca9137bd2654b35a5343',
    '15m':'6b1f1ee1f6cd2c482530b12d1c6582cc87b9d1f2273e3b0b2298f30c409e83eb',
}

def sha(data):
    return hashlib.sha256(data).hexdigest()

def write_json(path, obj):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')

def fetch(url):
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url,timeout=30) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            if exc.code in (400,401,403,404,418,451) or attempt==2: raise
        except (urllib.error.URLError,TimeoutError):
            if attempt==2: raise
        time.sleep(attempt+1)
    raise RuntimeError('unreachable')

def download(job):
    symbol,interval,month,folder=job
    name=f'{symbol}-{interval}-{month}.zip'
    url=f'{BASE}/{symbol}/{interval}/{name}'
    directory=folder/'raw'/symbol/interval
    directory.mkdir(parents=True,exist_ok=True)
    dest=directory/name; check=directory/(name+'.CHECKSUM')
    checksum=check.read_bytes() if check.exists() else fetch(url+'.CHECKSUM')
    expected=checksum.decode().strip().split()[0]
    content=dest.read_bytes() if dest.exists() else fetch(url)
    actual=sha(content)
    if actual!=expected: raise ValueError('Official SHA256 mismatch: '+name)
    dest.write_bytes(content); check.write_bytes(checksum)
    return {'symbol':symbol,'interval':interval,'month':month,'url':url,'path':str(dest),
            'bytes':len(content),'sha256':actual,'official_sha256_verified':True}

def read_zip(path):
    with zipfile.ZipFile(path) as z:
        names=z.namelist()
        if len(names)!=1 or not names[0].endswith('.csv'): raise ValueError('Unexpected ZIP structure')
        frame=pd.read_csv(io.BytesIO(z.read(names[0])),header=None,dtype=str)
    if len(frame.columns)!=12: raise ValueError('Unexpected kline schema')
    if frame.iloc[0,0] in ('open_time','open_timestamp'): frame=frame.iloc[1:].reset_index(drop=True)
    frame.columns=COLUMNS
    for col in COLUMNS: frame[col]=pd.to_numeric(frame[col],errors='raise')
    for col in ('open_time','close_time','trades'):
        if not np.equal(frame[col],np.floor(frame[col])).all(): raise ValueError('Noninteger '+col)
        frame[col]=frame[col].astype('int64')
    return frame.drop(columns='ignore')

def structural_audit(frame,symbol,interval,start,end,holdout):
    step=STEPS[interval]
    first=pd.Timestamp(start+'-01',tz='UTC'); last=pd.Timestamp(end+'-01',tz='UTC')+pd.offsets.MonthBegin(1)
    expected=np.arange(first.value//1_000_000,last.value//1_000_000,step,dtype=np.int64)
    times=frame.open_time.to_numpy(dtype=np.int64)
    missing=np.setdiff1d(expected,times)
    ranges=[]
    for stamp in missing:
        if ranges and stamp==ranges[-1]['end_open_ms']+step:
            ranges[-1]['end_open_ms']=int(stamp);ranges[-1]['bars']+=1
        else:ranges.append({'start_open_ms':int(stamp),'end_open_ms':int(stamp),'bars':1})
    r={'symbol':symbol,'interval':interval,'scope':'HOLDOUT_STRUCTURAL_ONLY' if holdout else 'DEVELOPMENT',
       'expected_start_utc':first.isoformat(),'expected_end_exclusive_utc':last.isoformat(),
       'rows':len(frame),'expected_rows':len(expected),'first_open_utc':pd.Timestamp(int(times[0]),unit='ms',tz='UTC').isoformat(),
       'last_open_utc':pd.Timestamp(int(times[-1]),unit='ms',tz='UTC').isoformat(),
       'sorted':bool(frame.open_time.is_monotonic_increasing),'duplicate_times':int(frame.open_time.duplicated().sum()),
       'missing_bars':len(missing),'missing_ranges':ranges,'off_grid':int((times%step!=0).sum()),
       'bad_close_times':int((frame.close_time!=frame.open_time+step-1).sum()),
       'nonfinite_rows':int((~np.isfinite(frame.to_numpy(dtype=float))).any(axis=1).sum()),
       'invalid_ohlc':int(((frame[['open','high','low','close']]<=0).any(axis=1)|(frame.high<frame[['open','low','close']].max(axis=1))|(frame.low>frame[['open','high','close']].min(axis=1))).sum()),
       'negative_volume_rows':int((frame[['volume','quote_volume','trades','taker_buy_volume','taker_buy_quote_volume']]<0).any(axis=1).sum()),
       'invalid_taker_rows':int((frame.taker_buy_volume>frame.volume+1e-7).sum()),
       'outside_requested_range':int(((times<expected[0])|(times>expected[-1])).sum()),
       'imputation':'NONE','deduplication':'NONE','label_or_return_distribution_computed':False,
       'model_fit_or_performance_computed':False}
    fatal=['duplicate_times','off_grid','bad_close_times','nonfinite_rows','invalid_ohlc','negative_volume_rows','invalid_taker_rows','outside_requested_range']
    if not r['sorted'] or any(r[k] for k in fatal):raise ValueError('Structural validation failed: '+json.dumps(r))
    return r

def collect(jobs,folder):
    completed=[];failed=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        tasks={pool.submit(download,job):job for job in jobs}
        for future in concurrent.futures.as_completed(tasks):
            symbol,interval,month,_=tasks[future]
            try:completed.append(future.result())
            except Exception as exc:failed.append({'symbol':symbol,'interval':interval,'month':month,'error':f'{type(exc).__name__}: {exc}'})
            n=len(completed)+len(failed)
            if n%20==0 or n==len(jobs):print(json.dumps({'folder':folder.name,'finished':n,'total':len(jobs),'failed':len(failed)}),flush=True)
    completed.sort(key=lambda r:(r['symbol'],r['interval'],r['month']))
    write_json(folder/'download_manifest.json',{'archives':completed,'failures':failed,'workers':4})
    return completed,failed

def normalize(records,folder,start,end,holdout=False,reuse=False):
    outputs=[]
    for symbol,interval in [('BTCUSDT','4h'),('BTCUSDT','15m'),('ETHUSDT','4h')]:
        selected=[r for r in records if r['symbol']==symbol and r['interval']==interval]
        frame=pd.concat([read_zip(r['path']) for r in selected],ignore_index=True)
        reused=None
        if reuse and symbol=='BTCUSDT':
            old=EXISTING[interval];actual=sha(old.read_bytes())
            if actual!=EXISTING_SHA[interval]:raise ValueError('Existing V1 source hash changed')
            frame=pd.concat([frame,pd.read_csv(old)],ignore_index=True)
            source_manifest=old.parent/'download_manifest.json'
            reused={'normalized_path':str(old),'normalized_sha256':actual,'archive_manifest_path':str(source_manifest),
                    'archive_manifest_sha256':sha(source_manifest.read_bytes()),'raw_archives_copied':False}
        audit=structural_audit(frame,symbol,interval,start,end,holdout)
        target=folder/f'{symbol}_{interval}_{start}_{end}.csv.gz'
        frame.to_csv(target,index=False,compression={'method':'gzip','mtime':0})
        audit.update({'path':str(target),'sha256':sha(target.read_bytes()),'bytes':target.stat().st_size,'reused_source':reused})
        write_json(folder/f'{symbol}_{interval}_audit.json',audit)
        outputs.append(audit)
    write_json(folder/'datasets.json',{'datasets':outputs,'holdout_quarantine':holdout})
    return outputs

def compare_development(folder):
    big=pd.read_csv(folder/'BTCUSDT_4h_2020-01_2025-12.csv.gz').set_index('open_time')
    small=pd.read_csv(folder/'BTCUSDT_15m_2020-01_2025-12.csv.gz')
    small['bucket']=small.open_time//STEPS['4h']*STEPS['4h'];g=small.groupby('bucket',sort=True)
    sizes=g.size();complete=(sizes==16)&(g.open_time.min()==sizes.index)&(g.open_time.max()==sizes.index+15*STEPS['15m'])
    agg=g.agg(open=('open','first'),high=('high','max'),low=('low','min'),close=('close','last'),volume=('volume','sum'),quote_volume=('quote_volume','sum'),trades=('trades','sum'),taker_buy_volume=('taker_buy_volume','sum'),taker_buy_quote_volume=('taker_buy_quote_volume','sum'))
    agg=agg.loc[complete];index=big.index.intersection(agg.index);a=big.loc[index];b=agg.loc[index]
    details=[];counts={};affected=set()
    for col in b.columns:
        exact=col in ('open','high','low','close','trades')
        same=np.isclose(a[col],b[col],rtol=0 if exact else 1e-12,atol=0 if exact else 1e-7)
        counts[col]=int((~same).sum())
        for pos in np.flatnonzero(~same):
            stamp=int(index[pos]);affected.add(stamp)
            details.append({'open_time':stamp,'open_utc':pd.Timestamp(stamp,unit='ms',tz='UTC').isoformat(),'field':col,'official_4h':float(a[col].iloc[pos]),'aggregate_15m':float(b[col].iloc[pos])})
    colors=np.sign(a.close-a.open)!=np.sign(b.close-b.open)
    report={'scope':'DEVELOPMENT_ONLY','canonical':'Official4h; no replacement or repair','official_rows':len(big),'complete_15m_buckets':int(complete.sum()),'incomplete_15m_buckets':int((~complete).sum()),'compared_rows':len(index),'affected_window_count':len(affected),'field_mismatch_counts':counts,'target_color_mismatch_count':int(colors.sum()),'holdout_not_compared':True}
    pd.DataFrame(details,columns=['open_time','open_utc','field','official_4h','aggregate_15m']).to_csv(folder/'aggregation_discrepancies.csv',index=False)
    write_json(folder/'aggregation_comparison.json',report)
    return report

def main():
    p=argparse.ArgumentParser();p.add_argument('--scope',choices=['development','holdout','both'],default='both');a=p.parse_args()
    if a.scope in ('development','both'):
        folder=ROOT/'data/development';folder.mkdir(parents=True,exist_ok=True)
        jobs=[]
        for symbol,interval,start,end in [('BTCUSDT','4h','2020-01','2021-12'),('BTCUSDT','15m','2020-01','2021-12'),('ETHUSDT','4h','2020-01','2025-12')]:
            jobs.extend((symbol,interval,str(month),folder) for month in pd.period_range(start,end,freq='M'))
        records,failed=collect(jobs,folder)
        if failed:raise SystemExit('Development download incomplete; no normalized datasets written')
        outputs=normalize(records,folder,'2020-01','2025-12',reuse=True)
        compare_development(folder)
        print(json.dumps({'event':'development_ready','datasets':[{'symbol':o['symbol'],'interval':o['interval'],'rows':o['rows'],'missing_bars':o['missing_bars'],'path':o['path'],'sha256':o['sha256']} for o in outputs]}),flush=True)
    if a.scope in ('holdout','both'):
        folder=ROOT/'data/holdout_2026';folder.mkdir(parents=True,exist_ok=True)
        probe=(folder/'availability_probe.json')
        if probe.exists() and not json.loads(probe.read_text())['available']:
            print(json.dumps({'event':'holdout_unavailable','probe':str(probe)}));return
        jobs=[(s,i,str(m),folder) for s,i in [('BTCUSDT','4h'),('BTCUSDT','15m'),('ETHUSDT','4h')] for m in pd.period_range('2026-01','2026-09',freq='M')]
        records,failed=collect(jobs,folder)
        if failed:
            write_json(folder/'status.json',{'status':'INCOMPLETE_NOT_AVAILABLE_FOR_EVALUATION','failures':failed,'performance_not_inspected':True})
            print(json.dumps({'event':'holdout_incomplete','failed':len(failed)}));return
        outputs=normalize(records,folder,'2026-01','2026-09',holdout=True)
        write_json(folder/'status.json',{'status':'RESERVED_UNEVALUATED','performance_not_inspected':True,'structural_only':True,'dataset_files':[o['path'] for o in outputs]})
        print(json.dumps({'event':'holdout_reserved','datasets':[{'symbol':o['symbol'],'interval':o['interval'],'rows':o['rows'],'missing_bars':o['missing_bars'],'path':o['path'],'sha256':o['sha256']} for o in outputs]}),flush=True)

if __name__=='__main__':main()
