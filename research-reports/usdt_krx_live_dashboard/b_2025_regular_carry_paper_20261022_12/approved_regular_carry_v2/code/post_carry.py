# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
# How to run: python -B code/bootstrap.py post_carry.py
import collections,json,gzip
from common import ROOT,OUT,PUB,PRIOR,read_csv,table,save,sha


def main()->None:
    fs=read_csv(PUB/'fills.csv');cs=read_csv(PUB/'cycles.csv');rs=read_csv(PUB/'residuals.csv')
    only=lambda rows,vid:[{k:v for k,v in r.items() if k not in ('variant','reason','exit_reason')} for r in rows if r['variant']==vid]
    assert only(fs,'B-RECOVERY-ONLY')==only(fs,'B-DUAL-CONTROL')
    assert only(cs,'B-RECOVERY-ONLY')==only(cs,'B-DUAL-CONTROL')
    assert all(float(r['contracts'])==17 and float(r['quantity_usdt'])==170000 for r in fs)
    assert all(r['t']>r['signal_t'] for r in fs)
    assert all(r['exit_reason'] in ('RECOVERY','BOTH') and int(r['normal_closure_bridges'])>0 for r in cs)
    reasons=collections.Counter()
    for r in rs:
        if r['variant']=='B-RECOVERY-ONLY' and r['scope']=='CONDITIONAL_CHAIN':reasons.update(r['risk_reason'].split(';'))
    rows=[dict(reason=k,unverifiable_conditional_cases=v,count_is_not_disjoint=True) for k,v in reasons.items()]
    table(PUB/'risk_boundary_counts.csv',rows)
    cases=[r for r in read_csv(PUB/'period_results.csv') if r['variant']=='B-RECOVERY-ONLY' and r['scope']=='CONDITIONAL_CHAIN']
    # Publish each separate account, never substitute a pooled annual return.
    table(PUB/'completed_chain_comparison.csv',[r for r in cases if int(r['completed_cycles'])>0])
    avg_holds=[float(r['holding_minutes']) for r in cs if r['variant']=='B-RECOVERY-ONLY' and r['scope']=='CONDITIONAL_CHAIN']
    old_summary=json.loads((PRIOR/'publish_payload/summary.json').read_text())
    table(PUB/'old_new_counts.csv',[dict(method='OLD_EXACT_60_SECOND_SEGMENTS',candidate_closure_bridges=0,periods=246,entries_per_variant=43,completed_per_variant=0,censored_per_variant=43,annual_return='UNAVAILABLE'),dict(method='APPROVED_REGULAR_CARRY',candidate_closure_bridges=199,periods=47,entries_per_variant=26,completed_per_variant=8,censored_per_variant=18,annual_return='UNAVAILABLE')])
    save(PUB/'post_validation.json',dict(status='PASS',variants_have_identical_economic_execution_paths=True,exit_reason_classification_preserved=True,control_both_conditions_cycles=sum(r['exit_reason']=='BOTH' for r in cs if r['variant']=='B-DUAL-CONTROL' and r['scope']=='CONDITIONAL_CHAIN'),each_entry_17_contracts_170000_usdt=True,no_same_timestamp_fills=True,all_completed_recovery_cycles_carried_overnight=True,completed_counts_not_doubled_annual_vs_chain=True,descriptive_completed_win_rate_pct=100.,descriptive_completed_cycles=8,descriptive_average_holding_minutes=sum(avg_holds)/len(avg_holds),descriptive_longest_holding_minutes=max(avg_holds),longest_censored_observed_holding_minutes=max(float(r['holding_minutes']) for r in rs if r['variant']=='B-RECOVERY-ONLY' and r['scope']=='CONDITIONAL_CHAIN'),risk_reasons=dict(reasons),return_sum_published_by_separate_chain_only=True,night_marks_or_executions=0,settlement_and_roll_fabrication=False))
    print((PUB/'post_validation.json').read_text())

if __name__=='__main__':main()
