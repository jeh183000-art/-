# /// script
# requires-python = "==3.12.0"
# dependencies = ["numpy==2.2.6"]
# ///
# Run: python -B code/bootstrap.py build_all.py
from __future__ import annotations
import hashlib,json
from runner import ROOT,SOURCE_HASH,MARGIN_HASH,canonical,table,write_json
from registry import BASE,signature,inventory
from hypotheses import pools

def main() -> None:
    used=inventory();old_count=len(used);all_conditions=[];reused=[]
    for category in range(1,6):
        group=[]
        for label,rule in pools(category):
            digest=signature(rule)
            if digest in used:
                reused.append(dict(category=category,signature=digest,rule=json.dumps(rule,sort_keys=True),status='REUSE_RULE_NO_NEW_SIMULATION'))
                continue
            used.add(digest)
            number=(category-1)*2+len(group)//50+1
            candidate=dict(candidate_id=f'BP-{number:02d}-{len(group)%50+1:03d}',
                group=label,parent_strategy='BF-09-027',rule=rule,rule_sha256=hashlib.sha256(canonical(rule)).hexdigest(),
                semantic_signature=digest,category=category)
            group.append(candidate)
            if len(group)==100:break
        assert len(group)==100,('POOL_CAPACITY',category,len(group))
        all_conditions.extend(group)
    assert len(all_conditions)==500 and len({c['semantic_signature'] for c in all_conditions})==500
    code={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((ROOT/'code').glob('*.py'))}
    (ROOT/'preregistration').mkdir(exist_ok=True)
    for n in range(1,11):
        conditions=all_conditions[(n-1)*50:n*50]
        record=dict(batch=f'batch_{n:04d}',conditions=conditions,grid_sha256=hashlib.sha256(canonical(conditions)).hexdigest(),
            code_sha256=code,source_sha256=SOURCE_HASH,margin_sha256=MARGIN_HASH,
            baseline_commit='c63352755d43b067b2124e748297efe6cbf6ecbf',previous_final_commit='8a33d1d495ddcb8b3ce0c3b13e2bf31abfd95c43',
            parent_B=BASE,prior_conditions_excluded=old_count,groups={g:sum(c['group']==g for c in conditions) for g in sorted({c['group'] for c in conditions})},
            A_C_D_search_enabled=False,final_oos_access=False,old_conditions_recomputed=False,maximum_new_conditions=500,
            frozen=dict(contracts=17,spot_quantity=170000,futures_initial_cash=30000000,additional_entries=False,simultaneous_opposite=False,
                external_deposits=False,auto_transfers=False,slippage_bp=2,next_contiguous_observed_minute_open=True),
            tolerances=dict(score_new_record_pp=1e-8,mdd_and_money_krw=.01,trigger_attribution_return_pp=1e-10),
            causal_features=dict(current_bar_excluded=True,window='previous N observed minutes',reset='contract roll or >30 calendar-minute gap',
                no_entry_until_full_window=True,volatility_scale='entry clip(std/.25,.5,2.5); recovery clip(std/.25,.5,2)',
                signal_entry_lines='min(-.05,long_entry*entry_scale+weight*lagged_center), max(.05,short_entry*entry_scale+weight*lagged_center)',
                targets_frozen_at_actual_signal=True,reentry='new crossing only; signals during cooldown discarded, never queued',
                confirmation='flat only; progress from adverse trough, minimum observed bars, expiry in calendar minutes'),
            score='sum unrounded completed cycle net/abs(initial spot entry notional)*100; residual separate',
            exploratory_followup=True,raw_input_status='INPUT_NOT_REMOTELY_REPRODUCIBLE')
        write_json(ROOT/'preregistration'/f'batch_{n:04d}.json',record)
    table(ROOT/'reuse_rules.csv',reused)
    write_json(ROOT/'all_500_preregistration.json',dict(status='PREREGISTERED_NOT_EXECUTED',conditions=all_conditions,
        code_sha256=code,new_count=500,categories=5,each_category=100,old_unique_rules=old_count,
        baseline_B_profit_target_pct=.7,all_sequences_fixed_before_control_and_new_runs=True))
    print(json.dumps(dict(registered=500,old_unique_rules=old_count,reused_proposals=len(reused))),flush=True)

if __name__=='__main__':main()
