"""2025 B quote-log PAPER: immutable strict/1m/2m missing-data sensitivity.

Run only on the user's existing D: Windows inputs; no downloading, trading,
OOS access, interpolation, forward filling, trade optimization or writes to input.
Not an official KRX/backtest/annual return validation. Python 3.12+, stdlib only.

  python -B run_gap_sensitivity.py --input "D:/.../data_local/segments.jsonl" \
      --official "D:/.../krx_2025_full_1m/contract_selection.csv" \
      --out "D:/Codex_Research/usdt_krx_live_dashboard/studies/b_2025_gap_sensitivity_v3"
"""
from __future__ import annotations
import argparse, csv, hashlib, json
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from datetime import datetime
from gap_policy import Boundary, classify_boundary

Q=170000.0
CONTRACTS=17
INITIAL=30000000.0
VARIANTS=('B-RECOVERY-ONLY','B-DUAL-CONTROL')
SENSITIVITIES=(0,1,2)
BASELINE=dict(chains=47,normal_bridges=199,entries=26,cycles=8,unverifiable_opens=18,
              first_entry='2025-01-03T10:21:00',first_exit='2025-01-06T09:02:00',
              first_net=1006055.4538430077,annual_prefix_last='2025-01-10T09:01:00')

@dataclass(frozen=True)
class Quote:
    t:datetime
    sa:float
    sb:float
    fa:float
    fb:float
    gap:float
    reference_contract:str
    source:str
    line:int
    @classmethod
    def parse(cls, r):
        q=cls(datetime.fromisoformat(r['t']),float(r['sa']),float(r['sb']),
              float(r['fa']),float(r['fb']),float(r['gap']),str(r['reference_contract']),
              str(r['source']),int(r['line']))
        assert min(q.sa,q.sb,q.fa,q.fb)>0 and q.sa>=q.sb and q.fa>=q.fb
        assert abs(q.gap-100*((q.sa+q.sb)/(q.fa+q.fb)-1))<1e-8
        return q

@dataclass
class Position:
    cycle:int
    direction:int
    signal:Quote
    entry:Quote
    sp:float
    fp:float
    entry_costs:tuple[float,float,float,float]
    overnight_bridges:int=0
    unseen_calendar_minutes:int=0
    small_gap_count:int=0
    edge_gap_count:int=0
    skipped_intraday_minutes:int=0
    skipped_edge_minutes:int=0
    missing_fill_after_exit_signal:int=0

@dataclass
class State:
    cash_spot:float=0.0
    cash_future:float=INITIAL
    realized:float=0.0
    counter:int=0
    position:Position|None=None
    previous:Quote|None=None
    pending_entry:tuple[int,Quote]|None=None
    pending_exit:Quote|None=None
    exit_cause:str=''
    high_equity:float=INITIAL
    mdd:float=0.0
    max_observed_open_loss:float=0.0


def fee(sp,fp):
    return (sp*Q*.0005,CONTRACTS*600+fp*Q*.000003157,sp*Q*.0002,fp*Q*.0002)


def execution(q,direction,entry):
    buyspot=(direction==1)==entry
    return (q.sa,q.fb) if buyspot else (q.sb,q.fa)


def liquidation(p,q):
    sp,fp=execution(q,p.direction,False)
    spot=p.direction*(sp-p.sp)*Q
    future=p.direction*(p.fp-fp)*Q
    close_cost=fee(sp,fp)
    net=spot+future-sum(p.entry_costs)-sum(close_cost)
    return net,spot,future,close_cost,sp,fp


def crossing(prev,q):
    if prev.gap>-.97 and q.gap<=-.97:return 1
    if prev.gap<.85 and q.gap>=.85:return -1
    return 0


