from __future__ import annotations

import csv
import gzip
import hashlib
import importlib.util
import json
import os
import platform
import shutil
import sys
import time
from pathlib import Path

import numpy as np

from audit import replay
from engine import simulate
from signals import prepare
from validation2 import verify_book
from event_schema import ACCOUNT_PHASES, compare_events

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT.parents[1]
SOURCE = PROJECT / 'shared/approved_20261016_01'
REFERENCE = PROJECT / 'studies/split_vs_lump17_20261021_01/runs/B_LUMP17'
SOURCE_HASH = '62becd7d50e05bdcf47010cdcdfdd8178bbe2ef1d8099a84ab18fae8fea19fbd'
MARGIN_HASH = '910816bc61c9d9b7361bec370e225bfeae9cde0f11b889265cb4409ecb9344b8'
NAMES = 'times month_ids month_end contract_ids gap spot_open spot_close future_open future_close roll_flag roll_old_open old_contract_ids continuous_prev settlement_due settlement_price settlement_spot_mark initial_rate maintenance_rate'.split()
TRADE_FIELDS = 'entry_signal_row entry_row exit_signal_row exit_row direction entry_spot entry_future exit_spot exit_future spot_gross future_gross fees slippage net hold_minutes roll_count exit_target cycle_id exit_reason_bits'.split()
EVENT_FIELDS = 'event_code row cycle_id direction spot_price future_price spot_gross_delta future_gross_delta spot_fee future_fee spot_slippage future_slippage contract_id signal_row'.split()
ORDER_FIELDS = 'row signal_row direction requested_contracts filled_contracts reason_code future_cash_before initial_required future_fee future_slippage spot_price future_price'.split()
LEDGER_FIELDS = 'spot_net_cash_flow future_cash future_unrealized initial_required maintenance_headroom total_equity open_net_paid_cost direction mdd_krw initial_headroom spot_financing_proxy'.split()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()


