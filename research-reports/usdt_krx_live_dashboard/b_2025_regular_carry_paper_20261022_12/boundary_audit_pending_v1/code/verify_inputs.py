# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
# How to run: python -B code/bootstrap.py verify_inputs.py; no prices simulated.
from pathlib import Path
import csv,json,hashlib
ROOT=Path(__file__).resolve().parents[1]
PRIOR=Path(r'D:/Codex_Research/usdt_krx_live_dashboard/studies/b_2025_quote_paper_20261022_11')
SOURCE=Path(r'D:/Codex_Research/usdt_krx_live_dashboard/studies/github_2025_quote_log_audit_20261022/v1')
rows=[]
for source,manifest in ((PRIOR/'publish_payload',PRIOR/'publish_payload/manifest.csv'),(SOURCE,SOURCE/'publish_payload/local_artifact_hashes.csv')):
    with manifest.open(encoding='utf-8-sig') as f:
        for r in csv.DictReader(f):
            p=source/r['path'];b=p.read_bytes();h=hashlib.sha256(b).hexdigest();assert len(b)==int(r['bytes']) and h==r['sha256']
            rows.append(dict(path=str(p),bytes=len(b),sha256=h,passed=True))
with (ROOT/'results/input_integrity.csv').open('w',encoding='utf8',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
print(json.dumps(dict(input_checks=len(rows),all_pass=True,downloads=0,old_results_modified=False)))
