# /// script
# requires-python = "==3.12.0"
# dependencies = ["numpy==2.2.6"]
# ///
# Run with code/bootstrap.py in this frozen research runtime.
from __future__ import annotations

import csv
import gzip
import hashlib
import json
import shutil
import sys
import tarfile
from pathlib import Path

from runner import ROOT, SOURCE_HASH, MARGIN_HASH, table, write_json
from path_reports import write_prereg_report,write_result_report


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def manifest(out):
    rows=[]
    for path in sorted(out.rglob('*')):
        if not path.is_file() or path.name=='manifest.csv':continue
        relative=path.relative_to(out).as_posix()
        role='results_csv'
        if relative.startswith('code/') or path.name=='strategy_code_ref.json':role='strategy_code'
        elif path.name=='settings.json' or path.suffix=='.json':role='settings'
        if path.name=='environment.json':role='environment'
        if 'REPORT' in path.name or path.suffix=='.md':role='statistics_report'
        if 'ledger' in relative or 'fills' in relative or 'cycles' in relative or 'archive' in relative:role='fills'
        if path.name=='costs.csv':role='costs'
        rows.append(dict(path=relative,role=role,bytes=path.stat().st_size,sha256=digest(path)))
    table(out/'manifest.csv',rows,['path','role','bytes','sha256'])


def prereg(number):
    name=f'batch_{number:04d}';out=ROOT/'publish_payloads'/f'{name}_prereg_v1'
    assert not out.exists();out.mkdir(parents=True)
    shutil.copy2(ROOT/'preregistration'/f'{name}.json',out/'settings.json')
    shutil.copy2(ROOT/'publication/code_ref.json',out/'strategy_code_ref.json')
    table(out/'costs.csv',[dict(spot_fee_per_side=.0005,future_fee_per_contract=600,clearing=.000003157,slippage_bp_per_leg_per_side=2,borrow='UNVERIFIED_NOT_INCLUDED',funding='NOT_APPLICABLE',roll='BOTH_LEGS')])
    table(out/'results.csv',[dict(status='PREREGISTERED_NOT_EXECUTED',conditions=50)])
    table(out/'fills.csv',[dict(status='NO_NEW_MARKET_SIMULATION_EXECUTED')])
    write_json(out/'environment.json',dict(python=sys.version,storage='D_ONLY',mode='EXPLORATORY_PAPER',input_status='INPUT_NOT_REMOTELY_REPRODUCIBLE'))
    write_json(out/'provenance.json',dict(source_sha256=SOURCE_HASH,margin_sha256=MARGIN_HASH,baseline_commit='c63352755d43b067b2124e748297efe6cbf6ecbf',B='BF-09-027',A_C_D_modified=False,final_oos_access=False))
    write_prereg_report(name,out)
    manifest(out);print(str(out),flush=True)


