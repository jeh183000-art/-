# /// script
# requires-python = ">=3.12"
# dependencies = ["numpy==2.2.6"]
# ///
# How to run: python -B code/bootstrap.py run_quarter.py 1 (then2,3,4; never reruns existing quarters).
from __future__ import annotations
import json,sys,statistics
from typing import Mapping
from dataclasses import asdict
from common import ROOT,LOCAL,OUT,sha,table,save
from model import Quote,Variant,Book,INITIAL_F,crossing,frozen_drawdowns
from simulator import run_segment
from verify_quote_book import audit_run,regressions


def signals_for_segment(quotes:list[Quote])->list:
    signals=[]
    for i in range(1,len(quotes)):
        d=crossing(quotes[i-1],quotes[i])
        if not d:continue
        q=quotes[i];hit=None;mae=0.0
        for later in quotes[i+1:]:
            mae=max(mae,-d*(later.gap-q.gap))
            if d*(later.gap-q.gap)>=.6-1e-12:hit=later;break
        signals.append(dict(t=q.t.isoformat(),direction=d,signal_gap=q.gap,target_gap=q.gap+d*.6,next_continuous_observation=i+1<len(quotes),recovery_t=hit.t.isoformat() if hit else '',recovery_minutes=(hit.t-q.t).total_seconds()/60 if hit else None,max_additional_gap_pp=mae,status='RECOVERY_OBSERVED' if hit else 'CENSORED_BEFORE_RECOVERY',segment=q.segment,source=q.source,line=q.line))
    return signals


def summarize(result,identity)->Mapping:
    rows=result.cycles;closed=[float(c['net']) for c in rows];wins=[x for x in closed if x>0];losses=[x for x in closed if x<0]
    trace=frozen_drawdowns([m['combined_equity'] for m in result.marks]);holds=[r['holding_minutes'] for r in rows]
    return dict(**identity,entry_fills=sum(e['kind']=='ENTRY' for e in result.fills),completed_cycles=len(rows),win_rate_pct=len(wins)/len(closed)*100 if closed else None,PF=sum(wins)/-sum(losses) if losses else 'INF_NO_LOSSES' if wins else None,completed_score_pct=sum(r['return_pct'] for r in rows),realized_net_krw=sum(closed),mdd_krw=float(trace[-1,2]),max_liquidation_loss_krw=max([0.]+[-m['open_net_after_close_cost'] for m in result.marks]),average_closed_holding_minutes=statistics.mean(holds) if holds else None,longest_closed_holding_minutes=max(holds) if holds else None,residual_contracts=17 if result.residual else 0,residual_net_after_estimated_close_cost=result.residual['liquidation_estimate_net'] if result.residual else 0.,open_holding_lower_bound_minutes=result.residual['holding_minutes'] if result.residual else 0.,unverifiable_open_cycles=int(result.residual is not None),canceled_entry_signals=result.canceled_entries,max_spot_entry_notional=max([0.]+[e['spot_notional'] for e in result.fills if e['kind']=='ENTRY']),minimum_future_cash=min(m['future_cash'] for m in result.marks),margin_verification='UNVERIFIED',borrow_verification='UNVERIFIED_THEORETICAL_REVERSE',roll_count=0,roll_cost_krw=0.,roll_cost_explanation='NO_CERTIFIED_ROLL_EXECUTED; crossing open positions censored, never free-rolled',annual_return=False)


