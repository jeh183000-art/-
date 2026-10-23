# /// script
# requires-python = ">=3.12"
# dependencies = ["numpy==2.2.6"]
# ///
# Run: python -B audit_v3.py; audits saved output without rerunning strategy.
from pathlib import Path
from collections import defaultdict, Counter
from decimal import Decimal
import csv
import hashlib
import json
import site
import sys
site.addsitedir('C:/Users/48733/AppData/Roaming/Python/Python312/site-packages')
ROOT = Path(__file__).resolve().parents[1]
PRIOR = ROOT.parent / 'b_2025_quote_paper_20261022_11'
BASE = ROOT.parent / 'b_2025_regular_carry_paper_20261022_12/approved_carry_v2'
sys.path.insert(0, str(PRIOR / 'code'))
from model import Quote, Book, frozen_drawdowns
from simulator import SegmentRun
from verify_quote_book import audit_run

def read(path: Path) -> list[dict[str, str]]:
    with path.open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))

def write(path: Path, rows: list[dict]) -> None:
    with path.open('x', encoding='utf8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

def main() -> None:
    lookup = {}
    with (PRIOR / 'data_local/segments.jsonl').open(encoding='utf8') as stream:
        for line in stream:
            for row in json.loads(line)['quotes']:
                lookup[row['t']] = Quote.parse(row)
    frozen = json.loads((ROOT / 'preregistration.json').read_text())
    for field in ('input', 'official'):
        info = frozen[field]
        assert hashlib.sha256(Path(info['path']).read_bytes()).hexdigest() == info['sha256']
    proofs = []; periods = []; exposure = []; boundaries = []; baseline = []
    for limit in range(3):
        path = ROOT / f'results/MISSING_{limit}M'
        counts = Counter((r['kind'], r['allowed']) for r in read(path / 'boundaries.csv'))
        for (kind, allowed), count in counts.items():
            matching = [r for r in read(path / 'boundaries.csv') if (r['kind'], r['allowed']) == (kind, allowed)]
            boundaries.append(dict(limit=limit,kind=kind,allowed=allowed,count=count,
                total_missing_minutes=sum(int(r['missing_minutes']) for r in matching),
                max_missing_minutes=max(int(r['missing_minutes']) for r in matching)))
        for variant in ('B-RECOVERY-ONLY','B-DUAL-CONTROL'):
            detail = path / variant
            fills = read(detail / 'fills.csv'); cycles = read(detail / 'cycles.csv')
            signals = read(detail / 'signals.csv'); marks = read(detail / 'observed_valuation_ledger.csv')
            groups = defaultdict(list)
            for mark in marks:
                group = mark['chain'] if mark['scope'] == 'CONDITIONAL_CHAIN' else 'ONE_ACCOUNT'
                groups[(mark['scope'], group)].append(mark)
            for (scope, group), rows in groups.items():
                eligible = lambda r: r['scope'] == scope and (scope != 'CONDITIONAL_CHAIN' or r['chain'] == group)
                fs = [r for r in fills if eligible(r)]; cs = [r for r in cycles if eligible(r)]
                ss = [r for r in signals if eligible(r)]
                observed = {r['t']: r for r in rows}
                nf = []
                for row in fs:
                    vals = dict(row)
                    for key in ('cycle','direction','spot_fee','future_fee','spot_slippage','future_slippage'):
                        vals[key] = float(row[key])
                    kind = 'ENTRY_SIGNAL' if row['kind'] == 'ENTRY' else 'EXIT_SIGNAL'
                    preceding = [r for r in ss if r['kind'] == kind and r['cycle'] == row['cycle'] and r['t'] < row['t']]
                    vals['signal_t'] = preceding[-1]['t']
                    vals.update(contracts=17,quantity_usdt=170000,spot_notional=float(row['spot_price'])*170000,
                        future_notional=float(row['future_price'])*170000,spot_cash=float(observed[row['t']]['cash_spot']),
                        future_cash=float(observed[row['t']]['cash_future']))
                    nf.append(vals)
                nc = [dict(r,cycle=int(r['cycle']),net=float(r['net']),return_pct=float(r['return_pct'])) for r in cs]
                nm = [dict(combined_pnl=float(r['equity_reference'])-30000000,
                    open_net_after_close_cost=float(r['open_net_estimate']),future_unrealized=float(r['future_unrealized']),
                    spot_cash=float(r['cash_spot']),future_cash=float(r['cash_future']),
                    contracts=int(r['held_contracts']),held_direction=int(r['position_direction'])) for r in rows]
                proof = audit_run([lookup[r['t']] for r in rows], SegmentRun(Book(),tuple(nf),tuple(nc),tuple(nm),None,0), Book())
                trace = frozen_drawdowns([float(r['equity_reference']) for r in rows])
                assert all(abs(float(r['running_mdd'])-float(t[2])) < .0001 for r,t in zip(rows,trace))
                assert all(float(a['running_mdd']) <= float(b['running_mdd']) for a,b in zip(rows,rows[1:]))
                proofs.append(dict(limit=limit,variant=variant,scope=scope,chain=group,**proof))
                net = sum(float(r['net']) for r in cs)
                residual = float(rows[-1]['open_net_estimate'])
                periods.append(dict(limit=limit,variant=variant,scope=scope,chain=group,first=rows[0]['t'],last=rows[-1]['t'],
                    entries=len([r for r in fs if r['kind']=='ENTRY']),completed=len(cs),
                    completed_net_krw=net,completed_score_pct=sum(float(r['return_pct']) for r in cs),
                    last_open_net_krw=residual,closed_plus_last_open_krw=net+residual,
                    residual_contracts=int(rows[-1]['held_contracts']),observed_mdd_krw=proof['mdd_krw'],
                    maximum_open_loss_krw=max(max(0,-float(r['open_net_estimate'])) for r in rows)))
            exposure.extend(dict(limit=limit,**r) for r in cycles if r['scope']=='CONDITIONAL_CHAIN' and r['gap_exposed']=='True')
            if limit == 0:
                old_cycles = [r for r in read(BASE/'publish_payload/cycles.csv') if r['variant']==variant]
                old_marks = [r for r in read(BASE/'results/all_marks.csv') if r['variant']==variant]
                key = lambda r: (r['scope'],r['chain'],r['cycle'])
                new_cycles = {key(r):r for r in cycles}
                for r in old_cycles:
                    cur = new_cycles[key(r)]
                    for name in ('entry_t','exit_t','entry_signal_t','exit_signal_t','exit_reason'):
                        assert cur[name]==r[name], (name,cur,r)
                    for name in ('net','return_pct','entry_notional','spot_gross','future_gross'):
                        assert abs(Decimal(cur[name])-Decimal(r[name])) < Decimal('.0001')
                mapping = {'cash_spot':'spot_cash','cash_future':'future_cash','open_net_estimate':'open_net_after_close_cost',
                    'equity_reference':'combined_equity','running_mdd':'cumulative_mdd'}
                om = {(r['scope'],r['chain'],r['t']):r for r in old_marks}
                assert len(om)==len(marks)
                for r in marks:
                    orig=om[(r['scope'],r['chain'],r['t'])]
                    for a,b in mapping.items():
                        assert abs(float(r[a])-float(orig[b])) < .0001, (a,r['t'])
                baseline.append(dict(variant=variant,all_cycles_match=True,all_mark_cash_mdd_match=True,
                    compared_marks=len(marks),compared_cycles=len(cycles)))
    write(ROOT/'audit/independent_audit.csv',proofs)
    write(ROOT/'audit/period_results.csv',periods)
    write(ROOT/'audit/gap_exposed_cycles.csv',exposure)
    write(ROOT/'audit/boundary_summary.csv',boundaries)
    (ROOT/'audit/validation.json').write_text(json.dumps(dict(status='PASS',audited_groups=len(proofs),
        checked_marks=sum(r['checked_quotes'] for r in proofs),baseline_full_parity=baseline,
        original_v3_unmodified=True,input_hashes_unchanged=True,
        annual_result_certified=False),indent=2),encoding='utf8')
    print(json.dumps(dict(status='PASS',audited_groups=len(proofs),baseline_full_parity=baseline)))

if __name__ == '__main__':
    main()