def results(number):
    name=f'batch_{number:04d}'; source=ROOT/'batches'/name
    out=ROOT/'publish_payloads'/f'{name}_results_v1'
    assert not out.exists();out.mkdir(parents=True)
    for filename in ('results.csv','checkpoint.json','environment.json','settings.json','ledger_schema.json'):
        shutil.copy2(source/filename,out/filename)
    shutil.copy2(ROOT/'publication/code_ref.json',out/'strategy_code_ref.json')
    rows=[json.loads(p.read_text()) for p in sorted((source/'candidates').glob('*/result.json'))]
    assert len(rows)==50
    allrows=[json.loads(p.read_text()) for p in sorted((ROOT/'batches').glob('batch_*/candidates/*/result.json'))]
    eligible=sorted([r for r in allrows if r['feasible'] and r['cycles']>0],key=lambda r:r['score_pct'],reverse=True)
    qualified=[r for r in eligible if r['goal_qualified']]
    for suffix,selected in [('all',eligible),('all_targets',qualified),('min42',[r for r in eligible if r['cycles']>=42]),('no_residual',[r for r in eligible if r['residual_contracts']==0])]:table(out/f'ranking_{suffix}.csv',selected)
    table(out/'target_shortfalls.csv',[dict(r,failed_targets=';'.join(k for k in ('beats_B','meets_cycle_count','meets_residual_zero','meets_mdd_limit','margin_shortage_free') if not r[k])) for r in allrows if not r['goal_qualified']])
    table(out/'ineligible.csv',[r for r in allrows if not r['feasible']])
    table(out/'zero_completed.csv',[r for r in allrows if r['cycles']==0])
    for filename in ('cycles.csv.gz','fills.csv.gz','orders.csv.gz'):
        with gzip.open(out/filename,'wt',encoding='utf8',newline='') as destination:
            writer=None
            for folder in sorted((source/'candidates').iterdir()):
                with gzip.open(folder/filename,'rt',encoding='utf8',newline='') as stream:
                    reader=csv.DictReader(stream)
                    for row in reader:
                        if writer is None:writer=csv.DictWriter(destination,fieldnames=list(row));writer.writeheader()
                        writer.writerow(row)
            if writer is None:destination.write('status\nNO_ROWS\n')
    table(out/'costs.csv',[{k:r[k] for k in ('candidate_id','fees_krw','slippage_krw','borrow_unverified')} for r in rows])
    table(out/'risks.csv',[{k:r[k] for k in ('candidate_id','mdd_krw','maximum_open_loss_krw','residual_contracts','residual_net_after_exit_cost','minimum_initial_headroom_krw','minimum_maintenance_headroom_krw','insufficient_rolls','maintenance_breach_marks','feasible')} for r in rows])
    table(out/'validation.csv',[dict(candidate_id=r['candidate_id'],status='PASS_INDEPENDENT_REPLAY',maximum_account_difference_krw=r['audit_max_difference_krw'],atomic_order_contracts=17) for r in rows])
    inventory=[]
    for path in sorted((source/'candidates').rglob('*')):
        if path.is_file():inventory.append(dict(path=path.relative_to(source).as_posix(),bytes=path.stat().st_size,sha256=digest(path)))
    table(out/'archive_inventory.csv',inventory)
    archive=source/'full_ledgers.tar'
    with tarfile.open(archive,'x') as tf:
        for path in sorted((source/'candidates').rglob('*')):
            if path.is_file():tf.add(path,arcname=path.relative_to(source).as_posix(),recursive=False)
    parts=[]
    with archive.open('rb') as stream:
        index=1
        while block:=stream.read(16*1024*1024):
            dest=out/f'full_ledgers.tar.part{index:03d}'
            with dest.open('xb') as f:f.write(block)
            parts.append(dict(path=dest.name,bytes=len(block),sha256=digest(dest)));index+=1
    write_json(out/'archive_parts.json',dict(format='uncompressed tar split exact binary concatenation',archive_bytes=archive.stat().st_size,archive_sha256=digest(archive),parts=parts,
        reconstruction='Join sorted full_ledgers.tar.partNNN bytes then verify SHA256 and extract tar. Account NPZ preserves every OPEN/CLOSE/SETTLEMENT mark. export_account_csv.py creates full CSV without recomputing trades.'))
    for row in sorted([r for r in rows if r['feasible'] and r['cycles']],key=lambda r:r['score_pct'],reverse=True)[:3]:
        folder=source/'candidates'/row['candidate_id']
        for filename in ('cycles','fills'):
            with gzip.open(folder/f'{filename}.csv.gz','rb') as inp, (out/f"top_{row['candidate_id']}_{filename}.csv").open('xb') as dest:shutil.copyfileobj(inp,dest)

    rules={r['candidate_id']:r['rule'] for p in sorted((ROOT/'preregistration').glob('batch_*.json')) for r in json.loads(p.read_text())['conditions']}
    current=sorted([r for r in rows if r['feasible'] and r['cycles']],key=lambda r:r['score_pct'],reverse=True)
    current_goal=[r for r in current if r['goal_qualified']]
    selected=current_goal[0] if current_goal else current[0] if current else None
    summary=dict(batch=name,new_conditions_total=number*50,qualified_count=len(qualified),batch_qualified_count=len(current_goal),
        goal_best=qualified[0] if qualified else None,score_best=eligible[0] if eligible else None,
        batch_goal_best=current_goal[0] if current_goal else None,batch_score_best=current[0] if current else None,
        selected=selected,selected_rule=rules[selected['candidate_id']] if selected else None,
        source_sha256=SOURCE_HASH,margin_sha256=MARGIN_HASH,code_reference=json.loads((ROOT/'publication/code_ref.json').read_text()),
        raw_input_status='INPUT_NOT_REMOTELY_REPRODUCIBLE',final_oos_access=False,c_free_gib=shutil.disk_usage('C:/').free/1024**3,d_free_gib=shutil.disk_usage('D:/').free/1024**3)
    write_json(out/'publication_summary.json',summary)
    table(out/'risk_classification.csv',[dict(candidate_id=r['candidate_id'],low_cycle_count=r['low_cycle_count'],long_holding_risk=r['long_holding_risk'],longer_than_baseline=r['longer_than_baseline'],open_loss_hidden_risk=r['open_loss_hidden_risk'],residual_net_after_exit_cost=r['residual_net_after_exit_cost'],forced_terminal_score_pct=r['forced_terminal_score_pct'],margin_shortage_free=r['margin_shortage_free']) for r in allrows])
    write_result_report(number,out,rows,allrows,rules,summary)
    manifest(out);print(str(out),flush=True)


if __name__=='__main__':
    {'prereg':prereg,'results':results}[sys.argv[1]](int(sys.argv[2]))
