# /// script
# requires-python = ">=3.12"
# dependencies = ["numpy==2.2.6"]
# ///
# How to run: python -B code/bootstrap.py finalize_carry.py; reporting only.
import collections,gzip,json,shutil,statistics
from common import ROOT,PRIOR,SOURCE,OUT,PUB,sha,read_csv,table,save
from model import INITIAL_F,frozen_drawdowns


def main()->None:
    frozen=json.loads((ROOT/'preregistration/execution_hashes.json').read_text())
    for r in frozen['code']:assert sha((ROOT/'code'/r['path']).read_bytes())==r['sha256']
    for r in frozen['immutable_dependencies']:assert sha(__import__('pathlib').Path(r['path']).read_bytes())==r['sha256']
    assert sha((ROOT/'preregistration/settings.json').read_bytes())==frozen['settings_sha256']
    data={n:sum((read_csv(OUT/f'quarter_{q}/{n}.csv') for q in range(1,5)),[]) for n in ('fills','cycles','signals','marks','residuals','monthly')}
    groups=collections.defaultdict(list)
    for m in data['marks']:groups[(m['variant'],m['scope'],m['chain'] if m['scope']=='CONDITIONAL_CHAIN' else 'ONE_ACCOUNT')].append(m)
    periods=[]
    for (variant,scope,chain),marks in groups.items():
        match=lambda r:r['variant']==variant and r['scope']==scope and (scope!='CONDITIONAL_CHAIN' or r['chain']==chain)
        fills=[r for r in data['fills'] if match(r)];cycles=[r for r in data['cycles'] if match(r)];residuals=[r for r in data['residuals'] if match(r)]
        nets=[float(r['net']) for r in cycles];holds=[float(r['holding_minutes']) for r in cycles];wins=[x for x in nets if x>0];losses=[x for x in nets if x<0]
        marks.sort(key=lambda r:r['t']);trace=frozen_drawdowns([float(r['combined_equity']) for r in marks])
        for m,(p,c,dd) in zip(marks,trace):assert abs(p-float(m['running_equity_peak']))<.0001 and abs(c-float(m['current_drawdown']))<.0001 and abs(dd-float(m['cumulative_mdd']))<.0001
        periods.append(dict(variant=variant,scope=scope,chain=chain,first=marks[0]['t'],last=marks[-1]['t'],entries=sum(r['kind']=='ENTRY' for r in fills),completed_cycles=len(cycles),win_rate_pct=len(wins)/len(nets)*100 if nets else None,PF=sum(wins)/-sum(losses) if losses else 'INF_NO_LOSSES' if wins else None,completed_cycle_score_pct=sum(float(r['return_pct']) for r in cycles),closed_cycle_net_krw=sum(nets),observed_mdd_krw=float(trace[-1,2]),maximum_observed_open_loss_krw=max([0.]+[-float(m['open_net_after_close_cost']) for m in marks]),average_completed_holding_minutes=statistics.mean(holds) if holds else None,longest_completed_holding_minutes=max(holds) if holds else None,normal_carry_completed_cycles=sum(int(r['normal_closure_bridges'])>0 for r in cycles),residual_contracts=17 if residuals else 0,last_observed_open_net_krw=float(residuals[-1]['liquidation_estimate_net']) if residuals else 0.,last_observed_total_net_krw=float(marks[-1]['combined_pnl']),risk_reason=residuals[-1]['risk_reason'] if residuals else '',residual_holding_minutes=float(residuals[-1]['holding_minutes']) if residuals else 0.,entry_cost_paid_krw=sum(float(r[k]) for r in fills if r['kind']=='ENTRY' for k in ('spot_fee','future_fee','spot_slippage','future_slippage')),minimum_observed_future_account_equity=min(float(m['future_account_equity']) for m in marks),max_spot_notional_reference=max(float(m['required_spot_notional']) for m in marks),annual_return_certified=False,overnight_risk='UNOBSERVED',margin_and_borrow='UNVERIFIED'))
    table(PUB/'period_results.csv',periods)
    table(PUB/'results.csv',[r for r in periods if r['scope']=='ANNUAL_PREFIX'])
    for name in ('fills','cycles','signals','residuals','monthly'):table(PUB/f'{name}.csv',data[name])
    table(OUT/'all_marks.csv',data['marks'])
    with (OUT/'all_marks.csv').open('rb') as src,gzip.open(PUB/'valuation_ledger.csv.gz','wb') as dst:shutil.copyfileobj(src,dst)
    archive=(PUB/'valuation_ledger.csv.gz').read_bytes();raw=gzip.decompress(archive);assert sha(raw)==sha((OUT/'all_marks.csv').read_bytes())
    save(PUB/'archive_verification.json',dict(path='valuation_ledger.csv.gz',compressed_bytes=len(archive),compressed_sha256=sha(archive),uncompressed_bytes=len(raw),uncompressed_sha256=sha(raw),rows=len(data['marks']),lossless=True))
    for filename in ('boundary_recheck.csv','chains.csv','carry_plan.json','input_integrity.csv','preparation.json','tests.json'):shutil.copyfile(OUT/filename,PUB/filename)
    for filename in ('settings.json','execution_hashes.json'):shutil.copyfile(ROOT/'preregistration'/filename,PUB/filename)
    for filename in ('strategy_code_ref.json','cross_comparison_distribution.csv','cross_comparison_limitations.json','reference_input_hashes.csv'):shutil.copyfile(PRIOR/'publish_payload'/filename,PUB/filename)
    shutil.copyfile(SOURCE/'publish_payload/error_only_future_dates.csv',PUB/'price_missing_20_files.csv')
    for q in range(1,5):
        shutil.copyfile(OUT/f'quarter_{q}/independent_audit.csv',PUB/f'independent_audit_quarter_{q}.csv')
        shutil.copyfile(OUT/f'quarter_{q}/quarter_open_checkpoints.csv',PUB/f'quarter_{q}_open_checkpoints.csv')
    table(PUB/'costs.csv',[{**{k:r[k] for k in ('variant','scope','chain','cycle','kind','t','contracts','spot_fee','future_fee','spot_slippage','future_slippage')},'roll_cost':0,'roll_status':'NO_ROLL_EXECUTED_UNVERIFIED_BOUNDARIES_CENSORED'} for r in data['fills']])
    first=[r for r in data['cycles'] if r['variant']=='B-RECOVERY-ONLY' and r['scope']=='ANNUAL_PREFIX'][0]
    table(PUB/'first_trade_path.csv',[m for m in data['marks'] if m['variant']=='B-RECOVERY-ONLY' and m['scope']=='ANNUAL_PREFIX' and m['cycle']=='1'])
    table(PUB/'first_completed_cycle.csv',[first])
    main=[r for r in periods if r['variant']=='B-RECOVERY-ONLY' and r['scope']=='ANNUAL_PREFIX'][0]
    cases=[r for r in periods if r['variant']=='B-RECOVERY-ONLY' and r['scope']=='CONDITIONAL_CHAIN']
    # Only counts and descriptive duration/risk extrema are pooled. Returns stay per separate account/chain.
    summary=dict(mode='APPROVED_CONDITIONAL_REGULAR_SESSION_CARRY_PAPER',boundaries_allowed=199,conditional_chains=47,final_independent_audit_accounts=len(read_csv(OUT/'quarter_4/independent_audit.csv')),completed_cycles_per_variant=sum(r['completed_cycles'] for r in cases),normal_carry_completed_cycles_per_variant=sum(r['normal_carry_completed_cycles'] for r in cases),entries_per_variant=sum(r['entries'] for r in cases),unverifiable_or_end_open_cases_per_variant=sum(r['residual_contracts']>0 for r in cases),annual_score_or_pnl=None,separate_chain_scores_not_annual=True,first_trade=first,annual_prefix=main,largest_separate_chain_observed_mdd=max(r['observed_mdd_krw'] for r in cases),largest_separate_chain_observed_open_loss=max(r['maximum_observed_open_loss_krw'] for r in cases),all_identity_borrow_depth_margin_unverified=True,night_marks_created=0,rolls_fabricated=0,originals_changed=False,source_downloads=0)
    save(PUB/'summary.json',summary)
    save(PUB/'checkpoint.json',dict(status='LOCAL_VERIFIED_PENDING_PUBLICATION',quarters_complete=[1,2,3,4],annual_prefix_censored_at=main['last'],annual_risk_reason=main['risk_reason'],continuation_scheduled=False))
    code=PUB/'code';code.mkdir(exist_ok=True)
    for path in (ROOT/'code').glob('*.py'):shutil.copyfile(path,code/path.name)
    print(json.dumps(summary,ensure_ascii=False))

if __name__=='__main__':main()
