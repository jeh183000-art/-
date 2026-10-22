from pathlib import Path
import csv,json,gzip,hashlib,re,io,zipfile,tarfile,datetime,collections,math
import sys
ROOT=Path(__file__).resolve().parents[1];FILES_ONLY='--files-only' in sys.argv;OUT=ROOT/('audit_files_only' if FILES_ONLY else 'audit');OUT.mkdir(exist_ok=True)
protected=re.compile(r'final[_ -]?oos|forward[_ -]?oos|protected[_ -]?oos|holdout',re.I)
rows=list(csv.DictReader((ROOT/'inventory/data_candidates.csv').open()))
sources=[];cache={};union={};origins=collections.defaultdict(list);conflicts=[];monthrows=[];gaps=[]
master=Path(r'D:/Codex_Research/archive/c_drive_migration_20261020/codex_workspace/files-pasted-by-the-user-codex/outputs/usdt_krx_live_dashboard/data/archive_2025_2026/krx_daily/contract_master.csv')
code_map={}
for mm in csv.DictReader(master.open(encoding='utf-8-sig')):
 code=mm['contract_code_krx'];month=mm['contract_month'].replace('-','')
 if code.startswith(('175W','A755','A756')):code_map[code]=('175W' if code.startswith('175W') else code[:4])+month[-2:]
def is2025(s):return '2025' in s or bool(re.search(r'175w[0-9abc]|a755',s.lower()))
def normalize(r,name):
 code=r.get('contract_code_kis') or r.get('contract_code') or r.get('contract_code_krx') or r.get('symbol') or ''
 if not code:
  m=re.search(r'(175W[0-9]{2}|A75[56][0-9]{2})',name,re.I);code=m.group(1).upper() if m else ''
 code=code_map.get(code,code)
 if not re.match(r'^(175W|A755|A756)',code):return None
 op=r.get('open',r.get('futs_oprc'));hi=r.get('high',r.get('futs_hgpr'));lo=r.get('low',r.get('futs_lwpr'));cl=r.get('close',r.get('futs_prpr'));vol=r.get('volume',r.get('cntg_vol'))
 if None in (op,hi,lo,cl):return None
 stamp=r.get('actual_kst') or r.get('timestamp_kst') or ''
 day=r.get('trade_date') or r.get('stck_bsop_date') or r.get('date') or ''
 clock=r.get('time_kst') or r.get('stck_cntg_hour') or ''
 session=r.get('session','') or ('night' if re.search(r'night|야간|_cm_',name,re.I) or str(clock).zfill(6)>='180000' else 'regular')
 session='night' if 'night' in session.lower() or '야간' in session else 'regular'
 try:
  if stamp:
   dt=datetime.datetime.fromisoformat(stamp.replace('Z','+00:00'))
   if dt.tzinfo:dt=dt.astimezone(datetime.timezone(datetime.timedelta(hours=9))).replace(tzinfo=None)
  elif day and clock:
   d=re.sub('[^0-9]','',str(day))[:8];t=re.sub('[^0-9]','',str(clock)).zfill(6);dt=datetime.datetime.strptime(d,'%Y%m%d')+datetime.timedelta(hours=int(t[:2]),minutes=int(t[2:4]),seconds=int(t[4:6]))
  else:return None
  if dt.year!=2025:return None
  prices=tuple(map(float,(op,hi,lo,cl,vol or 0)))
 except (ValueError,TypeError,OverflowError):return None
 if not all(map(math.isfinite,prices)):return None
 business=str(r.get('business_date') or r.get('trade_date') or dt.strftime('%Y%m%d')).replace('-','')[:8]
 return (business,dt.isoformat(sep=' '),code,session,*prices)
def inspect(raw,name,archive=''):
 digest=hashlib.sha256(raw).hexdigest();entry=dict(path=name,archive=archive,bytes=len(raw),sha256=digest,classification='',rows_2025=0,first='',last='',contracts='',duplicate_keys=0,ohlc_errors=0)
 # Only header/structure recognition for daily reports, ledgers, other instruments; no strategy analysis.
 try:
  if name.lower().endswith('.gz'):raw=gzip.decompress(raw)
  text=raw.decode('utf-8-sig')
  if name.lower().endswith(('.csv','.csv.gz')):
   reader=csv.DictReader(io.StringIO(text));fields=set(reader.fieldnames or [])
   if {'market','candle_date_time_kst'}<=fields:entry['classification']='UPBIT_NOT_KRX';return entry
   if not (('time_kst' in fields or 'stck_cntg_hour' in fields or 'actual_kst' in fields) and ('open' in fields or 'futs_oprc' in fields)):
    entry['classification']='DAILY_STATUS_DERIVED_OR_NON_BAR';return entry
   records=list(reader)
  else:
   obj=json.loads(text)
   if isinstance(obj,dict):records=obj.get('bars') or obj.get('output2') or []
   elif isinstance(obj,list):records=obj
   else:records=[]
   if not isinstance(records,list):records=[]
  records=[r for r in records if isinstance(r,dict)]
  bars=[x for r in records if (x:=normalize(r,name)) is not None]
  entry['classification']='USD_FUTURES_1M' if bars else 'EMPTY_OR_NO_VERIFIED_USD_1M_ROWS'
  if not bars:return entry
  keys=[(r[1],r[2],r[3]) for r in bars];entry['rows_2025']=len(bars);entry['duplicate_keys']=len(keys)-len(set(keys));entry['first']=min(r[1] for r in bars);entry['last']=max(r[1] for r in bars);entry['contracts']=';'.join(sorted({r[2] for r in bars}));entry['ohlc_errors']=sum(r[5]<max(r[4],r[7]) or r[6]>min(r[4],r[7]) or r[6]>r[5] or r[8]<0 for r in bars)
  for month in sorted({r[0][:6] for r in bars}):
   b=[r for r in bars if r[0][:6]==month];monthrows.append(dict(path=name,archive=archive,month=month,rows=len(b),business_dates=len({r[0] for r in b}),first=min(r[1] for r in b),last=max(r[1] for r in b),contracts=';'.join(sorted({r[2] for r in b}))))
  for r in bars:
   if entry['ohlc_errors']:continue
   key=(r[0],r[1],r[2],r[3]);old=union.get(key)
   if old is not None and old[4:]!=r[4:]:conflicts.append(dict(key=str(key),first_origin=origins[key][0],conflicting_origin=archive+'!'+name))
   else:union[key]=r
   if len(origins[key])<5:origins[key].append(archive+'!'+name)
 except (ValueError,UnicodeError,csv.Error,OSError) as e:entry['classification']='READ_ERROR_'+type(e).__name__
 return entry
