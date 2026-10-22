# /// script
# requires-python = "==3.12.0"
# dependencies = []
# ///
# Run: python -B code/bootstrap.py ../operations/strict_exit_triggers.py BATCH_NUMBER
from __future__ import annotations
import csv,json,sys
from collections import Counter
from runner import ROOT,table,write_json
number=int(sys.argv[1]);name=f'batch_{number:04d}'
out=ROOT/'publish_payloads'/f'{name}_results_v1'
counts=[];details=[]
labels=('gap_recovery','net_profit','gap_stop','net_stop','time_limit','stall_limit','state_trail')
for path in sorted((ROOT/'batches'/name/'candidates').glob('*/exit_attribution.csv')):
    with path.open(encoding='utf8',newline='') as stream:
        source=list(csv.DictReader(stream))
    counter=Counter()
    for row in source:
        bits=int(row['reason_bits'])
        flags=(bool(bits&1),row['profit']=='True',bool(bits&2),bool(bits&4) and row['profit']!='True',bool(bits&8),bool(bits&16),bool(bits&32))
        causes=[label for label,active in zip(labels,flags) if active]
        assert causes
        if len(causes)==1:counter[causes[0]+'_alone']+=1
        for cause in causes:counter[cause+'_any']+=1
        if len(causes)>1:counter['multiple_causes']+=1
        details.append(dict(candidate_id=path.parent.name,cycle_id=row['cycle_id'],signal_row=row['signal_row'],causes=';'.join(causes),number_of_simultaneous_causes=len(causes)))
    assert sum(counter[k+'_alone'] for k in labels)+counter['multiple_causes']==len(source)
    counts.append(dict(candidate_id=path.parent.name,cycles=len(source),**{k+suffix:counter[k+suffix] for k in labels for suffix in ('_alone','_any')},multiple_causes=counter['multiple_causes']))
table(out/'strict_exit_trigger_counts.csv',counts)
table(out/'strict_exit_trigger_ledger.csv',details)
write_json(out/'strict_exit_trigger_validation.json',dict(status='PASS',conditions=50,completed_cycles=len(details),all_cause_partition=True,simulation_repeated=False))
text=(out/'REPORT_KO.md').read_text(encoding='utf8')
note='\n발동횟수 정의: 기존 exit_gap_only/exit_profit_only는 두 주요 청산조건 사이의 배타성입니다. 시간·손절·정체·상태추적까지 포함한 진정한 단독/동시 발동은 strict_exit_trigger_counts.csv 및 strict_exit_trigger_ledger.csv에서 전 조건으로 분리했습니다.\n'
(out/'REPORT_KO.md').write_text(text+note,encoding='utf8')
print(json.dumps(dict(status='PASS_STRICT_EXIT_CAUSES',conditions=50,cycles=len(details))),flush=True)