def transition_tick(s:State,q:Quote,bridge:Boundary|None,variant:str,scope:str,chain:int):
    fills=[];cycles=[];signals=[];events=[]
    assert bridge is None or bridge.allowed
    jumped=bridge is not None and bridge.kind!='CONTIGUOUS'
    if jumped:
        if s.pending_entry is not None:
            events.append(dict(kind='CANCEL_MISSING_ENTRY_FILL',t=q.t.isoformat(),reason=bridge.kind))
        if s.pending_exit is not None:
            events.append(dict(kind='CANCEL_MISSING_EXIT_FILL',t=q.t.isoformat(),reason=bridge.kind))
            if s.position:s.position.missing_fill_after_exit_signal+=1
        s.pending_entry=None;s.pending_exit=None
        if s.position:
            p=s.position
            if bridge.kind in ('NORMAL_CLOSED_SESSION','SESSION_EDGE_SMALL_GAP'):
                p.overnight_bridges+=1
                p.unseen_calendar_minutes+=(q.t-s.previous.t).total_seconds()/60-1
            if bridge.kind=='INTRADAY_SMALL_GAP':
                p.small_gap_count+=1;p.skipped_intraday_minutes+=bridge.missing_minutes
            elif bridge.kind=='SESSION_EDGE_SMALL_GAP':
                p.edge_gap_count+=1;p.skipped_edge_minutes+=bridge.missing_minutes
        events.append(dict(kind='OBSERVED_GAP',t=q.t.isoformat(),reason=bridge.kind,unobserved_mins=bridge.missing_minutes))
    # Execution is ONLY on an actually observed 60-second successor of signal.
    if s.pending_exit is not None:
        p=s.position
        assert p is not None and s.previous is not None and (q.t-s.pending_exit.t).total_seconds()==60
        close_net,sg,fg,cc,sp,fp=liquidation(p,q)
        s.cash_spot+=p.direction*sp*Q-cc[0]-cc[2]
        s.cash_future+=fg-cc[1]-cc[3]
        s.realized+=close_net
        flags=dict(intraday_gap_count=p.small_gap_count,edge_gap_count=p.edge_gap_count,
                   missing_intraday_minutes=p.skipped_intraday_minutes,missing_edge_minutes=p.skipped_edge_minutes,
                   exit_signal_fill_gaps=p.missing_fill_after_exit_signal,
                   gap_exposed=bool(p.small_gap_count or p.edge_gap_count or p.missing_fill_after_exit_signal),
                   overnight_bridges=p.overnight_bridges,unobserved_calendar_minutes=p.unseen_calendar_minutes,
                   contract_verified=False,timezone_verified=False,borrowing_verified=False,depth_verified=False,
                   margin_verified=False)
        cycles.append(dict(variant=variant,scope=scope,chain=chain,cycle=p.cycle,direction=p.direction,
             entry_signal_t=p.signal.t.isoformat(),entry_t=p.entry.t.isoformat(),
             exit_signal_t=s.pending_exit.t.isoformat(),exit_t=q.t.isoformat(),
             entry_signal_gap=p.signal.gap,exit_signal_gap=s.pending_exit.gap,
             entry_notional=p.sp*Q,spot_gross=sg,future_gross=fg,
             fees=p.entry_costs[0]+p.entry_costs[1]+cc[0]+cc[1],
             slippage=p.entry_costs[2]+p.entry_costs[3]+cc[2]+cc[3],net=close_net,
             return_pct=close_net/(p.sp*Q)*100,holding_minutes=(q.t-p.entry.t).total_seconds()/60,
             exit_reason=s.exit_cause,rolls=0,**flags))
        fills.append(dict(variant=variant,scope=scope,chain=chain,kind='EXIT',t=q.t.isoformat(),cycle=p.cycle,
             direction=p.direction,spot_price=sp,future_price=fp,
             spot_fee=cc[0],future_fee=cc[1],spot_slippage=cc[2],future_slippage=cc[3],
             source=q.source,line=q.line))
        s.position=None;s.pending_exit=None
    if s.pending_entry is not None:
        d,signal=s.pending_entry
        assert s.position is None and (q.t-signal.t).total_seconds()==60
        sp,fp=execution(q,d,True);ec=fee(sp,fp);s.counter+=1
        s.cash_spot-=d*sp*Q+ec[0]+ec[2]
        s.cash_future-=ec[1]+ec[3]
        s.position=Position(s.counter,d,signal,q,sp,fp,ec)
        fills.append(dict(variant=variant,scope=scope,chain=chain,kind='ENTRY',t=q.t.isoformat(),cycle=s.counter,
             direction=d,spot_price=sp,future_price=fp,
             spot_fee=ec[0],future_fee=ec[1],spot_slippage=ec[2],future_slippage=ec[3],
             source=q.source,line=q.line))
        s.pending_entry=None
    open_net=0.0;future_unrealized=0.0
    if s.position is not None:
        p=s.position;open_net=liquidation(p,q)[0]
        future_exit=execution(q,p.direction,False)[1]
        future_unrealized=p.direction*(p.fp-future_exit)*Q
        s.max_observed_open_loss=max(s.max_observed_open_loss,-open_net)
        recovered=p.direction*(q.gap-p.signal.gap)>=.6-1e-12
        pnl=variant=='B-DUAL-CONTROL' and open_net/(p.sp*Q)*100>=.7-1e-12
        if recovered or pnl:
            s.pending_exit=q
            s.exit_cause='BOTH' if recovered and pnl else 'RECOVERY' if recovered else 'PNL_TARGET'
            signals.append(dict(variant=variant,scope=scope,chain=chain,kind='EXIT_SIGNAL',t=q.t.isoformat(),
                 cycle=p.cycle,direction=p.direction,gap=q.gap,reason=s.exit_cause))
    elif s.previous is not None and not jumped:
        d=crossing(s.previous,q)
        if d:
            s.pending_entry=(d,q)
            signals.append(dict(variant=variant,scope=scope,chain=chain,kind='ENTRY_SIGNAL',t=q.t.isoformat(),
                 cycle=s.counter+1,direction=d,gap=q.gap,reason='MIDPOINT_CROSS'))
    eq=INITIAL+s.realized+open_net
    s.high_equity=max(s.high_equity,eq);s.mdd=max(s.mdd,s.high_equity-eq)
    mark=dict(variant=variant,scope=scope,chain=chain,t=q.t.isoformat(),
         position_direction=s.position.direction if s.position else 0,
         held_contracts=CONTRACTS if s.position else 0,
         cash_spot=s.cash_spot,cash_future=s.cash_future,future_unrealized=future_unrealized,
         future_equity_observed_reference=s.cash_future+future_unrealized,realized=s.realized,
         open_net_estimate=open_net,equity_reference=eq,running_mdd=s.mdd,
         gap_exposed=bool(s.position and (s.position.small_gap_count or s.position.edge_gap_count or s.position.missing_fill_after_exit_signal)),
         source=q.source,line=q.line)
    s.previous=q
    return fills,cycles,signals,events,mark


