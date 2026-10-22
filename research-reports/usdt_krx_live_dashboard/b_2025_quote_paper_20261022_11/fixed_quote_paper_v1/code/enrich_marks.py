# /// script
# requires-python = ">=3.12"
# dependencies = ["numpy==2.2.6"]
# ///
# How to run: python -B code/bootstrap.py enrich_marks.py; no trading or recomputation of fills.
import collections,gzip,shutil
from common import OUT,PUB,read_csv,table,save,sha
from model import frozen_drawdowns,INITIAL_F
rows=read_csv(OUT/'all_valuation_ledger.csv');groups=collections.defaultdict(list)
for r in rows:
    key=(r['variant'],r['scope'],r['segment'] if r['scope']=='INDEPENDENT_EPISODE' else 'ONE_CONTINUOUS_ACCOUNT')
    groups[key].append(r)
for key,rs in groups.items():
    rs.sort(key=lambda r:r['t']);trace=frozen_drawdowns([float(r['combined_equity']) for r in rs]);peak=INITIAL_F;maximum=0.
    for r,(p,dd,mdd) in zip(rs,trace):
        value=float(r['combined_equity']);peak=max(peak,value);maximum=max(maximum,peak-value)
        assert abs(p-peak)<.0001 and abs(dd-(peak-value))<.0001 and abs(mdd-maximum)<.0001
        r.update(running_equity_peak=float(p),current_drawdown=float(dd),cumulative_mdd=float(mdd),future_account_equity=float(r['future_cash'])+float(r['future_unrealized']))
path=OUT/'valuation_ledger_with_dd.csv';table(path,rows)
with path.open('rb') as src,gzip.open(PUB/'valuation_ledger.csv.gz','wb') as dst:shutil.copyfileobj(src,dst)
packed=(PUB/'valuation_ledger.csv.gz').read_bytes();unpacked=gzip.decompress(packed)
assert sha(unpacked)==sha(path.read_bytes())
save(PUB/'archive_verification.json',dict(archive='valuation_ledger.csv.gz',compressed_bytes=len(packed),compressed_sha256=sha(packed),uncompressed_bytes=len(unpacked),uncompressed_sha256=sha(unpacked),local_lossless_match=True,rows=len(rows),groups=len(groups),mdd_never_decreases_in_each_account=True,contains='own financial ledger; no full source quote table'))
print(dict(rows=len(rows),account_groups=len(groups),mdd_columns_verified=True))
