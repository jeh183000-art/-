# /// script
# requires-python = "==3.12.0"
# dependencies = []
# ///
"""Independent raw-price CSV replay including whole-bundle admission and quantities."""
from __future__ import annotations
import csv
import gzip
import json
import math
from collections import defaultdict
from enum import StrEnum
from pathlib import Path
from typing import assert_never

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT.parents[1]/'shared/approved_20261016_01'

class Kind(StrEnum):
    ENTRY='ENTRY'
    EXIT='EXIT'
    SETTLE='SETTLE'
    ROLL_CLOSE='ROLL_CLOSE'
    ROLL_OPEN='ROLL_OPEN'

class Phase(StrEnum):
    OPEN='OPEN'
    CLOSE='CLOSE'
    SETTLEMENT='SETTLEMENT'

def read(path: Path) -> list[dict[str,str]]:
    with path.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))

def near(a: float,b: float) -> None:
    assert abs(a-b)<.002,(a,b)

def main() -> None:
    raw=read(SOURCE/'matched_simulation_bars.csv');schedule=read(SOURCE/'margin_schedule.csv')
    rates=[]
    for r in raw:
        day=r['business_date'];iso=day[:4]+'-'+day[4:6]+'-'+day[6:]
        sr=next(s for s in schedule if s['effective_from']<=iso<=s['effective_to'])
        rates.append((float(sr['customer_initial_margin_pct'])/100,float(sr['maintenance_margin_pct'])/100))
    audits=[];atomic=[]
    for directory in sorted((ROOT/'runs').iterdir()):
        result=json.loads((directory/'result.json').read_text());limited=not directory.name.startswith('CONTROL')
        sc=0.;fc=30000000.;peak=30000000.;mdd=loss=required_spot=0.
        min_initial=min_maint=30000000.;max_qty=0;count_marks=0;exposure=observations=0
        lots={};futures=set();byrow=defaultdict(list);byset=defaultdict(list);byorder=defaultdict(list)
        all_events=read(directory/'events.csv');orders={int(o['order_id']):o for o in read(directory/'orders.csv')}
        for e in all_events:
            byrow[int(e['row'])].append(e);byset[int(e['set_id'])].append(e)
            if e['kind']=='ENTRY':byorder[int(e['order_id'])].append(e)
        lump=directory.name=='B_LUMP17'
        for oid,order in orders.items():
            n=int(order['requested_contracts']);filled=int(order['filled_contracts'])
            assert filled in (0,n)
            assert len(byorder[oid])==filled
            if lump:
                assert n==17 and float(order['requested_usdt'])==170000.
                assert sum(abs(float(e['spot_quantity_change'])) for e in byorder[oid])==filled*10000
                assert len({e['direction'] for e in byorder[oid]})<=1
                atomic.append(dict(order_id=oid,row=int(order['row']),requested_contracts=n,filled_contracts=filled,status='PASS'))
            elif result['strategy']=='U-007206':assert n==1
        with gzip.open(directory/'accounts.csv.gz','rt',encoding='utf8',newline='') as f:
            for mark in csv.DictReader(f):
                i=int(mark['row']);phase=Phase(mark['phase']);r=raw[i];ir,mr=rates[i]
                for e in byrow[i]:
                    kind=Kind(e['kind'])
                    if (phase==Phase.SETTLEMENT)!=(kind==Kind.SETTLE) or phase==Phase.CLOSE:continue
                    sid=int(e['set_id']);d=int(e['direction']);oid=int(e['order_id'])
                    sp=float(e['spot_price']);fp=float(e['future_price'])
                    expected_f=float(r['roll_old_open']) if kind==Kind.ROLL_CLOSE else float(r['official_daily_settlement']) if kind==Kind.SETTLE else float(r['future_open'])
                    near(fp,expected_f);near(sp,float(r['settlement_spot_mark']) if kind==Kind.SETTLE else float(r['spot_open']))
                    assert e['contract_code']==(r['roll_old_kis'] if kind==Kind.ROLL_CLOSE else r['contract_code_kis'])
                    sf=sp*10000*.0005 if kind in (Kind.ENTRY,Kind.EXIT) else 0.
                    ss=sp*10000*.0002 if kind in (Kind.ENTRY,Kind.EXIT) else 0.
                    ff=600+fp*10000*.000003157 if kind!=Kind.SETTLE else 0.
                    fs=fp*10000*.0002 if kind!=Kind.SETTLE else 0.
                    ds=df=sg=fg=dqs=dqf=0.
                    match kind:
                        case Kind.ENTRY:
                            assert sid not in lots and int(e['signal_row'])==i-1 and r['continuous_prev']=='True'
                            first=e is byorder[oid][0]
                            if limited and first:
                                n=int(orders[oid]['requested_contracts'])
                                fu=math.fsum(l['d']*(l['basis']-fp)*10000 for l in lots.values())
                                assert len(lots)+n<=17 and fc-n*(ff+fs)>=-1e-7
                                assert fc+fu-n*(ff+fs)>=(len(lots)+n)*fp*10000*ir-1e-7
                                if lump:assert not lots
                            lots[sid]={'d':d,'s':sp,'basis':fp,'fg':0.,'cost':0.,'order':oid}
                            futures.add(sid);ds=-d*sp*10000-sf-ss;df=-ff-fs;dqs=d*10000;dqf=-d
                        case Kind.EXIT:
                            l=lots[sid];sg=d*(sp-l['s'])*10000;fg=d*(l['basis']-fp)*10000
                            ds=d*sp*10000-sf-ss;df=fg-ff-fs;dqs=-d*10000;dqf=d
                            del lots[sid];futures.remove(sid)
                            assert e['exit_reason']=='TARGET'
                        case Kind.SETTLE | Kind.ROLL_CLOSE:
                            l=lots[sid];fg=d*(l['basis']-fp)*10000;df=fg-ff-fs
                            l['fg']+=fg;l['basis']=fp
                            if kind==Kind.ROLL_CLOSE:futures.remove(sid);dqf=d
                        case Kind.ROLL_OPEN:
                            lots[sid]['basis']=fp;df=-ff-fs;futures.add(sid);dqf=-d
                        case unexpected:assert_never(unexpected)
                    if sid in lots:lots[sid]['cost']+=sf+ff+ss+fs
                    sc+=ds;fc+=df
                    for key,value in [('spot_delta',ds),('future_delta',df),('spot_gross',sg),('future_segment',fg),('spot_fee',sf),('future_fee',ff),('spot_slippage',ss),('future_slippage',fs),('spot_cash_after',sc),('future_cash_after',fc),('spot_quantity_change',dqs),('future_quantity_change',dqf)]:near(float(e[key]),value)
                    assert len(lots)<=17 and len(futures)<=17
                match phase:
                    case Phase.OPEN:sp=float(r['spot_open']);fp=float(r['future_open'])
                    case Phase.CLOSE:sp=float(r['spot_close']);fp=float(r['future_close'])
                    case Phase.SETTLEMENT:sp=float(r['settlement_spot_mark']);fp=float(r['official_daily_settlement'])
                    case unexpected:assert_never(unexpected)
                fu=math.fsum(l['d']*(l['basis']-fp)*10000 for l in lots.values())
                sm=math.fsum(l['d']*sp*10000 for l in lots.values())
                eq=sc+sm+fc+fu;peak=max(peak,eq);mdd=max(mdd,peak-eq)
                loss=max(loss,-math.fsum(l['d']*(sp-l['s'])*10000+l['fg']+l['d']*(l['basis']-fp)*10000-l['cost'] for l in lots.values()))
                initial=len(lots)*fp*10000*ir;maint=len(lots)*fp*10000*mr
                min_initial=min(min_initial,fc+fu-initial);min_maint=min(min_maint,fc+fu-maint)
                free_spot=sc-sum((l['s']+sp)*10000 for l in lots.values() if l['d']<0)
                required_spot=max(required_spot,-free_spot);max_qty=max(max_qty,len(lots))
                for key,value in [('spot_cash',sc),('future_cash',fc),('future_unrealized',fu),('total_equity',eq),('mdd',mdd),('initial_required',initial),('maintenance_required',maint),('maintenance_headroom',fc+fu-maint)]:near(float(mark[key]),value)
                if phase==Phase.CLOSE:exposure+=len(lots);observations+=1
                count_marks+=1
        fills=read(directory/'fills.csv');cycles=read(directory/'cycles.csv')
        for fill in fills:
            events=byset[int(fill['set_id'])]
            net=math.fsum(float(e['spot_gross'])+float(e['future_segment'])-float(e['spot_fee'])-float(e['future_fee'])-float(e['spot_slippage'])-float(e['future_slippage']) for e in events)
            near(net,float(fill['net']))
        returns=[]
        for cycle in cycles:
            chosen=[f for f in fills if f['cycle_id']==cycle['cycle_id']]
            ret=math.fsum(float(x['net']) for x in chosen)/math.fsum(abs(float(x['entry_spot'])*10000) for x in chosen)*100
            assert abs(ret-float(cycle['return_pct']))<1e-10;returns.append(ret)
            if lump:assert len(chosen)==17 and len({e['order_id'] for e in all_events if e['kind']=='ENTRY' and e['cycle_id']==cycle['cycle_id']})==1
        assert abs(math.fsum(returns)-result['score_pct'])<1e-10
        for field,value in [('net_realized',sum(float(f['net']) for f in fills)),('mdd',mdd),('max_open_evaluation_loss',loss),('minimum_initial_margin_headroom',min_initial),('minimum_maintenance_headroom',min_maint),('required_spot_financing_on_observed_path',required_spot),('average_observed_contracts',exposure/observations)]:near(float(result[field]),value)
        assert max_qty==result['max_contracts'] and len(lots)==result['residual_sets']
        audits.append(dict(case=directory.name,status='PASS',account_marks=count_marks,orders=len(orders),closed_sets=len(fills),max_contracts=max_qty,score_pct=math.fsum(returns)))
        print(json.dumps(audits[-1]),flush=True)
    (ROOT/'independent_validation.json').write_text(json.dumps({'status':'PASS','cases':audits,'method':'Separate raw CSV, margin schedule, per-event cash/quantity/cost replay; no engine imports'},indent=2))
    (ROOT/'atomic_quantity_validation.json').write_text(json.dumps({'status':'PASS','expected_bundle_contracts':17,'expected_bundle_usdt':170000,'orders':atomic},indent=2))

if __name__=='__main__':main()