def censor(s:State,variant:str,scope:str,chain:int,reason:str):
    if not s.position:return None
    p=s.position;assert s.previous is not None
    net,sg,fg,c,sp,fp=liquidation(p,s.previous)
    return dict(variant=variant,scope=scope,chain=chain,cycle=p.cycle,direction=p.direction,
       entry_t=p.entry.t.isoformat(),last_observed_t=s.previous.t.isoformat(),
       hypothetical_liquidation_net=net,observed_holding_minutes=(s.previous.t-p.entry.t).total_seconds()/60,
       intraday_gap_count=p.small_gap_count,edge_gap_count=p.edge_gap_count,
       missing_intraday_minutes=p.skipped_intraday_minutes,missing_edge_minutes=p.skipped_edge_minutes,
       missing_exit_fill_count=p.missing_fill_after_exit_signal,overnight_bridges=p.overnight_bridges,
       risk_reason=reason,realized=False,contract_verified=False,margin_verified=False,borrow_verified=False)


def load_quotes(path:Path):
    h=hashlib.sha256();rows=[];segments=0
    with path.open('rb') as f:
        for raw in f:
            h.update(raw);segment=json.loads(raw);segments+=1
            for r in segment['quotes']:rows.append(Quote.parse(r))
    assert rows and all(a.t<b.t for a,b in zip(rows,rows[1:])), 'invalid quote ordering'
    assert len(rows)==84717 and segments==246, (len(rows),segments)
    return rows,h.hexdigest()


def load_official(path:Path):
    with path.open(encoding='utf-8-sig',newline='') as f:
        arr=[r for r in csv.DictReader(f) if r['date'].startswith('2025')]
    by={r['date']:r for r in arr}
    assert len(by)==len(arr) and len(by)>=240
    return by,{d:i for i,d in enumerate(sorted(by))}


def plan(quotes,official,ranks,tolerance):
    bridges=[None];chains=[1];chain=1;bridge_events=[]
    for left,right in zip(quotes,quotes[1:]):
        b=classify_boundary(left,right,official,ranks,tolerance)
        if not b.allowed:chain+=1
        bridges.append(b);chains.append(chain)
        if b.kind!='CONTIGUOUS':
            bridge_events.append(dict(before=left.t.isoformat(),after=right.t.isoformat(),kind=b.kind,
                  allowed=b.allowed,missing_minutes=b.missing_minutes,reason=b.reason,
                  reference_a=left.reference_contract,reference_b=right.reference_contract,
                  actual_contract_verified=False))
    return bridges,chains,bridge_events


