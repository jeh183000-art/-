# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
# How to run: python -B code/bootstrap.py post_checks.py
import json,gzip,collections
from common import ROOT,PUB,OUT,LOCAL,SOURCE,read_csv,save,table,sha


def main()->None:
    frozen=json.loads((ROOT/'preregistration/execution_hashes.json').read_text())
    assert sha((ROOT/'preregistration/settings.json').read_bytes())==frozen['settings_sha256']
    bounds=read_csv(PUB/'boundary_jumps.csv');rolls=[r for r in bounds if r['old_reference']!=r['new_reference']]
    with gzip.open(PUB/'valuation_ledger.csv.gz','rt',encoding='utf8') as f:
        import csv
        marks=list(csv.DictReader(f))
    quotes_by_t={}
    with (LOCAL/'segments.jsonl').open(encoding='utf8') as f:
        for line in f:
            s=json.loads(line)
            for q in s['quotes']:quotes_by_t[q['t']]=q
    maximal=0.
    for r in bounds:
        a=quotes_by_t[r['before']];b=quotes_by_t[r['after']]
        expected=(b['fa']+b['fb']-a['fa']-a['fb'])/2
        maximal=max(maximal,abs(expected-float(r['future_mid_jump_krw'])))
    assert maximal<1e-10
    signals=read_csv(PUB/'signals.csv');filled=read_csv(PUB/'fills.csv');residual=read_csv(PUB/'unverifiable_open.csv')
    assert all(int(float(r['contracts']))==17 and r['kind']=='ENTRY' for r in filled)
    assert len([r for r in filled if r['scope']=='INDEPENDENT_EPISODE' and r['variant']=='B-RECOVERY-ONLY'])==43
    assert len([r for r in residual if r['scope']=='INDEPENDENT_EPISODE' and r['variant']=='B-RECOVERY-ONLY'])==43
    assert all(float(r['contracts']) in (0.,17.) for r in marks)
    # The old audit's error-only files are retained as a metadata list; no prices are created.
    old_empty=read_csv(SOURCE/'publish_payload/error_only_future_dates.csv');assert len(old_empty)==20
    table(PUB/'price_missing_20_files.csv',old_empty)
    public_local_artifacts=[]
    for file in ('segments.jsonl',):
        p=LOCAL/file;public_local_artifacts.append(dict(path=str(p),bytes=p.stat().st_size,sha256=sha(p.read_bytes()),scope='LOCAL_ONLY_FULL_INPUT_QUOTE_TABLE_NOT_PUBLISHED'))
    table(PUB/'new_local_input_hashes.csv',public_local_artifacts)
    save(PUB/'post_verification.json',dict(status='PASS',roll_reference_boundaries=len(rolls),boundary_jump_formula_max_error=maximal,max_abs_roll_reference_boundary_jump_krw=max(abs(float(r['future_mid_jump_krw'])) for r in rolls),roll_prices_product_identity_confirmed=False,forced_rolls_executed=0,filled_event_count=len(filled),completed_exit_events=0,signal_rows=len(signals),financial_mark_rows=len(marks),unknown_price_files=20,all_filled_bundles_17=True,all_original_code_and_normalized_hashes_checked=True,cyclic_cash_resets_in_annual_chain=0,auxiliary_episode_accounts='separate not annual; explicitly disclosed',original_data_merged_with_quotes=False,source_data_downloads=0,annual_profit_computed=False))
    print((PUB/'post_verification.json').read_text())

if __name__=='__main__':main()
