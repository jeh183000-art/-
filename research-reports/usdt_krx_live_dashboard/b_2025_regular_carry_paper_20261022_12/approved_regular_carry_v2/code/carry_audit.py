# /// script
# requires-python = ">=3.12"
# dependencies = ["numpy==2.2.6"]
# ///
# How to run: imported by quarterly runner; immutable quote adapter auditor is reused.
import json
from dataclasses import asdict
from datetime import datetime,timedelta
from typing import Mapping
from common import OUT,PRIOR,sha,read_csv,table,save
from model import Quote,Variant,Book,INITIAL_F,frozen_drawdowns
from simulator import SegmentRun
from verify_quote_book import audit_run
from carry_engine import State,advance,residual


def tests()->Mapping:
    dates=[datetime(2025,1,3,15,27)+timedelta(minutes=i) for i in range(4)]+[datetime(2025,1,6,9)+timedelta(minutes=i) for i in range(2)]
    gaps=[0.,-1.1,-1.2,-.4,-.3,-.2]
    quotes=[Quote(t,1000*(1+g/100)+.5,1000*(1+g/100)-.5,1000.1,999.9,g,'SYNTHETIC',i+1,'SAME',1) for i,(t,g) in enumerate(zip(dates,gaps))]
    state=State();fills=[];cycles=[];marks=[];signals=[]
    for q in quotes:
        result=advance(state,q,Variant('TEST',None));fills.extend(result.fills);cycles.extend(result.cycles);marks.append(result.mark);signals.extend(result.signals)
    assert len(cycles)==1 and cycles[0]['normal_closure_bridges']==1
    assert fills[1]['t']=='2025-01-06T09:01:00' and fills[1]['signal_t']=='2025-01-06T09:00:00'
    assert any(r['kind']=='CANCEL_PENDING_AT_CLOSURE' for r in signals)
    assert len(marks)==6 and not any('2025-01-04' in m['t'] for m in marks)
    audit_run(quotes,SegmentRun(Book(state.sc,state.fc,state.realized,state.counter),tuple(fills),tuple(cycles),tuple(marks),None,0),Book())
    partial=State()
    for q in quotes[:4]:advance(partial,q,Variant('TEST',None))
    encoded=json.loads(json.dumps(partial.encode(),default=lambda v:v.isoformat()));resumed=State.restore(encoded);tail=[]
    for q in quotes[4:]:tail.extend(advance(resumed,q,Variant('TEST',None)).fills)
    assert tail==fills[1:]
    assert abs(resumed.realized-state.realized)<1e-8 and resumed.pos is None
    cancel_quotes=[Quote(datetime(2025,1,3,15,29),1000.5,999.5,1000.1,999.9,0.,'SYNTHETIC',1,'SAME',1),Quote(datetime(2025,1,3,15,30),989.5,988.5,1000.1,999.9,-1.1,'SYNTHETIC',2,'SAME',1),Quote(datetime(2025,1,6,9),988.5,987.5,1000.1,999.9,-1.2,'SYNTHETIC',3,'SAME',1)]
    cancel=State();seen=[]
    for q in cancel_quotes:seen.extend(advance(cancel,q,Variant('TEST',None)).fills)
    assert len(seen)==0 and cancel.pos is None
    return dict(status='PASS',weekend_carry=True,no_night_marks=True,no_retroactive_open_fill=True,reevaluated_exit_filled_next_minute=True,pending_entry_canceled=True,checkpoint_position_and_cash_preserved=True,Decimal_audit_pass=True)


def verify_through(quarter:int)->None:
    all_data={name:sum((read_csv(OUT/f'quarter_{q}/{name}.csv') for q in range(1,quarter+1)),[]) for name in ('fills','cycles','marks','residuals')}
    lookup={}
    with (PRIOR/'data_local/segments.jsonl').open(encoding='utf8') as f:
        for line in f:
            for q in json.loads(line)['quotes']:lookup[q['t']]=Quote.parse(q)
    groups={}
    for m in all_data['marks']:
        key=(m['variant'],m['scope'],m['chain'] if m['scope']=='CONDITIONAL_CHAIN' else 'ONE_ACCOUNT')
        groups.setdefault(key,[]).append(m)
    proofs=[]
    for key,rows in groups.items():
        rows.sort(key=lambda r:r['t']);vid,scope,chain=key
        eligible=lambda r:r['variant']==vid and r['scope']==scope and (scope!='CONDITIONAL_CHAIN' or r['chain']==chain)
        fs=[r for r in all_data['fills'] if eligible(r)];cs=[r for r in all_data['cycles'] if eligible(r)]
        # The existing Decimal auditor consumes numeric event fields rather than CSV strings.
        numeric_fills=[]
        numeric_cycles=[]
        numeric_marks=[]
        for r in fs:
            values=dict(r)
            for k in ('cycle','direction','quantity_usdt','contracts','spot_notional','future_notional','spot_gross','future_gross','spot_fee','future_fee','spot_slippage','future_slippage','spot_cash','future_cash'):values[k]=float(r[k])
            numeric_fills.append(values)
        for r in cs:
            values=dict(r)
            for k in ('cycle','net','return_pct'):values[k]=float(r[k])
            numeric_cycles.append(values)
        for r in rows:
            values=dict(r)
            for k in ('combined_pnl','open_net_after_close_cost','future_unrealized','spot_cash','future_cash','contracts','held_direction'):values[k]=float(r[k])
            numeric_marks.append(values)
        qs=[lookup[r['t']] for r in rows]
        proof=audit_run(qs,SegmentRun(Book(),tuple(numeric_fills),tuple(numeric_cycles),tuple(numeric_marks),None,0),Book())
        trace=frozen_drawdowns([float(r['combined_equity']) for r in rows])
        for r,(peak,current,mdd) in zip(rows,trace):
            assert abs(float(r['running_equity_peak'])-peak)<.0001 and abs(float(r['current_drawdown'])-current)<.0001 and abs(float(r['cumulative_mdd'])-mdd)<.0001
        proofs.append(dict(variant=vid,scope=scope,chain=chain,**proof))
    table(OUT/f'quarter_{quarter}/independent_audit.csv',proofs)
    print(json.dumps(dict(quarter=quarter,audited_accounts=len(proofs),all_pass=True)))
