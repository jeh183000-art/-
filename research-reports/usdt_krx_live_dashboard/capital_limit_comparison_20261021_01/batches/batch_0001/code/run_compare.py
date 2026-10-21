# /// script
# requires-python = "==3.12.0"
# dependencies = ["numpy==2.2.6", "numba==0.61.2", "pandas==3.0.1"]
# ///
"""Run only the frozen A/B comparison, with unconstrained regression anchors first."""
from __future__ import annotations
import csv
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import numpy as np
from accounts import Limits, Q, costs, ExecutionPrice
from simulation import Experiment, simulate

ROOT=Path(__file__).resolve().parents[1]
PROJECT=ROOT.parents[1]
SOURCE=PROJECT/'shared/approved_20261016_01'
OLD=PROJECT/'studies/unlimited_revalidation_20261017_01'
SINGLE=PROJECT/'studies/single_set_hypotheses_20261020_01'
NAMES='times month_ids month_end contract_ids gap spot_open spot_close future_open future_close roll_flag roll_old_open old_contract_ids continuous_prev settlement_due settlement_price settlement_spot_mark initial_rate maintenance_rate'.split()

def table(path: Path, rows: list[dict], fields: list[str] | None = None) -> None:
    names=fields or sorted({k for row in rows for k in row}) or ['status']
    opener=gzip.open if path.suffix=='.gz' else open
    with opener(path,'xt',encoding='utf-8',newline='') as stream:
        w=csv.DictWriter(stream,fieldnames=names);w.writeheader();w.writerows(rows)

