# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
# How to run: python -B code/inspect_boundaries.py; read-only classification, no simulation.
from pathlib import Path
import csv,json,hashlib,datetime as dt
ROOT=Path(__file__).resolve().parents[1]
PRIOR=Path(r'D:/Codex_Research/usdt_krx_live_dashboard/studies/b_2025_quote_paper_20261022_11')
ARCH=Path(r'D:/Codex_Research/archive/c_drive_migration_20261020/codex_workspace/files-pasted-by-the-user-codex/outputs/usdt_krx_live_dashboard/data')
def read(p:Path)->list:
    with p.open(encoding='utf-8-sig') as f:return list(csv.DictReader(f))
def table(p:Path,rows:list)->None:
    with p.open('w',encoding='utf8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]) if rows else ['status']);w.writeheader();w.writerows(rows)
official={r['date']:r for r in read(ARCH/'krx_2025_full_1m/contract_selection.csv') if r['date'].startswith('2025')}
days=sorted(official);ranks={d:i for i,d in enumerate(days)}
segments=[]
with (PRIOR/'data_local/segments.jsonl').open(encoding='utf8') as f:
    for line in f:segments.append(json.loads(line))
rows=[]
for left,right in zip(segments,segments[1:]):
    a=left['quotes'][-1];b=right['quotes'][0];ta=dt.datetime.fromisoformat(a['t']);tb=dt.datetime.fromisoformat(b['t']);da=ta.strftime('%Y%m%d');db=tb.strftime('%Y%m%d')
    consecutive_dates=da in ranks and db in ranks and ranks[db]==ranks[da]+1
    same=official[da]['contract_code_kis']==official[db]['contract_code_kis']
    live_a=official[da]['expiry_date']>=ta.date().isoformat();live_b=official[db]['expiry_date']>=tb.date().isoformat()
    volume= float(official[da]['official_volume'])>0 and float(official[db]['official_volume'])>0
    clock=ta.time()==dt.time(15,30) and tb.time()==dt.time(9)
    reasons=[]
    if ta.date()==tb.date():reasons.append('INTRADAY_MISSING_PRICE')
    if not same:reasons.append('REFERENCE_CONTRACT_CHANGE_NO_ROLL_QUOTES')
    if ta.date()!=tb.date() and not consecutive_dates:reasons.append('MISSING_OFFICIAL_TRADING_DATES')
    if ta.date()!=tb.date() and not clock:reasons.append('LOGGER_WINDOW_EDGE_PRICE_MISSING')
    reference_eligible=ta.date()!=tb.date() and consecutive_dates and same and live_a and live_b and volume and clock
    rows.append(dict(before=a['t'],after=b['t'],left_segment=left['segment'],right_segment=right['segment'],calendar_elapsed_hours=(tb-ta).total_seconds()/3600,next_official_trading_date=consecutive_dates,same_reference_contract=same,reference_contract_a=official[da]['contract_code_kis'],reference_contract_b=official[db]['contract_code_kis'],reference_expiry_a=official[da]['expiry_date'],reference_expiry_b=official[db]['expiry_date'],reference_traded_both_days=volume,logger_1530_to_0900=clock,strict_actual_log_contract_confirmed=False,reference_based_carry_requires_extra_assumption=reference_eligible,strict_1545_coverage_confirmed=False,risk_reasons=';'.join(reasons) if reasons else 'NORMAL_CALENDAR_CLOSURE_UNDER_LOGGER_WINDOW_ASSUMPTION'))
table(ROOT/'results/boundary_classification.csv',rows)
summary=dict(boundaries=len(rows),reference_based_potential_bridges=sum(r['reference_based_carry_requires_extra_assumption'] for r in rows),strict_proven_actual_contract_bridges=0,strict_full_regular_close_coverage_bridges=0,reference_changes=sum(not r['same_reference_contract'] for r in rows),intraday_missing_boundaries=sum('INTRADAY' in r['risk_reasons'] for r in rows),missing_trading_date_boundaries=sum('MISSING_OFFICIAL' in r['risk_reasons'] for r in rows),no_overnight_prices_created=True)
(ROOT/'results/boundary_summary.json').write_text(json.dumps(summary,indent=2),encoding='utf8');print(json.dumps(summary))