def run_one(quotes,bridges,chain_ids,variant,tolerance,detail):
    annual=State();period=State();annual_active=True;prev_chain=chain_ids[0]
    all_fills=[];all_cycles=[];all_residuals=[];all_signals=[];all_marks=[];all_events=[]
    # Each independent period receives an explicitly separate reference cash balance.
    for i,(q,chain) in enumerate(zip(quotes,chain_ids)):
        if chain!=prev_chain:
            reason=bridges[i].kind
            rem=censor(period,variant,'CONDITIONAL_CHAIN',prev_chain,reason)
            if rem:all_residuals.append(rem)
            period=State()
            if annual_active:
                rem=censor(annual,variant,'ANNUAL_PREFIX',prev_chain,reason)
                if rem:
                    all_residuals.append(rem)
                    annual_active=False
                else:
                    annual.previous=None;annual.pending_entry=None;annual.pending_exit=None
            prev_chain=chain
        bridged=bridges[i] if i and bridges[i].allowed and bridges[i].kind!='CONTIGUOUS' else None
        for scope,state in [('CONDITIONAL_CHAIN',period),('ANNUAL_PREFIX',annual)]:
            if scope=='ANNUAL_PREFIX' and not annual_active:continue
            fs,cs,ss,es,m=transition_tick(state,q,bridged,variant,scope,chain)
            all_fills.extend(fs);all_cycles.extend(cs);all_signals.extend(ss)
            all_events.extend(dict(variant=variant,scope=scope,chain=chain,**e) for e in es)
            all_marks.append(m)
    rem=censor(period,variant,'CONDITIONAL_CHAIN',prev_chain,'END_OF_OBSERVED_DATA')
    if rem:all_residuals.append(rem)
    if annual_active:
        rem=censor(annual,variant,'ANNUAL_PREFIX',prev_chain,'END_OF_OBSERVED_DATA')
        if rem:all_residuals.append(rem)
    episodes=[c for c in all_cycles if c['scope']=='CONDITIONAL_CHAIN']
    episode_entries=sum(f['scope']=='CONDITIONAL_CHAIN' and f['kind']=='ENTRY' for f in all_fills)
    episode_censors=[c for c in all_residuals if c['scope']=='CONDITIONAL_CHAIN']
    annual_rows=[r for r in all_marks if r['scope']=='ANNUAL_PREFIX']
    annual_cycles=[c for c in all_cycles if c['scope']=='ANNUAL_PREFIX']
    annual_residuals=[c for c in all_residuals if c['scope']=='ANNUAL_PREFIX']
    period_marks=[r for r in all_marks if r['scope']=='CONDITIONAL_CHAIN']
    summary=dict(variant=variant,allowed_missing_minutes=tolerance,
         independent_chains=max(chain_ids),conditional_entries=episode_entries,
         conditional_completed_cycles=len(episodes),conditional_censored_opens=len(episode_censors),
         conditional_gap_exposed_completed=sum(c['gap_exposed'] for c in episodes),
         conditional_no_gap_exposure_completed=sum(not c['gap_exposed'] for c in episodes),
         conditional_completed_wins=sum(c['net']>0 for c in episodes),
         worst_conditional_chain_observed_mdd=max((m['running_mdd'] for m in period_marks),default=0.0),
         worst_conditional_chain_open_loss=max((max(0,-m['open_net_estimate']) for m in period_marks),default=0.0),
         minimum_conditional_chain_observed_future_equity=min((m['future_equity_observed_reference'] for m in period_marks),default=None),
         conditional_completed_net_krw_sum_NOT_ANNUAL=sum(c['net'] for c in episodes),
         conditional_completed_return_pct_sum_NOT_ANNUAL=sum(c['return_pct'] for c in episodes),
         annual_prefix_last=annual_rows[-1]['t'] if annual_rows else None,
         annual_prefix_entries=sum(f['scope']=='ANNUAL_PREFIX' and f['kind']=='ENTRY' for f in all_fills),
         annual_prefix_completed=len(annual_cycles),
         annual_prefix_realized_net=sum(c['net'] for c in annual_cycles),
         annual_prefix_last_total_observed=annual_rows[-1]['equity_reference']-INITIAL if annual_rows else None,
         annual_prefix_mdd=annual_rows[-1]['running_mdd'] if annual_rows else None,
         annual_prefix_min_future_equity=min((m['future_equity_observed_reference'] for m in annual_rows),default=None),
         annual_prefix_unverifiable_remaining=len(annual_residuals),
         annual_prefix_status='CENSORED_OR_END_NO_ANNUAL_VALIDATION',
         annual_return_available=False, official_futures_data=False, source_identity_verified=False,
         qualified_only_as_sensitivity_PAPER=True)
    # Independent recomputation of all completed cycles using decimal arithmetic.
    for c in all_cycles:
        v=lambda k:Decimal(str(c[k]))
        reconstructed=v('spot_gross')+v('future_gross')-v('fees')-v('slippage')
        assert abs(reconstructed-v('net'))<Decimal('0.0001'),c
        assert abs(v('return_pct')-(v('net')/v('entry_notional')*100))<Decimal('0.00000001'),c
        assert c['gap_exposed']==bool(c['intraday_gap_count'] or c['edge_gap_count'] or c['exit_signal_fill_gaps'])
    # Full financial ledgers are written to D only, never by this script to GitHub.
    for fn,records in [('fills',all_fills),('cycles',all_cycles),('residuals',all_residuals),
                       ('signals',all_signals),('observed_valuation_ledger',all_marks),('gap_events',all_events)]:
        write_csv(detail/f'{fn}.csv',records)
    return summary,all_cycles


