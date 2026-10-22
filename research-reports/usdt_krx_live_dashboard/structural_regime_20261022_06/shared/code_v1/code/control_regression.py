# /// script
# requires-python = "==3.12.0"
# dependencies = ["numpy==2.2.6"]
# ///
# Run: python -B code/bootstrap.py control_regression.py
from __future__ import annotations
import hashlib,json
import numpy as np
from runner import ROOT,load,calculate,canonical,write_json
from registry import BASE

def main() -> None:
    """The sole permitted old-strategy market rerun, excluded from new condition count."""
    assert BASE['pnl_profit_pct']==.7
    candidate=dict(candidate_id='CONTROL_BF-09-027',group='BASELINE_CONTROL_NOT_NEW',rule=BASE,
        rule_sha256=hashlib.sha256(canonical(BASE)).hexdigest())
    target=ROOT/'control_regression'
    target.mkdir()
    write_json(target/'preregistration.json',dict(candidate=candidate,new_condition_count=0,
        purpose='New optional path gates must be inert for the original B',
        tolerances=dict(score_pp=1e-8,money_krw=.01),strict_arrays='exact numeric equality including NaN positions',
        code_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((ROOT/'code').glob('*.py'))}))
    v,frame,codes=load()
    result=calculate(candidate,v,frame,codes,target/'CONTROL_B')
    original=ROOT/'baseline/B_original'
    comparisons={}
    with np.load(original/'numeric_result.npz') as old,np.load(target/'CONTROL_B/numeric_result.npz') as new:
        for key in ('trades','events','residual','risk','equity','extremes','orders'):
            np.testing.assert_array_equal(old[key],new[key])
            comparisons[key]='EXACT_MATCH'
    with np.load(original/'full_account_ledger.npz') as old,np.load(target/'CONTROL_B/full_account_ledger.npz') as new:
        np.testing.assert_array_equal(old['ledger'],new['ledger'])
        comparisons['ledger']='EXACT_MATCH'
    assert result['cycles']==42 and result['residual_contracts']==0
    assert abs(result['score_pct']-16.7054302006977)<1e-8
    assert abs(result['net_realized']-41295918.91188297)<.01 and result['mdd_krw']==9350000.
    write_json(target/'validation.json',dict(status='PASS',candidate='BF-09-027',new_condition_count=0,
        cycles=42,score_pct=result['score_pct'],net_krw=result['net_realized'],mdd_krw=result['mdd_krw'],
        arrays=comparisons,baseline_profit_target_pct=.7,old_strategy_runs=1,
        exact_trade_cost_cash_margin_path_match=True))
    print(json.dumps(dict(status='PASS_CONTROL_EXACT_ARRAYS',cycles=42,score=result['score_pct'])),flush=True)

if __name__=='__main__':main()