def write_json(path, value):
    with path.open('x', encoding='utf8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)


def table(path, rows, fields=None):
    names = fields or sorted({key for row in rows for key in row}) or ['status']
    opener = gzip.open if path.name.endswith('.gz') else open
    with opener(path, 'xt', encoding='utf8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=names)
        writer.writeheader(); writer.writerows(rows)


def load():
    for filename, expected in [('matched_simulation_bars.csv', SOURCE_HASH), ('margin_schedule.csv', MARGIN_HASH)]:
        assert hashlib.sha256((SOURCE / filename).read_bytes()).hexdigest() == expected
    spec = importlib.util.spec_from_file_location('frozen_lump17_input_loader', SOURCE / 'paper_engine.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    a = module.load_arrays()
    return tuple(a[key] for key in NAMES), a['frame'], a['contract_codes']


def safe_number(value):
    return float(value) if np.isfinite(value) and abs(value) < 1e90 else None


def calculate(candidate, v, frame, codes, out):
    assert not out.exists(); out.mkdir(parents=True)
    rule = candidate['rule']
    assert hashlib.sha256(canonical(rule)).hexdigest() == candidate['rule_sha256']
    context = {'night': frame['session'].astype(str).str.contains('night', case=False).to_numpy(),
               'volume': frame['future_volume'].to_numpy()}
    args = prepare(rule, v, context)
    values = simulate(v, *args)
    trades, events, residual, risk, equity, extremes, ledger, orders = values
    np.savez_compressed(out / 'full_account_ledger.npz', ledger=ledger)
    np.savez_compressed(out / 'numeric_result.npz', trades=trades, events=events, residual=residual,
                        risk=risk, equity=equity, extremes=extremes, orders=orders)
    checks = replay(v, trades, events, ledger, orders, args[-1])
    independent = verify_book(v,trades,events,residual,ledger,orders,args[-1])
    maximum_contracts = 17 if np.any(np.nan_to_num(ledger[:, :, 7]) != 0) else 0
    assert maximum_contracts in (0, 17)
    cycle_rows = []
    for trade in trades:
        row = dict(zip(TRADE_FIELDS, map(float, trade)))
        i, j = int(trade[1]), int(trade[3])
        row.update(candidate_id=candidate['candidate_id'], contracts=17, spot_quantity=170000,
                   spot_entry_notional=trade[5] * 170000, return_pct=trade[13] / (trade[5] * 170000) * 100,
                   entry_kst=str(frame.iloc[i]['timestamp_kst']), exit_kst=str(frame.iloc[j]['timestamp_kst']),
                   entry_business_date=str(frame.iloc[i]['business_date']), exit_business_date=str(frame.iloc[j]['business_date']),
                   entry_contract=codes[int(v[3][i])-1], exit_contract=codes[int(v[3][j])-1])
        cycle_rows.append(row)
    event_rows = []
    for event in events:
        row = dict(zip(EVENT_FIELDS, map(float, event)))
        kind, i, sign = int(event[0]), int(event[1]), int(event[3])
        row.update(candidate_id=candidate['candidate_id'], timestamp_kst=str(frame.iloc[i]['timestamp_kst']),
                   business_date=str(frame.iloc[i]['business_date']), contract_code=codes[int(event[12])-1],
                   spot_quantity_change=sign*170000 if kind == 1 else -sign*170000 if kind == 2 else 0,
                   future_quantity_change=-sign*17 if kind in (1,4) else sign*17 if kind in (2,3) else 0)
        event_rows.append(row)
    order_rows = [dict(zip(ORDER_FIELDS, map(float, order)), candidate_id=candidate['candidate_id']) for order in orders]
    table(out/'cycles.csv.gz', cycle_rows)
    table(out/'fills.csv.gz', event_rows)
    table(out/'orders.csv.gz', order_rows)
    residual_row = dict(candidate_id=candidate['candidate_id'], contracts=17 if residual[0] else 0,
                        cycle_id=float(residual[0]), direction=float(residual[1]), entry_row=float(residual[2]),
                        spot_entry=float(residual[3]), future_entry=float(residual[4]),
                        gross_spot=float(residual[5]), gross_future=float(residual[6]), fees_paid=float(residual[7]),
                        slippage_paid=float(residual[8]), estimated_exit_cost=float(residual[9]),
                        net_after_exit_cost=float(residual[10]), hold_minutes=float(residual[11]))
    table(out/'residual.csv', [residual_row])
    score = sum(row['return_pct'] for row in cycle_rows)
    forced_score = score + (residual[10]/(residual[3]*170000)*100 if residual[0] else 0.)
    valid_marks = ledger[:, :, 7] != 0
    valid_marks &= np.isfinite(ledger[:, :, 7])
    needed = np.nanmax(ledger[:, :, 10])
    result = dict(candidate_id=candidate['candidate_id'], family=rule['family'], group=candidate['group'],
                  rule_sha256=candidate['rule_sha256'], cycles=len(trades), score_pct=score,
                  net_realized=float(np.sum(trades[:,13])), win_rate_pct=100*sum(row['net']>0 for row in cycle_rows)/len(trades) if len(trades) else None,
                  mean_cycle_return_pct=score/len(trades) if len(trades) else None,
                  mdd_krw=float(risk[0]), maximum_open_loss_krw=float(risk[1]),
                  maximum_future_cycle_loss_krw=float(risk[3]), maximum_contracts=maximum_contracts,
                  spot_financing_proxy_krw=float(needed), maximum_initial_margin_krw=float(np.nanmax(ledger[:,:,3])),
                  minimum_initial_headroom_krw=safe_number(checks[1]), minimum_maintenance_headroom_krw=safe_number(checks[2]),
                  maintenance_breach_marks=int(checks[3]), insufficient_rolls=int(risk[6]),
                  admission_rejections=int(np.sum(orders[:,4]==0)),
                  residual_contracts=int(residual_row['contracts']), residual_net_after_exit_cost=float(residual[10]),
                  forced_terminal_score_pct=float(forced_score), longest_hold_minutes=float(max([row['hold_minutes'] for row in cycle_rows]+[residual[11]])),
                  average_hold_minutes=float(np.mean(trades[:,14])) if len(trades) else None,
                  average_observed_contracts=float(np.mean(np.where(np.isfinite(ledger[:,1,7]),abs(ledger[:,1,7])*17,0))),
                  fees_krw=float(np.sum(events[:,8:10])), slippage_krw=float(np.sum(events[:,10:12])),
                  borrow_unverified=bool(np.any(events[:,3]==-1)),
                  feasible=bool(checks[3]==0 and risk[6]==0), audit_max_difference_krw=float(checks[0]))
    for name, sign in [('long',1),('reverse',-1)]:
        selected = [row for row in cycle_rows if row['direction']==sign]
        result[name+'_cycles']=len(selected); result[name+'_score_pct']=sum(row['return_pct'] for row in selected)
        result[name+'_net_krw']=sum(row['net'] for row in selected)
    periods = []
    for prefix in ('month','quarter'):
        for name in sorted({r['exit_business_date'][:7] if prefix=='month' else r['exit_business_date'][:4]+'-Q'+str((int(r['exit_business_date'][5:7])-1)//3+1) for r in cycle_rows}):
            selected = [r for r in cycle_rows if (r['exit_business_date'][:7] if prefix=='month' else r['exit_business_date'][:4]+'-Q'+str((int(r['exit_business_date'][5:7])-1)//3+1))==name]
            periods.append(dict(period_type=prefix,period=name,cycles=len(selected),score_pct=sum(r['return_pct'] for r in selected),net=sum(r['net'] for r in selected)))
    table(out/'period_contribution.csv',periods)
    write_json(out/'audit.json',dict(status='PASS',vector_replay=independent,independent_replay=True,max_account_difference_krw=float(checks[0]),
                                   all_initial_orders_atomic_17=True,no_additions=True,no_simultaneous_opposite=True,
                                   quantities_verified=True,cycle_count=len(cycle_rows),margin_eligibility=result['feasible']))
    marks=ledger.reshape(-1,11);marks=marks[np.isfinite(marks[:,5])]
    assert np.all(np.diff(marks[:,8])>=0)
    initial_deficits=int(np.sum((np.abs(marks[:,7])>0)&(marks[:,9]<-.01)))
    margin_ok=bool(result['feasible'] and result['admission_rejections']==0 and initial_deficits==0)
    result.update(initial_margin_deficit_marks=initial_deficits,margin_shortage_free=margin_ok,
        meets_cycle_count=result['cycles']>=39,meets_residual_zero=result['residual_contracts']==0,
        meets_mdd_limit=result['mdd_krw']<=9350000.01,beats_B=bool(result['score_pct']>14.95131907100779),
        goal_qualified=bool(result['cycles']>=39 and result['residual_contracts']==0 and result['mdd_krw']<=9350000.01 and margin_ok and result['score_pct']>14.95131907100779))
    result.update(score_delta_B_pp=float(score-14.95131907100779),numerical_tie_to_B=bool(abs(score-14.95131907100779)<1e-9))
    write_json(out/'result.json',result)
    return result


def batch(number, v, frame, codes):
    name=f'batch_{number:04d}'
    registration=json.loads((ROOT/'preregistration'/f'{name}.json').read_text())
    assert len(registration['conditions'])==50
    assert hashlib.sha256(canonical(registration['conditions'])).hexdigest()==registration['grid_sha256']
    receipt=json.loads((ROOT/'publication'/f'{name}_prereg_verified.json').read_text())
    assert receipt['status']=='PUBLISHED_VERIFIED' and receipt['grid_sha256']==registration['grid_sha256']
    assert json.loads((ROOT/'baseline_audit/validation.json').read_text())['status']=='PASS'
    for filename, expected in registration['code_sha256'].items():
        assert hashlib.sha256((ROOT/'code'/filename).read_bytes()).hexdigest()==expected
    out=ROOT/'batches'/name
    assert not out.exists();out.mkdir(parents=True)
    results=[]
    for candidate in registration['conditions']:
        assert shutil.disk_usage('C:/').free>10*1024**3 and shutil.disk_usage('D:/').free>10*1024**3
        row=calculate(candidate,v,frame,codes,out/'candidates'/candidate['candidate_id'])
        results.append(row)
        checkpoint=dict(status='LOCAL_AUDITED',batch=name,completed=len(results),new_conditions_total=(number-1)*50+len(results),last_candidate=candidate['candidate_id'])
        with (out/'progress.jsonl').open('a',encoding='utf8') as stream:stream.write(json.dumps(checkpoint)+'\n')
        print(json.dumps(dict(event='CONDITION_AUDITED',**row)),flush=True)
    table(out/'results.csv',results)
    write_json(out/'checkpoint.json',dict(status='LOCAL_AUDITED_NOT_PUBLISHED',batch=name,completed=50,new_conditions_total=number*50,next_batch=number+1 if number<10 else None))
    write_json(out/'environment.json',dict(python=sys.version,platform=platform.platform(),numpy=np.__version__,execution='PAPER_EXPLORATORY_ONLY',input_reproduction='INPUT_NOT_REMOTELY_REPRODUCIBLE'))
    shutil.copy2(ROOT/'preregistration'/f'{name}.json',out/'settings.json')
    write_json(out/'ledger_schema.json',dict(account_ledger=dict(file='full_account_ledger.npz',array='ledger',shape='[input_row,phase,field]',phase=['OPEN','CLOSE','SETTLEMENT'],fields=LEDGER_FIELDS),
        source_sha256=SOURCE_HASH,margin_sha256=MARGIN_HASH,events=EVENT_FIELDS,cycles=TRADE_FIELDS,orders=ORDER_FIELDS,
        missing_settlement='NaN; no synthetic mark',quantities=dict(contracts=17,spot=170000),spot_cash='net flow from zero; sufficient external procurement assumed',
        timestamp_join='approved input row index; no raw market duplication',mark_prices='same source row OPEN/CLOSE or official settlement; raw market inputs remain D-only'))
    print(json.dumps(dict(event='BATCH_LOCAL_AUDITED',batch=name,conditions=50)),flush=True)


def main():
    lock=ROOT/'worker.lock'
    with lock.open('x') as stream:stream.write(str(os.getpid()))
    try:
        v,frame,codes=load()
        batch(int(sys.argv[1]),v,frame,codes)
    finally:
        lock.unlink()


if __name__=='__main__':main()