def write_csv(path,rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf-8',newline='') as f:
        if not rows:
            f.write('status\nEMPTY\n');return
        fields=list(dict.fromkeys(k for row in rows for k in row))
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='raise');w.writeheader();w.writerows(rows)


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--input',required=True,type=Path)
    ap.add_argument('--official',required=True,type=Path)
    ap.add_argument('--out',required=True,type=Path)
    a=ap.parse_args()
    assert a.input.is_file() and a.official.is_file(), 'must provide existing D: input files'
    if a.out.exists():
        assert not any(a.out.iterdir()),'destination must be absent or empty, NEVER overwrite old study'
    a.out.mkdir(parents=True,exist_ok=True)
    quotes,data_sha=load_quotes(a.input);official,ranks=load_official(a.official)
    results=[];strict_ok=False
    for tolerance in SENSITIVITIES:
        bridges,ids,bev=plan(quotes,official,ranks,tolerance)
        label=f'MISSING_{tolerance}M'
        dat=a.out/label;dat.mkdir(exist_ok=False)
        write_csv(dat/'boundaries.csv',bev)
        normal=sum(b.kind=='NORMAL_CLOSED_SESSION' for b in bridges if b)
        for variant in VARIANTS:
            detail=dat/variant;detail.mkdir(exist_ok=False)
            summary,cycles=run_one(quotes,bridges,ids,variant,tolerance,detail)
            summary.update(strict_baseline_reference={'reference_commit':'72cc8eb39044f0ccc056cf9e1b1ffe637e5dbf74',
                      'strict_expected_entries':26,'strict_expected_completed':8,'strict_expected_censored':18},
                normal_overnight_bridge_count=normal,
                small_bridge_events=sum(b.allowed and b.missing_minutes>0 for b in bridges if b))
            if tolerance==0:
                found=(summary['independent_chains'],normal,summary['conditional_entries'],
                       summary['conditional_completed_cycles'],summary['conditional_censored_opens'])
                expected=(47,199,26,8,18)
                assert found==expected,f'STRICT BASELINE MISMATCH: found {found}, expected {expected}. DO NOT ACCEPT V3 RESULTS.'
                first=next((c for c in cycles if c['scope']=='CONDITIONAL_CHAIN' and c['entry_t']==BASELINE['first_entry']),None)
                assert first is not None and first['exit_t']==BASELINE['first_exit'] and abs(first['net']-BASELINE['first_net'])<.0001,'baseline first-cycle mismatch'
                assert summary['annual_prefix_last']==BASELINE['annual_prefix_last'],'annual prefix end mismatch'
                assert abs(summary['annual_prefix_last_total_observed']-(-6524711.524555992))<.01,'baseline annual-prefix marked PnL mismatch'
                assert abs(summary['annual_prefix_mdd']-7530766.978399001)<.01,'baseline annual-prefix MDD mismatch'
                strict_ok=True
            results.append(summary)
        print(f'COMPLETE {label} (reference {normal} normal closure bridges)')
    assert strict_ok
    write_csv(a.out/'sensitivity_comparison.csv',results)
    (a.out/'summary.json').write_text(json.dumps(dict(status='CONDITIONAL_SENSITIVITY_COMPLETED_BASELINE_AUDITED',
          strict_reproduced=True,source_input_sha256=data_sha,official_input_sha256=hashlib.sha256(a.official.read_bytes()).hexdigest(),
          annual_2025_verified=False,source_price_identity_verified=False,baseline_commit='72cc8eb39044f0ccc056cf9e1b1ffe637e5dbf74',
          notes=['This is missing-observation sensitivity, NOT new official 2025 validation',
                 'Risk-exposed closed trades cannot be certified as unbiased fills',
                 'No overnight / intragap prices or executions simulated',
                 'Reference monthly futures mapping not actual log identity',
                 'No margin/borrow/depth certification and no roll fabrication'],results=results),
          ensure_ascii=False,indent=2),encoding='utf8')
    print('GAP_TOLERANCE_STUDY_COMPLETE; note independent-chain sums are NOT annual returns')

if __name__=='__main__':main()
