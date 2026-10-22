from pathlib import Path
import csv,json,re,zipfile,tarfile,time
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'inventory'
archives=list(csv.DictReader((OUT/'archives.csv').open()))
protected=re.compile(r'final[_ -]?oos|forward[_ -]?oos|protected[_ -]?oos|holdout',re.I)
summaries=[];candidates=[]
with (OUT/'archive_member_metadata.csv').open('w',encoding='utf8',newline='') as out:
 w=csv.DictWriter(out,fieldnames=['archive','member','bytes','is_file','protected_path']);w.writeheader()
 for a in archives:
  p=Path(a['path']);count=0;found=0;error=''
  if a['protected_path']=='True':summaries.append(dict(archive=str(p),members=0,candidates=0,status='PROTECTED_CONTAINER_NOT_OPENED',error=''));continue
  try:
   if p.suffix.lower()=='.zip':
    with zipfile.ZipFile(p) as z:entries=[(e.filename,e.file_size,not e.is_dir()) for e in z.infolist()]
    iterator=iter(entries);handle=None
   elif p.name.lower().endswith(('.tar','.tar.gz','.tgz','.tar.bz2','.tbz2','.tar.xz','.txz')):
    handle=tarfile.open(p,'r:*');iterator=((e.name,e.size,e.isfile()) for e in handle)
   else:raise ValueError('ARCHIVE_FORMAT_NOT_SUPPORTED_BY_STDLIB')
   try:
    for name,size,fileflag in iterator:
     low=(str(p)+'/'+name).lower();prot=bool(protected.search(low));w.writerow(dict(archive=str(p),member=name,bytes=size,is_file=fileflag,protected_path=prot));count+=1
     if not fileflag or prot or not name.lower().endswith(('.csv','.csv.gz','.parquet','.json','.jsonl','.ndjson','.log','.txt')):continue
     market=bool(re.search(r'krx|future|dollar|달러|선물',low));year='2025' in name.lower() or bool(re.search(r'175w[0-9abc]|a755',name.lower()));bars=bool(re.search(r'1m|1min|minute|분봉|bars|raw|ohlcv',name.lower()))
     if market and (year or bars):candidates.append(dict(archive=str(p),member=name,bytes=size,protected_path=prot,explicit_2025=year,bar_hint=bars));found+=1
   finally:
    if handle:handle.close()
  except (OSError,ValueError,tarfile.TarError,zipfile.BadZipFile) as e:error=type(e).__name__+':'+str(e)[:180]
  summaries.append(dict(archive=str(p),members=count,candidates=found,status='INDEXED' if not error else 'ERROR',error=error));print(json.dumps(dict(event='ARCHIVE_INDEXED',number=len(summaries),members=count,candidates=found,status=summaries[-1]['status'])),flush=True)
for n,rows in [('archive_index_summary.csv',summaries),('archive_candidates.csv',candidates)]:
 if rows:
  with (OUT/n).open('w',encoding='utf8',newline='') as f:w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
print(json.dumps(dict(archives=len(summaries),members=sum(s['members'] for s in summaries),candidates=len(candidates),errors=sum(s['status']=='ERROR' for s in summaries),protected_contents_read=False)),flush=True)
