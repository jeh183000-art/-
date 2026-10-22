# /// script
# requires-python = ">=3.12"
# dependencies = ["numpy==2.2.6"]
# ///
# How to run: python -B code/bootstrap.py finalize_results.py
from __future__ import annotations
import collections,gzip,json,shutil,statistics
from common import ROOT,OUT,PUB,SOURCE,LOCAL,OLD,sha,read_csv,table,save
from model import frozen_drawdowns,INITIAL_F


def main()->None:
    frozen=json.loads((ROOT/'preregistration/execution_hashes.json').read_text())
    for r in frozen['code']:assert sha((ROOT/'code'/r['path']).read_bytes())==r['sha256']
    assert sha((OLD/'validation2.py').read_bytes())==frozen['verified_mdd_reference']['sha256']
    collections_to_merge=('signals','fills','cycles','valuation_ledger','unverifiable_open','period_results','independent_audit','monthly_counts')
    merged={name:sum((read_csv(OUT/f'quarter_{q}/{name}.csv') for q in range(1,5)),[]) for name in collections_to_merge}
    # Header-only CSVs yield no rows: zero-cycle observations stay explicitly empty.
    assert len(merged['cycles'])==0
    assert all(r['passed']=='True' for r in merged['independent_audit'])
    assert len(merged['signals'])==306
    yearly=[]
    for variant in ('B-RECOVERY-ONLY','B-DUAL-CONTROL'):
        marks=[r for r in merged['valuation_ledger'] if r['variant']==variant and r['scope']=='ANNUAL_CHAIN_PREFIX']
        residual=[r for r in merged['unverifiable_open'] if r['variant']==variant and r['scope']=='ANNUAL_CHAIN_PREFIX']
        fills=[r for r in merged['fills'] if r['variant']==variant and r['scope']=='ANNUAL_CHAIN_PREFIX']
        trace=frozen_drawdowns([float(r['combined_equity']) for r in marks])
        prefix=dict(variant=variant,scope='ANNUAL_CHAIN_PREFIX',first=marks[0]['t'],last=marks[-1]['t'],entry_fills=len([r for r in fills if r['kind']=='ENTRY']),completed_cycles=0,annual_score_pct=None,annual_net_pnl_krw=None,annual_mdd_krw=None,completed_prefix_score_pct=0.0,completed_prefix_cycle_pnl_krw=0.0,entry_cost_paid_krw=sum(float(r[k]) for r in fills for k in ('spot_fee','future_fee','spot_slippage','future_slippage')),prefix_mdd_krw=float(trace[-1,2]),prefix_max_liquidation_loss_krw=max(-float(r['open_net_after_close_cost']) for r in marks),last_observed_liquidation_net_krw=float(residual[-1]['liquidation_estimate_net']),residual_contracts=17,holding_minutes_observed_lower_bound=float(residual[-1]['holding_minutes']),status='CENSORED_UNVERIFIABLE_AFTER_2025_01_03_NOT_FULL_YEAR',win_rate_pct=None,PF=None,margin='UNVERIFIED',time_product_contract='ASSUMED_NOT_CONFIRMED')
        yearly.append(prefix)
    table(PUB/'results.csv',yearly)
    for name in collections_to_merge:
        rows=merged[name]
        if name=='valuation_ledger':
            path=OUT/'all_valuation_ledger.csv';table(path,rows)
            with path.open('rb') as src,gzip.open(PUB/'valuation_ledger.csv.gz','wb') as dst:shutil.copyfileobj(src,dst)
        elif name=='cycles':table(PUB/'cycles.csv',[],['variant','scope','segment','cycle','entry_t','exit_t','net','return_pct','status'])
        else:table(PUB/f'{name}.csv',rows)
    for file in ('input_integrity.csv','preparation.json','exclusions.csv','duplicate_resolution.csv','boundary_jumps.csv','segments.csv','monthly_input.csv','regression_tests.json'):
        shutil.copyfile(OUT/file,PUB/file)
    for file in ('settings.json','execution_hashes.json','source_evidence.json'):shutil.copyfile(ROOT/'preregistration'/file,PUB/file)
    cdir=PUB/'code';cdir.mkdir(exist_ok=True)
    for path in (ROOT/'code').glob('*.py'):shutil.copyfile(path,cdir/path.name)
    # Previously published conditional comparisons are reused; neither the market inputs nor the old audit is modified.
    for file in ('cross_comparison_distribution.csv','cross_comparison_limitations.json','reference_input_hashes.csv'):
        shutil.copyfile(SOURCE/'publish_payload'/file,PUB/file)
    table(PUB/'costs.csv',[dict(**{k:r[k] for k in ('variant','scope','segment','cycle','kind','t','direction','contracts','spot_fee','future_fee','spot_slippage','future_slippage')},roll_cost=0,roll_status='NO_ROLL_EXECUTED_CROSSING_CENSORED') for r in merged['fills']])
    episodes=[r for r in merged['period_results'] if r['scope']=='INDEPENDENT_EPISODE']
    direction=[]
    for d in (1,-1):
        signals=[r for r in merged['signals'] if int(r['direction'])==d]
        direction.append(dict(direction=d,diagnostic_signals=len(signals),diagnostic_recoveries=sum(r['status']=='RECOVERY_OBSERVED' for r in signals),main_episode_entries=sum(r['variant']=='B-RECOVERY-ONLY' and int(r['direction'])==d and r['scope']=='INDEPENDENT_EPISODE' for r in merged['fills']),completed_cycles=0,completed_pnl=0,annual_pnl='UNAVAILABLE',borrowing='UNVERIFIED_THEORETICAL' if d==-1 else 'NOT_SPOT_SHORT'))
    table(PUB/'direction_counts.csv',direction)
    summary=dict(status='LOCAL_VERIFIED_PENDING_PUBLICATION',rule_variants=2,official_or_executable_performance=False,source_files_redownloaded=0,eligible_quote_observations=84717,independent_segments=246,input_integrity_checks=1306,independently_audited_runs=len(merged['independent_audit']),all_pass=True,diagnostic_entry_crossings=len(merged['signals']),next_continuous_quote_for_signal=sum(r['next_continuous_observation']=='True' for r in merged['signals']),diagnostic_recoveries=sum(r['status']=='RECOVERY_OBSERVED' for r in merged['signals']),annual_chain_censored_at='2025-01-03T15:30:00',annual_score_or_return=None,independent_episode_entries_per_variant=sum(int(r['entry_fills']) for r in episodes if r['variant']=='B-RECOVERY-ONLY'),independent_episode_unverifiable_opens_per_variant=sum(int(r['unverifiable_open_cycles']) for r in episodes if r['variant']=='B-RECOVERY-ONLY'),completed_cycles_each_variant=0,worst_episode_mdd_krw=max(float(r['mdd_krw']) for r in episodes),worst_episode_max_liquidation_loss_krw=max(float(r['max_liquidation_loss_krw']) for r in episodes),longest_censored_observed_holding_minutes=max(float(r['open_holding_lower_bound_minutes']) for r in episodes),originals_modified=False,protected_oos_accessed=False,margin_certification=False,roll_certification=False,price_timestamp_and_product_confirmed=False)
    save(PUB/'summary.json',summary)
    save(PUB/'checkpoint.json',dict(quarters_complete=[1,2,3,4],annual_chain_stopped_at='2025-01-03T15:30:00',backtest_mode='UNCONFIRMED_QUOTE_PAPER',full_year_financial_validation=False,no_next_sweep_scheduled=True))
    save(PUB/'provenance.json',dict(source_commit='c8469e29cbaf67368e4e0fff42de1d2a6fb779d4',audit_commit='5574b1b0c41ec863e9289f636ec04a1b3eb21b01',local_input_hash_inventory='input_integrity.csv',raw_and_complete_normalized_data_republication=False,complete_price_dataset_local_only=True,source_prices_not_official_bars=True,midpoint_gap_not_original_B_gap=True,execution_prices_assumed_ask_bid=True,simulation_fills_publish='Derived notional amounts, own fees/PnL and source references; original log lines and whole quote table not published',verified_drawdown_code=frozen['verified_mdd_reference'],costs_reference_engine_sha256=frozen['existing_engine_fee_reference_sha256'],settlement_and_roll_events='NOT_FABRICATED; any open boundary continuation is unverifiable',full_year_returns='NOT_COMPUTED',year2026_performance='Reference only; protected prices not accessed and existing B not rerun'))
    save(PUB/'environment.json',dict(python='3.12.0',numpy='2.2.6 existing installation',working_directory=str(ROOT),process_tmp_and_cache='D: study/runtime only',system_environment_changed=False,model='170000-USDT /17-contract assumed USD notional hedge; not certified identity',current_and_cumulative_dd='frozen validation2.drawdown_trace reused unchanged'))
    print(json.dumps(summary,ensure_ascii=False))

if __name__=='__main__':main()
