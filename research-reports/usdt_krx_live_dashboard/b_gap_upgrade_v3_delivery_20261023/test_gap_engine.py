"""Synthetic price scenarios only; run: python -B test_gap_engine.py"""
from datetime import datetime
from tempfile import TemporaryDirectory
from pathlib import Path
from gap_policy import classify_boundary
from run_gap_sensitivity import Quote, State, transition_tick, plan, run_one

official = {
 '20250103':dict(contract_code_kis='175W01',official_volume='1',expiry_date='2025-01-20'),
 '20250106':dict(contract_code_kis='175W01',official_volume='1',expiry_date='2025-01-20'),
 '20250107':dict(contract_code_kis='175W01',official_volume='1',expiry_date='2025-01-20'),
 '20250108':dict(contract_code_kis='175W01',official_volume='1',expiry_date='2025-01-20'),
 '20250109':dict(contract_code_kis='175W01',official_volume='1',expiry_date='2025-01-20'),
 '20250110':dict(contract_code_kis='175W01',official_volume='1',expiry_date='2025-01-20'),
 '20250120':dict(contract_code_kis='175W01',official_volume='1',expiry_date='2025-01-20'),
 '20250121':dict(contract_code_kis='175W02',official_volume='1',expiry_date='2025-02-17'),
}
ranks={k:i for i,k in enumerate(sorted(official))}

def q(t,g,ref='175W01'):
    fm=1000.;sm=fm*(1+g/100.)
    return Quote(datetime.fromisoformat(t),sm+.5,sm-.5,fm+.1,fm-.1,g,ref,'SYNTHETIC',1)

def exec_case(rows, tolerance):
    bridges,ids,events=plan(rows,official,ranks,tolerance)
    with TemporaryDirectory() as tmp:
        s,cs=run_one(rows,bridges,ids,'B-RECOVERY-ONLY',tolerance,Path(tmp))
    return s,cs,events

if __name__=='__main__':
    # Approved overnight: position held across a weekend; no fabricated market
    # observations or fills during closed clock hours.
    prices=[q('2025-01-03T15:27',0),q('2025-01-03T15:28',-1.1),
            q('2025-01-03T15:29',-1.2),q('2025-01-03T15:30',-1.2),
            q('2025-01-06T09:00',-.4),q('2025-01-06T09:01',-.3)]
    strict,strict_cycles,e=exec_case(prices,0)
    assert strict['conditional_entries']==1 and strict['conditional_completed_cycles']==1
    assert strict_cycles[0]['exit_t']=='2025-01-06T09:01:00'
    for n in (1,2):
        tolerant,cycles,e=exec_case(prices,n)
        assert tolerant['conditional_completed_cycles']==1 and cycles[0]['net']==strict_cycles[0]['net']
        assert not cycles[0]['gap_exposed']
    # Missing entry fill: never fill retroactively after a missing minute.
    entry_missing=[q('2025-01-10T09:00',0),q('2025-01-10T09:01',-1.1),
                   q('2025-01-10T09:03',-1.1),q('2025-01-10T09:04',-1.1)]
    s,c,e=exec_case(entry_missing,1)
    assert s['conditional_entries']==0
    # Do not detect a crossing across missing data.
    skipped_cross=[q('2025-01-10T09:00',0),q('2025-01-10T09:02',-1.1),
                   q('2025-01-10T09:03',-1.1),q('2025-01-10T09:04',-1.1)]
    s,c,e=exec_case(skipped_cross,1)
    assert s['conditional_entries']==0
    # Missing exit fill: cancel the pending order, re-evaluate on observed quote,
    # fill only at a consecutive next quote, and label the cycle gap-exposed.
    exit_missing=[q('2025-01-10T09:00',0),q('2025-01-10T09:01',-1.1),
        q('2025-01-10T09:02',-1.1),q('2025-01-10T09:03',-.4),
        q('2025-01-10T09:05',-.4),q('2025-01-10T09:06',-.4)]
    s,c,e=exec_case(exit_missing,1)
    c=[r for r in c if r['scope']=='CONDITIONAL_CHAIN']
    assert len(c)==1 and c[0]['gap_exposed'] and c[0]['exit_t']=='2025-01-10T09:06:00'
    assert c[0]['exit_signal_fill_gaps']==1 and c[0]['intraday_gap_count']==1
    s,c,e=exec_case(exit_missing,0)
    c=[r for r in c if r['scope']=='CONDITIONAL_CHAIN']
    assert len(c)==0 and s['conditional_censored_opens']==1
    # A genuine reference month change is never bridged, even at tolerance=2.
    roll=[q('2025-01-20T11:29',0),q('2025-01-20T11:30',-1.1),
          q('2025-01-21T09:00',-1.1,'175W02'),q('2025-01-21T09:01',-1.1,'175W02')]
    s,c,e=exec_case(roll,2)
    assert any(x['kind']=='REF_CHANGE_UNVERIFIED_ROLL' and not x['allowed'] for x in e)
    assert s['independent_chains']==2
    # Ordinary missing minutes can improve observational continuity, but never
    # claim that resulting gap-exposed winning trades are complete proof.
    print('TEST_GAP_ENGINE_PASS: overnight, missing-entry, missing-exit, reference-change, parity')
