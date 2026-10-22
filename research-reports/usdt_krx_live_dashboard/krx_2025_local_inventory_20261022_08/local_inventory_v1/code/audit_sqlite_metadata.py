from pathlib import Path
import sqlite3,csv,json,re,datetime
ROOT=Path(__file__).resolve().parents[1];rows=[]
for r in csv.DictReader((ROOT/'inventory/all_file_metadata.csv').open()):
 p=Path(r['path'])
 if p.name!='live.sqlite3' or 'usdt_krx_live_dashboard' not in str(p):continue
 con=sqlite3.connect(p.as_uri()+'?mode=ro',uri=True,timeout=2);con.execute('PRAGMA query_only=ON')
 for (name,) in con.execute("SELECT name FROM sqlite_master WHERE type='table'"):
  if not re.search(r'krx|futur|candle|bar|tick',name,re.I) or re.search('oos|holdout',name,re.I):continue
  cols=[x[1] for x in con.execute('PRAGMA table_info("'+name.replace('"','""')+'")')]
  dates=[c for c in cols if re.search(r'timestamp|time|date|_ts$',c,re.I)]
  counts={}
  for c in dates:
   q='"'+c.replace('"','""')+'"';n='"'+name.replace('"','""')+'"'
   # Metadata count only; do not retrieve any protected-year price.
   lo=int(datetime.datetime(2025,1,1,tzinfo=datetime.timezone(datetime.timedelta(hours=9))).timestamp());hi=int(datetime.datetime(2026,1,1,tzinfo=datetime.timezone(datetime.timedelta(hours=9))).timestamp())
   clauses=['CAST('+q+' AS TEXT) LIKE ?'];params=['2025%']
   for factor in (1,1000,1000000,1000000000):clauses.append('(CAST('+q+' AS REAL)>=? AND CAST('+q+' AS REAL)<?)');params.extend([lo*factor,hi*factor])
   counts[c]=con.execute('SELECT COUNT(*) FROM '+n+' WHERE '+' OR '.join(clauses),params).fetchone()[0]
  rows.append(dict(path=str(p),table=name,date_columns=dates,rows_in_calendar2025_iso_or_epoch=counts,prices_read=False))
 con.close()
(ROOT/'audit/sqlite_metadata.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps(rows))
