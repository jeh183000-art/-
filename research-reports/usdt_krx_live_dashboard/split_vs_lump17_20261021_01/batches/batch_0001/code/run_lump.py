# /// script
# requires-python = "==3.12.0"
# dependencies = ["numpy==2.2.6", "numba==0.61.2", "pandas==3.0.1"]
# ///
from __future__ import annotations
import hashlib
import json
import os
import sys
from pathlib import Path
from accounts import Limits, Q, ExecutionPrice, costs
from simulation import Experiment, simulate

ROOT=Path(__file__).resolve().parents[1]
PROJECT=ROOT.parents[1]
HELPERS=PROJECT/'studies/capital_limit_comparison_20261021_01/code'
sys.path.append(str(HELPERS))
from run_compare import load, table, regression

def main() -> None:
    settings=json.loads((ROOT/'settings.json').read_text())
    assert settings['preregistration_commit']=='1322cbf8e6db0ee97d22f558a694b44df5373bb5'
    assert settings['B']['entry_contracts']==17 and settings['B']['entry_usdt']==170000
    assert settings['spot_initial_capital'] is None and settings['spot_cash_limit'] is None
    assert hashlib.sha256((ROOT/'PREREG_COMPARE_KO.md').read_bytes()).hexdigest()==settings['preregistration_sha256']
    assert hashlib.sha256((HELPERS/'run_compare.py').read_bytes()).hexdigest()==settings['shared_helper_sha256']
    for name,h in settings['source_sha256'].items():
        assert hashlib.sha256((PROJECT/'shared/approved_20261016_01'/name).read_bytes()).hexdigest()==h
    for name,h in settings['code_sha256'].items():
        assert hashlib.sha256((ROOT/'code'/name).read_bytes()).hexdigest()==h
    with (ROOT/'worker.lock').open('x') as lock:lock.write(str(os.getpid()))
    try:
        v,frame,codes=load()
        stamps=frame['timestamp_kst'].astype(str).tolist()
        business=frame['business_date'].astype(str).tolist()
        cases=[Experiment('CONTROL_U','U-007206',Limits(0.,30000000.,17,False,True),1),
               Experiment('CONTROL_S1','S1-050',Limits(0.,30000000.,1,False,True),1),
               Experiment('A_SPLIT17','U-007206',Limits(0.,30000000.,17,True,True),1),
               Experiment('B_LUMP17','S1-050',Limits(0.,30000000.,17,True,True),17)]
        results=[];controls=[]
        for case in cases:
            out=ROOT/'runs'/case.name
            assert not out.exists();out.mkdir(parents=True)
            outcome=simulate(v,case);book=outcome.account
            cycles=[]
            for cid in sorted({f['cycle_id'] for f in book.fills}):
                fills=[f for f in book.fills if f['cycle_id']==cid]
                if any(l.cycle==cid for l in book.lots):continue
                notional=sum(abs(f['entry_spot']*Q) for f in fills);net=sum(f['net'] for f in fills)
                first=min(f['entry_row'] for f in fills);last=max(f['exit_row'] for f in fills)
                cycles.append(dict(cycle_id=cid,sets=len(fills),direction=fills[0]['direction'],notional=notional,
                    net=net,return_pct=net/notional*100,entry_row=first,exit_row=last,entry_kst=stamps[first],
                    exit_kst=stamps[last],hold_minutes=int(v[0][last]-v[0][first])))
            if case.name.startswith('CONTROL'):
                controls.append(regression(case.strategy,book,cycles))
            if case.name=='B_LUMP17':
                assert all(o['requested_contracts']==17 and o['requested_usdt']==170000 for o in outcome.orders)
                assert all(o['filled_contracts'] in (0,17) for o in outcome.orders)
                for order in outcome.orders:
                    entries=[e for e in book.events if e['kind']=='ENTRY' and e['order_id']==order['order_id']]
                    assert len(entries)==order['filled_contracts']
                    assert sum(abs(e['spot_quantity_change']) for e in entries)==order['filled_contracts']*10000
                assert all(c['sets']==17 for c in cycles)
            residual=[]
            p=ExecutionPrice(len(v[0])-1,'CLOSE',float(v[6][-1]),float(v[8][-1]),float(v[16][-1]),float(v[17][-1]))
            for l in book.lots:
                gross=l.direction*(p.spot-l.entry_s)*Q+l.future_gross+l.direction*(l.basis-p.future)*Q
                residual.append(dict(set_id=l.set_id,cycle_id=l.cycle,direction=l.direction,entry_row=l.entry_i,
                    notional=l.entry_s*Q,gross=gross,fees=l.fees,slippage=l.slip,estimated_close_cost=sum(costs(p)),
                    net_after_close=gross-l.fees-l.slip-sum(costs(p))))
            minimum_initial=30000000.;minimum_cash=30000000.;need_spot=need_long=0.;avg_qty=avg_spot=count=0.
            prior_below=False;breach_episodes=0
            for m in outcome.marks:
                i=m['row'];m['timestamp_kst']=stamps[i];m['business_date']=business[i]
                minimum_initial=min(minimum_initial,m['future_equity']-m['initial_required'])
                minimum_cash=min(minimum_cash,m['future_cash'])
                need_spot=max(need_spot,-m['spot_available'])
                if m['spot_market_value']>=0:need_long=max(need_long,-m['spot_cash'])
                below=m['maintenance_headroom'] < -1e-7
                breach_episodes+=int(below and not prior_below);prior_below=below
                if m['phase']=='CLOSE':avg_qty+=m['sets'];avg_spot+=abs(m['spot_market_value']);count+=1
            for e in book.events:
                i=e['row'];e['timestamp_kst']=stamps[i]
                e['contract_code']=codes[int(v[11][i])-1] if e['kind']=='ROLL_CLOSE' else codes[int(v[3][i])-1]
            for o in outcome.orders:o['timestamp_kst']=stamps[o['row']]
            for d in outcome.deficits:d['timestamp_kst']=stamps[d['row']]
            row=dict(case=case.name,strategy=case.strategy if case.entry_bundle==1 else 'S1-050-LUMP17',
                requested_entry_contracts=case.entry_bundle,spot_initial_capital=None,spot_limit=None,future_initial_cash=30000000.,
                completed_cycles=len(cycles),score_pct=sum(c['return_pct'] for c in cycles),net_realized=book.realized,
                win_rate_pct=100*sum(c['net']>0 for c in cycles)/len(cycles) if cycles else None,
                mdd=book.mdd,max_open_evaluation_loss=book.max_loss,max_contracts=book.max_sets,
                average_observed_contracts=avg_qty/count,average_observed_spot_notional=avg_spot/count,
                required_spot_financing_on_observed_path=need_spot,
                required_long_spot_financing_on_observed_path=need_long,
                max_long_order_spot_outlay=max((o['requested_usdt']*o['spot_price']*1.0007 for o in outcome.orders if o['filled_contracts'] and o['direction']==1),default=0.),
                max_short_notional=max((o['requested_usdt']*o['spot_price'] for o in outcome.orders if o['filled_contracts'] and o['direction']==-1),default=0.),
                max_single_order_spot_outlay=max((o['requested_usdt']*o['spot_price']*1.0007 for o in outcome.orders if o['filled_contracts']),default=0.),
                minimum_initial_margin_headroom=minimum_initial,minimum_maintenance_headroom=book.minimum_headroom,
                minimum_futures_cash=minimum_cash,required_initial_future_cash_on_observed_path=30000000.-minimum_initial,
                rejected_orders=sum(o['filled_contracts']==0 for o in outcome.orders),
                rejected_contracts=sum(o['requested_contracts'] for o in outcome.orders if o['filled_contracts']==0),
                maintenance_deficit_marks=book.breach_marks,maintenance_deficit_episodes=breach_episodes,
                feasibility='COUNTERFACTUAL_AFTER_DEFICIT' if outcome.deficits else 'NO_OBSERVED_FUNDING_DEFICIT',
                residual_sets=len(residual),residual_net_after_close=sum(r['net_after_close'] for r in residual),
                longest_hold_minutes=max([c['hold_minutes'] for c in cycles]+[0]),
                fees=sum(e['spot_fee']+e['future_fee'] for e in book.events),slippage=sum(e['spot_slippage']+e['future_slippage'] for e in book.events),
                spot_cash_flow=book.spot_cash,future_final_cash=book.future_cash,borrow_status='UNVERIFIED_THEORETICAL_ONLY' if case.strategy=='S1-050' else 'NOT_APPLICABLE')
            results.append(row)
            contributions=[]
            for direction in (1,-1):
                selected=[c for c in cycles if c['direction']==direction]
                contributions.append(dict(direction=direction,cycles=len(selected),net=sum(c['net'] for c in selected),score_pct=sum(c['return_pct'] for c in selected)))
            for name,rows in [('cycles.csv',cycles),('fills.csv',book.fills),('events.csv',book.events),('orders.csv',outcome.orders),
                ('accounts.csv.gz',outcome.marks),('residuals.csv',residual),('margin_deficits.csv',outcome.deficits),('direction_contribution.csv',contributions)]:
                table(out/name,rows)
            (out/'result.json').write_text(json.dumps(row,indent=2))
            (ROOT/'checkpoint.json').write_text(json.dumps({'last_case':case.name,'completed_cases':len(results),'stop_after':'B_LUMP17'}))
            print(json.dumps(row),flush=True)
        table(ROOT/'results.csv',results)
        (ROOT/'regression.json').write_text(json.dumps(controls,indent=2))
    finally:
        (ROOT/'worker.lock').unlink()

if __name__=='__main__':main()
