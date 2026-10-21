# /// script
# requires-python = "==3.12.0"
# dependencies = []
# ///
"""Independent CSV replay: imports no simulation or account implementation."""
from __future__ import annotations
import csv
import gzip
import json
import math
from collections import defaultdict
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT.parents[1]/'shared/approved_20261016_01'

def read(path: Path) -> list[dict]:
    with path.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))

def near(a: float,b: float) -> None:
    assert abs(a-b)<.002,(a,b)

def main() -> None:
    raw=read(SOURCE/'matched_simulation_bars.csv')
    schedule=read(SOURCE/'margin_schedule.csv')
    rates=[]
    for r in raw:
        date=r['business_date'];iso=date[:4]+'-'+date[4:6]+'-'+date[6:]
        s=next(x for x in schedule if x['effective_from']<=iso<=x['effective_to'])
        rates.append((float(s['customer_initial_margin_pct'])/100,float(s['maintenance_margin_pct'])/100))
    checks=[]
    for directory in sorted((ROOT/'runs').glob('*/*')):
        result=json.loads((directory/'result.json').read_text())
        sc=result['initial_spot'];fc=result['initial_future'];peak=sc+fc;mdd=0.
        lots={};event_by_row=defaultdict(list);cycle_entry=defaultdict(float);cycle_net=defaultdict(float)
        for event in read(directory/'events.csv'):event_by_row[int(event['row'])].append(event)
        rejection_by_row=defaultdict(list)
        for r in read(directory/'rejections.csv'):rejection_by_row[int(r['row'])].append(r)
        audited_entries=audited_marks=audited_rejections=0
        with gzip.open(directory/'accounts.csv.gz','rt',encoding='utf-8',newline='') as stream:
            for mark in csv.DictReader(stream):
                i=int(mark['row']);phase=mark['phase'];r=raw[i]
                initial,maintenance=rates[i]
                for e in event_by_row[i]:
                    if (phase=='SETTLEMENT') != (e['kind']=='SETTLE'):continue
                    if phase=='CLOSE':continue
                    sid=int(e['set_id']);cid=int(e['cycle_id']);d=int(e['direction']);kind=e['kind']
                    sp=float(e['spot_price']);fp=float(e['future_price']);notional=sp*10000
                    expected_f=float(r['roll_old_open']) if kind=='ROLL_CLOSE' or e.get('exit_reason')=='ROLL_MARGIN_FORCED' else float(r['official_daily_settlement']) if kind=='SETTLE' else float(r['future_open'])
                    near(fp,expected_f)
                    near(sp,float(r['settlement_spot_mark']) if kind=='SETTLE' else float(r['spot_open']))
                    sf=notional*.0005 if kind in ('ENTRY','EXIT') else 0.
                    ss=notional*.0002 if kind in ('ENTRY','EXIT') else 0.
                    ff=600+fp*10000*.000003157 if kind!='SETTLE' else 0.
                    fs=fp*10000*.0002 if kind!='SETTLE' else 0.
                    for key,value in [('spot_fee',sf),('future_fee',ff),('spot_slippage',ss),('future_slippage',fs)]:near(float(e[key]),value)
                    ds=df=sg=fg=0.
                    match kind:
                        case 'ENTRY':
                            assert sid not in lots
                            assert int(e['signal_row'])==i-1 and r['continuous_prev']=='True'
                            if result['scenario']!='REGRESSION':
                                assert len(lots)<result['cap']
                                fu=math.fsum(l['d']*(l['basis']-fp)*10000 for l in lots.values())
                                short=sum((l['entry_s']+sp)*10000 for l in lots.values() if l['d']<0)
                                assert sc-short>=notional+sf+ss-1e-7
                                assert fc-ff-fs>=-1e-7
                                assert fc+fu-ff-fs>=(len(lots)+1)*fp*10000*initial-1e-7
                            lots[sid]={'d':d,'entry_s':sp,'basis':fp,'cycle':cid}
                            ds=-d*notional-sf-ss;df=-ff-fs
                            cycle_entry[cid]+=notional;audited_entries+=1
                        case 'EXIT':
                            l=lots.pop(sid);sg=d*(sp-l['entry_s'])*10000;fg=d*(l['basis']-fp)*10000
                            ds=d*notional-sf-ss;df=fg-ff-fs
                        case 'SETTLE' | 'ROLL_CLOSE':
                            l=lots[sid];fg=d*(l['basis']-fp)*10000;df=fg-ff-fs;l['basis']=fp
                        case 'ROLL_OPEN':
                            lots[sid]['basis']=fp;df=-ff-fs
                        case unexpected:raise AssertionError(unexpected)
                    sc+=ds;fc+=df;cycle_net[cid]+=sg+fg-sf-ff-ss-fs
                    for key,value in [('spot_delta',ds),('future_delta',df),('spot_gross',sg),('future_segment',fg),('spot_cash_after',sc),('future_cash_after',fc)]:near(float(e[key]),value)
                match phase:
                    case 'OPEN':sp=float(r['spot_open']);fp=float(r['future_open'])
                    case 'CLOSE':sp=float(r['spot_close']);fp=float(r['future_close'])
                    case 'SETTLEMENT':sp=float(r['settlement_spot_mark']);fp=float(r['official_daily_settlement'])
                    case unexpected:raise AssertionError(unexpected)
                fu=math.fsum(l['d']*(l['basis']-fp)*10000 for l in lots.values())
                market=math.fsum(l['d']*sp*10000 for l in lots.values())
                equity=sc+market+fc+fu;peak=max(peak,equity);mdd=max(mdd,peak-equity)
                short=sum((l['entry_s']+sp)*10000 for l in lots.values() if l['d']<0)
                for key,value in [('sets',len(lots)),('spot_cash',sc),('future_cash',fc),('future_unrealized',fu),('future_equity',fc+fu),('initial_required',len(lots)*fp*10000*initial),('maintenance_required',len(lots)*fp*10000*maintenance),('total_equity',equity),('mdd',mdd),('spot_available',sc-short)]:near(float(mark[key]),value)
                if phase=='OPEN':
                    for rejection in rejection_by_row[i]:
                        reason=rejection['reason']
                        valid={'SPOT_CASH':sc-short<sp*10000*1.0007-1e-7,'POSITION_CAP':len(lots)>=result['cap'],
                            'FUTURE_OPERATING_CASH':fc-(600+fp*10000*.000203157)<-1e-7,
                            'INITIAL_MARGIN':fc+fu-(600+fp*10000*.000203157)<(len(lots)+1)*fp*10000*initial-1e-7,
                            'MAINTENANCE':fc+fu<len(lots)*fp*10000*maintenance-1e-7}
                        assert valid[reason],reason
                        audited_rejections+=1
                audited_marks+=1
        completed=read(directory/'cycles.csv')
        score=0.
        for c in completed:
            cid=int(c['cycle_id']);near(float(c['net']),cycle_net[cid]);near(float(c['notional']),cycle_entry[cid])
            ret=cycle_net[cid]/cycle_entry[cid]*100;near(float(c['return_pct']),ret);score+=ret
        near(score,result['score_pct']);near(mdd,result['mdd']);near(sc,result['spot_cash_end']);near(fc,result['future_cash_end'])
        near(sum(float(c['net']) for c in completed),result['net_realized'])
        checks.append(dict(case=str(directory.relative_to(ROOT/'runs')),status='PASS',entries=audited_entries,
            account_marks=audited_marks,rejections=audited_rejections,score_pct=score,independent_margin_schedule=True,source_price_checked=True))
        print(json.dumps(checks[-1]),flush=True)
    (ROOT/'independent_validation.json').write_text(json.dumps({'status':'PASS','implementation':'Separate CSV replay; no simulation imports','cases':checks},indent=2))

if __name__=='__main__':main()
