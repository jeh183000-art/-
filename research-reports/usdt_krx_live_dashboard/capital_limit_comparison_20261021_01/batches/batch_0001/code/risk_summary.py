# /// script
# requires-python = "==3.12.0"
# dependencies = []
# ///
import csv
import gzip
import json
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def write(name, rows):
    with (ROOT/name).open('x',encoding='utf8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

def main():
    monthly=[];risks=[];rejections=[];stress=[]
    for directory in sorted((ROOT/'runs').glob('[AB]/*')):
        result=json.loads((directory/'result.json').read_text())
        scenario=directory.parent.name;strategy=directory.name
        month='';previous=result['initial_spot']+result['initial_future'];peak=previous
        need=used=0.;mincash=result['initial_future'];states={};row_month={}
        with gzip.open(directory/'accounts.csv.gz','rt',encoding='utf8',newline='') as f:
            for r in csv.DictReader(f):
                current=r['business_date'][:6];eq=float(r['total_equity'])
                row_month[int(r['row'])]=current
                if current!=month:
                    month=current;peak=previous
                    states[month]=dict(scenario=scenario,strategy=strategy,month=month,start_equity=previous,end_equity=eq,marked_change=0.,mdd=0.,completed_cycles=0,completed_score_pct=0.)
                peak=max(peak,eq)
                state=states[month];state['end_equity']=eq
                state['marked_change']=eq-state['start_equity'];state['mdd']=max(state['mdd'],peak-eq)
                need=max(need,float(r['initial_required'])-float(r['future_equity'])+result['initial_future'])
                used=max(used,result['initial_spot']-float(r['spot_available']))
                mincash=min(mincash,float(r['future_cash']))
                previous=eq
        with (directory/'cycles.csv').open(encoding='utf8',newline='') as f:
            for c in csv.DictReader(f):
                stamp=row_month[int(c['exit_row'])]
                states[stamp]['completed_cycles']+=1;states[stamp]['completed_score_pct']+=float(c['return_pct'])
        monthly.extend(states.values())
        risks.append(dict(scenario=scenario,strategy=strategy,max_required_initial_futures_cash_on_observed_path=need,
            max_spot_cash_and_collateral_used=used,minimum_futures_cash=mincash,mdd=result['mdd'],max_open_loss=result['max_open_loss'],max_sets=result['max_sets'],minimum_maintenance_headroom=result['minimum_maintenance_headroom']))
        with (directory/'rejections.csv').open(encoding='utf8',newline='') as f:counts=Counter(r['reason'] for r in csv.DictReader(f))
        for reason,count in counts.items():rejections.append(dict(scenario=scenario,strategy=strategy,reason=reason,count=count))
        with (directory/'stress.csv').open(encoding='utf8',newline='') as f:records=list(csv.DictReader(f))
        for shock in (5.,7.,10.):
            chosen=min((r for r in records if abs(float(r['shock_pct'])-shock)<1e-9),key=lambda r:float(r['headroom_after_shock']))
            stress.append(dict(scenario=scenario,strategy=strategy,**chosen))
    write('monthly_risk_and_returns.csv',monthly)
    write('risks.csv',risks)
    write('rejection_summary.csv',rejections)
    write('stress_summary.csv',stress)
    print(json.dumps({'risk_cases':len(risks),'months':len(monthly),'rejection_groups':len(rejections)}))

if __name__=='__main__':main()