def load():
    expected='62becd7d50e05bdcf47010cdcdfdd8178bbe2ef1d8099a84ab18fae8fea19fbd'
    assert hashlib.sha256((SOURCE/'matched_simulation_bars.csv').read_bytes()).hexdigest()==expected
    spec=importlib.util.spec_from_file_location('approved_comparison_loader',SOURCE/'paper_engine.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    a=module.load_arrays()
    return tuple(a[k] for k in NAMES),a['frame'],a['contract_codes']

def regression(strategy: str, book, cycles: list[dict]) -> dict:
    if strategy=='U-007206':
        expected=(59,13.527810495012686,10821261.437143005,2166554.362856999,1759184.199999998)
        with (OLD/'registered_anchor_accounting_audit/winner_trades.csv').open(encoding='utf8',newline='') as f:
            ref=list(csv.DictReader(f))
        assert len(ref)==len(book.fills)==134
        for a,b in zip(book.fills,ref,strict=True):
            for x,y in [('entry_row','entry_fill_row_index'),('exit_row','exit_fill_row_index'),('net','net_pnl_krw'),('fees','fees_krw'),('slippage','slippage_krw')]:
                assert abs(float(a[x])-float(b[y]))<1e-5,(strategy,x,a[x],b[y])
    else:
        number='050' if strategy=='S1-050' else '037'
        ref=np.load(SINGLE/f'batch_0001/raw/S1-{number}.npz')['trades']
        expected=(45,13.15221660791525,1903331.04513901,715460.3548610001,550208.6) if number=='050' else (23,7.3452526352660525,1066890.739620002,369143.26038,291966.)
        assert len(ref)==len(book.fills)
        for a,b in zip(book.fills,ref,strict=True):
            for key,index in [('entry_row',1),('exit_row',3),('net',13),('fees',11),('slippage',12)]:
                assert abs(float(a[key])-float(b[index]))<1e-5,(strategy,key,a[key],b[index])
    got=(len(cycles),sum(c['return_pct'] for c in cycles),book.realized,
         sum(e['spot_fee']+e['future_fee'] for e in book.events),sum(e['spot_slippage']+e['future_slippage'] for e in book.events))
    np.testing.assert_allclose(got,expected,rtol=1e-10,atol=1e-5)
    return dict(strategy=strategy,status='PASS_ALL_CLOSED_FILLS_AND_COSTS',cycles=got[0],score_pct=got[1],net=got[2])

def main() -> None:
    lock=ROOT/'worker.lock'
    with lock.open('x') as f:f.write(str(os.getpid()))
    try:
        v,frame,codes=load()
        settings=json.loads((ROOT/'settings.json').read_text())
        for name,h in settings['code_sha256'].items():
            assert hashlib.sha256((ROOT/'code'/name).read_bytes()).hexdigest()==h
        results=[];checks=[]
        for scenario in ('REGRESSION','A','B'):
            for strategy in ('U-007206','S1-050','S1-037'):
                out=ROOT/'runs'/scenario/strategy
                assert not out.exists()
                out.mkdir(parents=True)
                cash=250000000. if scenario=='A' else 30000000.
                case=Experiment(scenario,strategy,Limits(cash,30000000.,17 if strategy=='U-007206' else 1,scenario!='REGRESSION'))
                result=simulate(v,case);book=result.account
                cycles=[]
                for cid in sorted({f['cycle_id'] for f in book.fills}):
                    fills=[f for f in book.fills if f['cycle_id']==cid]
                    if any(l.cycle==cid for l in book.lots):continue
                    notional=sum(f['entry_spot']*Q for f in fills)
                    net=sum(f['net'] for f in fills)
                    start=min(f['entry_row'] for f in fills);end=max(f['exit_row'] for f in fills)
                    cycles.append(dict(cycle_id=cid,sets=len(fills),notional=notional,net=net,return_pct=net/notional*100,
                        entry_row=start,exit_row=end,entry_kst=str(frame.iloc[start]['timestamp_kst']),exit_kst=str(frame.iloc[end]['timestamp_kst']),hold_minutes=int(v[0][end]-v[0][start])))
                residual=[]
                last=ExecutionPrice(len(v[0])-1,'CLOSE',float(v[6][-1]),float(v[8][-1]),float(v[16][-1]),float(v[17][-1]))
                for l in book.lots:
                    close_cost=sum(costs(last))
                    gross=l.direction*(last.spot-l.entry_s)*Q+l.future_gross+l.direction*(l.basis-last.future)*Q
                    residual.append(dict(set_id=l.set_id,cycle_id=l.cycle,entry_row=l.entry_i,direction=l.direction,
                        notional=l.entry_s*Q,gross=gross,fees_paid=l.fees,slippage_paid=l.slip,estimated_close_cost=close_cost,net_after_close=gross-l.fees-l.slip-close_cost))
                if scenario=='REGRESSION':
                    checks.append(regression(strategy,book,cycles))
                    assert not residual
                for e in book.events:
                    e['timestamp_kst']=str(frame.iloc[e['row']]['timestamp_kst'])
                    e['contract_code']=codes[int(v[11][e['row']])-1] if e['kind']=='ROLL_CLOSE' or (e['kind']=='EXIT' and e.get('exit_reason')=='ROLL_MARGIN_FORCED') else codes[int(v[3][e['row']])-1]
                for r in result.marks:
                    r['timestamp_kst']=str(frame.iloc[r['row']]['timestamp_kst'])
                    r['business_date']=str(frame.iloc[r['row']]['business_date'])
                row=dict(scenario=scenario,strategy=strategy,initial_spot=cash,initial_future=30000000.,cap=case.limits.cap,
                    cycles=len(cycles),score_pct=sum(c['return_pct'] for c in cycles),net_realized=book.realized,
                    win_rate_pct=100*sum(c['net']>0 for c in cycles)/len(cycles) if cycles else None,
                    max_sets=book.max_sets,mdd=book.mdd,max_open_loss=book.max_loss,max_initial_margin=book.max_initial,
                    minimum_maintenance_headroom=book.minimum_headroom,breach_marks=book.breach_marks,
                    rejected=len(result.rejections),residual_sets=len(residual),residual_net=sum(r['net_after_close'] for r in residual),
                    longest_hold_minutes=max([c['hold_minutes'] for c in cycles]+[0]),
                    spot_cash_end=book.spot_cash,future_cash_end=book.future_cash,
                    fees=sum(e['spot_fee']+e['future_fee'] for e in book.events),slippage=sum(e['spot_slippage']+e['future_slippage'] for e in book.events),
                    theoretical_borrow=strategy=='S1-050',forced_exits=sum(f['reason']!='TARGET' for f in book.fills))
                results.append(row)
                table(out/'cycles.csv',cycles)
                table(out/'fills.csv',book.fills)
                table(out/'events.csv',book.events)
                table(out/'accounts.csv.gz',result.marks)
                table(out/'rejections.csv',result.rejections)
                table(out/'residuals.csv',residual)
                table(out/'stress.csv',result.stress)
                (out/'result.json').write_text(json.dumps(row,indent=2))
                print(json.dumps(row),flush=True)
                (ROOT/'checkpoint.json').write_text(json.dumps({'last_completed':f'{scenario}/{strategy}','completed_cases':len(results),'next':'STOP_AFTER_A_B' if len(results)==9 else 'NEXT_REGISTERED_CASE'}))
        table(ROOT/'results.csv',results)
        (ROOT/'regression.json').write_text(json.dumps(checks,indent=2))
    finally:
        lock.unlink()

if __name__=='__main__':main()
