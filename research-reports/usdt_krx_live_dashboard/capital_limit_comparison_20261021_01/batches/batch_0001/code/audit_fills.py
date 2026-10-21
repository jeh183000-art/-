# /// script
# requires-python = "==3.12.0"
# dependencies = []
# ///
import csv
import json
import math
from collections import defaultdict
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def read(path):
    with path.open(encoding='utf8',newline='') as f:return list(csv.DictReader(f))

def main():
    checks=[]
    for case in sorted((ROOT/'runs').glob('*/*')):
        r=json.loads((case/'result.json').read_text())
        events=read(case/'events.csv');fills=read(case/'fills.csv');cycles=read(case/'cycles.csv')
        byset=defaultdict(list);active={};future_active=set()
        for e in events:
            sid=int(e['set_id']);key=(int(e['cycle_id']),int(e['stage']))
            byset[sid].append(e)
            match e['kind']:
                case 'ENTRY':
                    assert key not in active.values() and sid not in active
                    active[sid]=key;future_active.add(sid)
                case 'EXIT':
                    del active[sid];future_active.remove(sid)
                case 'ROLL_CLOSE':future_active.remove(sid)
                case 'ROLL_OPEN':future_active.add(sid)
                case 'SETTLE':assert sid in future_active
                case unexpected:raise AssertionError(unexpected)
            assert len(active)<=r['cap'] and len(future_active)<=r['cap']
            if r['strategy']!='U-007206':assert len(active)<=1
        assert len(active)==r['residual_sets']
        for fill in fills:
            entries=byset[int(fill['set_id'])]
            fees=math.fsum(float(e['spot_fee'])+float(e['future_fee']) for e in entries)
            slips=math.fsum(float(e['spot_slippage'])+float(e['future_slippage']) for e in entries)
            sg=math.fsum(float(e['spot_gross']) for e in entries)
            fg=math.fsum(float(e['future_segment']) for e in entries)
            for key,value in [('fees',fees),('slippage',slips),('spot_gross',sg),('future_gross',fg),('net',sg+fg-fees-slips)]:
                assert abs(float(fill[key])-value)<.00001,(case,key)
            entry=next(e for e in entries if e['kind']=='ENTRY')
            exit=next(e for e in entries if e['kind']=='EXIT')
            assert int(fill['entry_row'])==int(entry['row']) and int(fill['exit_row'])==int(exit['row'])
            for field,prefix in [('entry_spot','spot_price'),('entry_future','future_price')]:assert float(fill[field])==float(entry[prefix])
            assert float(fill['exit_spot'])==float(exit['spot_price']) and float(fill['exit_future'])==float(exit['future_price'])
        rates=[]
        for cycle in cycles:
            selected=[f for f in fills if f['cycle_id']==cycle['cycle_id']]
            net=math.fsum(float(f['net']) for f in selected)
            notional=math.fsum(abs(float(f['entry_spot'])*10000) for f in selected)
            rate=net/notional*100
            assert abs(float(cycle['return_pct'])-rate)<1e-10
            rates.append(rate)
        assert abs(math.fsum(rates)-r['score_pct'])<1e-10
        checks.append(dict(case=str(case.relative_to(ROOT/'runs')),status='PASS',sets_audited=len(fills),cycle_rates=len(rates),score_tolerance_pct=1e-10))
    (ROOT/'independent_fill_validation.json').write_text(json.dumps({'status':'PASS','cases':checks},indent=2))
    print('PASS',len(checks),'strict per-set and cycle audits')

if __name__=='__main__':main()
