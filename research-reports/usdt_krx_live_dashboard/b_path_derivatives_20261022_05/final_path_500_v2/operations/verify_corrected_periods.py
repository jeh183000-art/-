# /// script
# requires-python = "==3.12.0"
# dependencies = []
# ///
# Validate corrected month/quarter tables with strptime, independently of fromisoformat.
from __future__ import annotations
import csv,gzip,json
from datetime import datetime
from collections import defaultdict
from runner import ROOT,table,write_json
out=ROOT/'publish_payloads/final_path_500_v2'
with (out/'diagnostics/monthly_contribution.csv').open(encoding='utf8',newline='') as stream:
    months={(r['candidate_id'],r['exit_business_month']):r for r in csv.DictReader(stream)}
with (out/'diagnostics/quarterly_contribution.csv').open(encoding='utf8',newline='') as stream:
    quarters={(r['candidate_id'],r['exit_business_quarter']):r for r in csv.DictReader(stream)}
assert len(months)==5000 and len(quarters)==2000
checks=[]
for p in sorted((ROOT/'batches').glob('batch_*/candidates/*/cycles.csv.gz')):
    expected_month=defaultdict(list);expected_quarter=defaultdict(list)
    with gzip.open(p,'rt',encoding='utf8',newline='') as stream:
        cycles=list(csv.DictReader(stream))
    for r in cycles:
        raw=r['exit_business_date']
        d=datetime.strptime(raw,'%Y-%m-%d' if '-' in raw else '%Y%m%d')
        expected_month[d.strftime('%Y-%m')].append(r)
        expected_quarter[f'{d.year}-Q{(d.month-1)//3+1}'].append(r)
    for label,source,actual in [('month',expected_month,months),('quarter',expected_quarter,quarters)]:
        keys=[f'2026-{m:02d}' for m in range(1,11)] if label=='month' else [f'2026-Q{q}' for q in range(1,5)]
        for key in keys:
            values=source[key];target=actual[(p.parent.name,key)]
            assert int(target['cycles'])==len(values)
            assert abs(float(target['net_krw'])-sum(float(r['net']) for r in values))<.01
            assert abs(float(target['score_pct'])-sum(float(r['return_pct']) for r in values))<1e-8
    checks.append(dict(candidate_id=p.parent.name,status='PASS',cycles=len(cycles),monthly_and_quarterly_totals_exact_within_registered_tolerance=True))
assert len(checks)==500
table(out/'diagnostics/period_totals_independent_validation.csv',checks)
write_json(out/'diagnostics/period_totals_independent_validation.json',dict(status='PASS',conditions=500,cycles=sum(r['cycles'] for r in checks),
    monthly_rows=5000,quarterly_rows=2000,second_parser='datetime.strptime',
    raw_business_date='YYYYMMDD preserved in original ledgers',normalized_format='YYYY-MM / YYYY-QN',
    financial_simulation_repeated=False,score_or_trade_ledger_modified=False))
print('PASS_INDEPENDENT_PERIOD_LABELS_AND_TOTALS_500',flush=True)
