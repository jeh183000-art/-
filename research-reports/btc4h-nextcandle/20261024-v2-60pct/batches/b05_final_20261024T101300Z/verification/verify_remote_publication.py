"""Read public immutable GitHub bytes and compare the explicit research manifest."""
from pathlib import Path
import argparse
import concurrent.futures
import csv
import gzip
import hashlib
import json
import re
import urllib.request

p=argparse.ArgumentParser()
p.add_argument('--batch',type=Path,required=True)
p.add_argument('--commit',required=True)
p.add_argument('--prefix',required=True)
args=p.parse_args()
if not re.fullmatch('[a-f0-9]{40}',args.commit):
    raise SystemExit('Exact commit required')
if not args.prefix.startswith('research-reports/') or '..' in args.prefix:
    raise SystemExit('Invalid prefix')
entries=list(csv.DictReader((args.batch/'manifest.csv').open()))
manifest=args.batch/'manifest.csv'
entries.append({'path':'manifest.csv','bytes':str(manifest.stat().st_size),'sha256':hashlib.sha256(manifest.read_bytes()).hexdigest()})

def verify(item):
    relative=item['path']
    if '..' in Path(relative).parts or Path(relative).is_absolute():
        raise ValueError('Unsafe artifact path')
    url=f'https://raw.githubusercontent.com/jeh183000-art/-/{args.commit}/{args.prefix}/{relative}'
    request=urllib.request.Request(url,headers={'User-Agent':'BTC15-classification-byte-verification'})
    with urllib.request.urlopen(request,timeout=30) as response:
        blob=response.read()
    digest=hashlib.sha256(blob).hexdigest()
    if len(blob)!=int(item['bytes']) or digest!=item['sha256']:
        raise ValueError('Remote byte mismatch: '+relative)
    if blob!=(args.batch/relative).read_bytes():
        raise ValueError('Remote local comparison mismatch: '+relative)
    if relative.endswith('.gz'):
        expanded=gzip.decompress(blob)
        if relative.endswith('.csv.gz') and b'prediction_time' not in expanded.splitlines()[0]:
            raise ValueError('Invalid forecast CSV header: '+relative)
    return {'path':relative,'bytes':len(blob),'sha256':digest,'status':'MATCH'}

verified=[]
failures=[]
with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
    tasks={pool.submit(verify,item):item['path'] for item in entries}
    for future in concurrent.futures.as_completed(tasks):
        path=tasks[future]
        try:
            verified.append(future.result())
            if len(verified)%20==0:
                print(json.dumps({'verified':len(verified),'total':len(entries)}),flush=True)
        except Exception as exc:
            failures.append({'path':path,'error':f'{type(exc).__name__}: {exc}'})
status='PUBLISHED_VERIFIED' if not failures and len(verified)==len(entries) else 'REMOTE_VERIFICATION_FAILED'
receipt={'status':status,'repository':'jeh183000-art/-','commit':args.commit,'prefix':args.prefix,
         'verified_count':len(verified),'expected_count':len(entries),'failures':failures,
         'checks':['exact immutable commit URL','remote SHA256','remote byte size','byte-for-byte local equality','gzip decompression'],
         'files':sorted(verified,key=lambda x:x['path'])}
(args.batch.parent/'publication_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps({k:v for k,v in receipt.items() if k!='files'},indent=2))
if failures:
    raise SystemExit(1)