def main()->None:
    quarter=int(sys.argv[1]);assert quarter in (1,2,3,4)
    dest=OUT/f'quarter_{quarter}';assert not dest.exists();dest.mkdir()
    frozen=json.loads((ROOT/'preregistration/execution_hashes.json').read_text())
    for row in frozen['code']:
        assert sha((ROOT/'code'/row['path']).read_bytes())==row['sha256']
    assert sha((LOCAL/'segments.jsonl').read_bytes())==frozen['segments_sha256']
    if quarter==1:
        save(dest/'regression_tests.json',regressions())
        checkpoint={v:dict(active=True,book=asdict(Book()),censored_at=None) for v in ('B-RECOVERY-ONLY','B-DUAL-CONTROL')}
    else:
        checkpoint=json.loads((OUT/f'quarter_{quarter-1}/checkpoint.json').read_text())
    all_fills=[];all_cycles=[];all_marks=[];residuals=[];checks=[];summaries=[];signals=[];monthly=[]
    raw=[]
    with (LOCAL/'segments.jsonl').open(encoding='utf8') as f:
        for line in f:
            r=json.loads(line)
            month=int(r['quotes'][0]['t'][5:7])
            if (quarter-1)*3<month<=quarter*3:raw.append(r)
    for month in range((quarter-1)*3+1,quarter*3+1):
        msegments=[r for r in raw if int(r['quotes'][0]['t'][5:7])==month]
        month_start=len(signals)
        for r in msegments:
            qs=[Quote.parse(q) for q in r['quotes']];signals.extend(signals_for_segment(qs))
            for variant in (Variant('B-RECOVERY-ONLY',None),Variant('B-DUAL-CONTROL',.7)):
                cases=[('INDEPENDENT_EPISODE',Book())]
                if checkpoint[variant.id]['active']:cases.append(('ANNUAL_CHAIN_PREFIX',Book(**checkpoint[variant.id]['book'])))
                for scope,initial in cases:
                    result=run_segment(qs,variant,initial)
                    proof=audit_run(qs,result,initial)
                    ident=dict(variant=variant.id,scope=scope,segment=r['segment'],first=qs[0].t.isoformat(),last=qs[-1].t.isoformat(),end_reason=r['end_reason'])
                    summaries.append(summarize(result,ident));checks.append(dict(**ident,**proof))
                    for collection,target in ((result.fills,all_fills),(result.cycles,all_cycles),(result.marks,all_marks)):
                        for row in collection:target.append(dict(**ident,**row))
                    if result.residual:residuals.append(dict(**ident,**result.residual))
                    if scope=='ANNUAL_CHAIN_PREFIX':
                        checkpoint[variant.id]['book']=asdict(result.book)
                        if result.residual:
                            checkpoint[variant.id]['active']=False;checkpoint[variant.id]['censored_at']=qs[-1].t.isoformat();checkpoint[variant.id]['reason']=r['end_reason']
        for variant in ('B-RECOVERY-ONLY','B-DUAL-CONTROL'):
            chosen=[r for r in summaries if r['variant']==variant and r['scope']=='INDEPENDENT_EPISODE' and int(r['first'][5:7])==month]
            monthly.append(dict(month=f'2025-{month:02}',variant=variant,diagnostic_entry_crossings=len(signals)-month_start,potential_next_quote_entries=sum(s['next_continuous_observation'] for s in signals[month_start:]),diagnostic_recoveries=sum(s['status']=='RECOVERY_OBSERVED' for s in signals[month_start:]),episode_entry_fills=sum(r['entry_fills'] for r in chosen),episode_completed_cycles=sum(r['completed_cycles'] for r in chosen),unverifiable_episode_opens=sum(r['unverifiable_open_cycles'] for r in chosen),annual_return='NOT_COMPUTED',interpretation='SEPARATE_EPISODE_COUNTS_NOT_ANNUAL_ACCOUNT_PERFORMANCE'))
        print(json.dumps(dict(month=f'2025-{month:02}',rows=monthly[-2:],annual_chain=checkpoint),ensure_ascii=False),flush=True)
    table(dest/'signals.csv',signals);table(dest/'fills.csv',all_fills);table(dest/'cycles.csv',all_cycles);table(dest/'valuation_ledger.csv',all_marks)
    table(dest/'unverifiable_open.csv',residuals);table(dest/'period_results.csv',summaries);table(dest/'independent_audit.csv',checks);table(dest/'monthly_counts.csv',monthly)
    save(dest/'checkpoint.json',checkpoint)
    print(json.dumps(dict(quarter=quarter,status='VERIFIED',runs=len(checks),all_independent_audits_pass=True,completed_independent_episode_cycles=sum(r['completed_cycles'] for r in summaries if r['scope']=='INDEPENDENT_EPISODE'))),flush=True)

if __name__=='__main__':main()
