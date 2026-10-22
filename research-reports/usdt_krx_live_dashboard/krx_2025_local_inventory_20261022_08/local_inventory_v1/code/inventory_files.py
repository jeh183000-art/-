from pathlib import Path
import os,re,csv,json,time,collections
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'inventory';OUT.mkdir(exist_ok=True)
ROOTS=[Path('D:/Codex_Research'),Path('C:/Users/48733/Documents/Codex')]
protected=re.compile(r'final[_ -]?oos|forward[_ -]?oos|protected[_ -]?oos|holdout',re.I)
archive_re=re.compile(r'\.(zip|tar|tar\.gz|tgz|tar\.bz2|tbz2|7z|rar|tar\.xz|txz)$',re.I)
data_ext=('.csv','.csv.gz','.parquet','.json','.jsonl','.ndjson','.txt','.log')
errors=[];archives=[];candidates=[];count=0;top=collections.Counter()
with (OUT/'all_file_metadata.csv').open('w',encoding='utf8',newline='') as stream:
 w=csv.DictWriter(stream,fieldnames=['path','bytes','mtime_ns','protected_path']);w.writeheader()
 for root in ROOTS:
  if not root.exists():errors.append(dict(path=str(root),error='ROOT_NOT_PRESENT'));continue
  for directory,dirs,files in os.walk(root,followlinks=False):
   # Do not traverse generated output of this new audit; original repository objects and installed runtime are not research datasets.
   dirs[:]=[d for d in dirs if d not in ['.git','node_modules','__pycache__'] and not (Path(directory)/d).is_symlink() and str(Path(directory)/d)!=str(ROOT)]
   for name in files:
    p=Path(directory)/name
    try:st=p.stat()
    except OSError as e:errors.append(dict(path=str(p),error=type(e).__name__));continue
    text=str(p);low=text.lower();prot=bool(protected.search(text));w.writerow(dict(path=text,bytes=st.st_size,mtime_ns=st.st_mtime_ns,protected_path=prot));count+=1
    if archive_re.search(name):archives.append(dict(path=text,bytes=st.st_size,protected_path=prot))
    if not name.lower().endswith(data_ext) or name.lower().startswith('.env'):continue
    market=bool(re.search(r'krx|future|dollar|달러|선물',low))
    year='2025' in low or bool(re.search(r'175w[0-9abc]|a755',low))
    bar=bool(re.search(r'1m|1min|minute|분봉|bars|raw|ohlcv',low))
    if market and (year or bar):candidates.append(dict(path=text,bytes=st.st_size,protected_path=prot,selection='MARKET_AND_YEAR_OR_BAR_METADATA_ONLY'))
    if count%50000==0:print(json.dumps(dict(event='FILES_LISTED',count=count)),flush=True)
def savecsv(n,rows):
 if not rows:return
 with (OUT/n).open('w',encoding='utf8',newline='') as f:w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
savecsv('archives.csv',archives);savecsv('data_candidates.csv',candidates);savecsv('errors.csv',errors)
summary=dict(files=count,data_candidates=len(candidates),archives=len(archives),errors=len(errors),roots=list(map(str,ROOTS)),only_metadata=True,protected_contents_read=False,download_performed=False)
(OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps(summary,ensure_ascii=False),flush=True)
