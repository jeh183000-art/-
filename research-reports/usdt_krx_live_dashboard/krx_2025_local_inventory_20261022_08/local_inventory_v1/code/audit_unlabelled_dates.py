from pathlib import Path
import csv,gzip,re,json
ROOT=Path(__file__).resolve().parents[1];out=[]
for x in csv.DictReader((ROOT/'inventory/data_candidates.csv').open()):
 p=Path(x['path'])
 if '2025' in str(p) or x['protected_path']=='True' or not str(p).endswith(('.csv','.csv.gz')):continue
 if re.search(r'2026',p.name):continue
 if not re.search(r'1m|minute|bars|ohlcv|historical',str(p),re.I):continue
 stamps=[];n2025=0;fields=[]
 try:
  opener=gzip.open if p.name.endswith('.gz') else open
  with opener(p,'rt',encoding='utf-8-sig',newline='') as f:
   reader=csv.DictReader(f);fields=reader.fieldnames or [];key=next((k for k in ['trade_date','stck_bsop_date','business_date','actual_kst','timestamp_kst'] if k in fields),None)
   if key:
    for r in reader:
     s=r.get(key,'');year=s[:4]
     if re.match(r'^20[0-9]{2}',s):stamps.append(s);n2025+=year=='2025'
  out.append(dict(path=str(p),date_field=key or '',first=min(stamps) if stamps else '',last=max(stamps) if stamps else '',date_rows=len(stamps),date_rows_2025=n2025,price_fields_used=False))
 except (OSError,ValueError) as e:out.append(dict(path=str(p),date_field='',first='',last='',date_rows=0,date_rows_2025=0,price_fields_used=False))
with (ROOT/'audit/unlabelled_date_metadata.csv').open('w',encoding='utf8',newline='') as f:w=csv.DictWriter(f,fieldnames=list(out[0]));w.writeheader();w.writerows(out)
print(json.dumps(dict(files=len(out),with_2025_dates=[r for r in out if r['date_rows_2025']],prices_analyzed=False)))