for r in rows:
 p=Path(r['path']);name=str(p);low=name.lower()
 if not is2025(name) or protected.search(name) or r['protected_path']=='True':continue
 if re.search(r'upbit|usdt_krw_usdt|auth|credential|token|secret',p.name,re.I) or re.search(r'[/\\]upbit(?:_|[/\\])',name,re.I):continue
 if not low.endswith(('.csv','.csv.gz','.json')):continue
 # No protected 2026 input or combined-year minute bodies opened.
 if '2025_2026' in p.name or '2024_2026' in p.name:continue
 raw=p.read_bytes();sources.append(inspect(raw,name))
 if len(sources)%100==0:print(json.dumps(dict(event='FILES_AUDITED',count=len(sources))),flush=True)
# Archive indices must have completed before this script starts.
ars=[] if FILES_ONLY else list(csv.DictReader((ROOT/'inventory/archive_candidates.csv').open()))
for a in ars:
 name=a['member'];low=name.lower()
 if not is2025(name) or protected.search(name) or a['protected_path']=='True':continue
 if re.search(r'upbit|auth|credential|token|secret',name,re.I) or not low.endswith(('.csv','.csv.gz','.json')):continue
 if '2025_2026' in Path(name).name or '2024_2026' in Path(name).name:continue
 p=Path(a['archive'])
 try:
  if p.suffix.lower()=='.zip':
   with zipfile.ZipFile(p) as z:raw=z.read(name)
  else:
   with tarfile.open(p,'r:*') as t:
    e=t.getmember(name);f=t.extractfile(e);raw=f.read()
  sources.append(inspect(raw,name,str(p)))
 except (OSError,ValueError,KeyError,tarfile.TarError,zipfile.BadZipFile) as e:sources.append(dict(path=name,archive=str(p),bytes=a['bytes'],sha256='',classification='ARCHIVE_READ_ERROR_'+type(e).__name__,rows_2025=0,first='',last='',contracts='',duplicate_keys=0,ohlc_errors=0))
def save(n,rr,fields=None):
 with (OUT/n).open('w',encoding='utf8',newline='') as f:
  names=fields or (list(rr[0]) if rr else ['status']);w=csv.DictWriter(f,fieldnames=names);w.writeheader();w.writerows(rr)
save('file_audit.csv',sources);save('per_source_monthly.csv',monthrows);save('conflicts.csv',conflicts)
allrows=sorted(union.values());monthly=[]
for m in range(1,13):
 month=f'2025{m:02}';b=[r for r in allrows if r[0].startswith(month)];day=[r for r in b if r[3]=='regular'];night=[r for r in b if r[3]=='night']
 monthly.append(dict(month=month,regular_rows=len(day),regular_days=len({r[0] for r in day}),night_rows=len(night),night_sessions=len({r[0] for r in night}),contract_rows=len(b),unique_timestamps=len({r[1] for r in b})))
save('monthly_union.csv',monthly)
# Store only an audited derivative; do not replace any original or silently resolve conflicting sources.
barfields=['business_date','timestamp_kst','contract_code','session','open','high','low','close','volume']
save('verified_union_copy.csv',[dict(zip(barfields,r)) for r in allrows],barfields)
by=collections.defaultdict(list)
for r in allrows:by[(r[0],r[2],r[3])].append(r)
for key,b in by.items():
 ts=sorted({datetime.datetime.fromisoformat(x[1]) for x in b})
 for left,right in zip(ts,ts[1:]):
  n=int((right-left).total_seconds()/60)-1
  if n>0:gaps.append(dict(business_date=key[0],contract=key[1],session=key[2],previous=str(left),next=str(right),unobserved_minute_labels=n,classification='UNOBSERVED_NOT_INTERPOLATED; may include auction or no-trade intervals'))
save('unobserved_intervals.csv',gaps)
summary=dict(source_files_audited=len(sources),actual_bar_sources=sum(s['rows_2025']>0 for s in sources),union_contract_rows=len(allrows),conflicts=len(conflicts),full_year_continuity_confirmed=all(x['regular_days']>0 for x in monthly),strategy_run=False,downloads=False,protected_oos_read=False,originals_modified=False)
(OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps(dict(summary=summary,monthly=monthly),ensure_ascii=False),flush=True)
