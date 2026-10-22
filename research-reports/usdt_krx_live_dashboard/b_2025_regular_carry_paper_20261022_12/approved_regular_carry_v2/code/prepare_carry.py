# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
# How to run: python -B code/bootstrap.py prepare_carry.py
import datetime as dt,json
from common import ROOT,PRIOR,BOUNDARY,SOURCE,ARCH,OUT,sha,read_csv,table,save

def main()->None:
    integrity=[]
    for root,manifest in ((PRIOR/'publish_payload',PRIOR/'publish_payload/manifest.csv'),(SOURCE,SOURCE/'publish_payload/local_artifact_hashes.csv'),(BOUNDARY/'publish_payload',BOUNDARY/'publish_payload/manifest.csv')):
        for r in read_csv(manifest):
            p=root/r['path'];b=p.read_bytes();assert len(b)==int(r['bytes']) and sha(b)==r['sha256'];integrity.append(dict(path=str(p),bytes=len(b),sha256=sha(b),passed=True))
    official={r['date']:r for r in read_csv(ARCH/'krx_2025_full_1m/contract_selection.csv') if r['date'].startswith('2025')};days=sorted(official);ranks={d:i for i,d in enumerate(days)}
    old=read_csv(BOUNDARY/'results/boundary_classification.csv');links=[];lookup={};chains=[];chain=1
    segments=[]
    with (PRIOR/'data_local/segments.jsonl').open(encoding='utf8') as f:
        for line in f:segments.append(json.loads(line))
    for i,seg in enumerate(segments):
        lookup[str(seg['segment'])]=chain
        for q in seg['quotes']:assert '09:00:00'<=q['t'][11:]<='15:30:00'
        if i==len(segments)-1:
            chains.append(dict(chain=chain,last=seg['quotes'][-1]['t'],end_reason='DATA_END',next_observation=''));break
        a=seg['quotes'][-1];b=segments[i+1]['quotes'][0];ta=dt.datetime.fromisoformat(a['t']);tb=dt.datetime.fromisoformat(b['t']);da=ta.strftime('%Y%m%d');db=tb.strftime('%Y%m%d')
        same=official[da]['contract_code_kis']==official[db]['contract_code_kis'];nextdate=ranks[db]==ranks[da]+1
        valid=official[da]['expiry_date']>=ta.date().isoformat() and official[db]['expiry_date']>=tb.date().isoformat();vol=float(official[da]['official_volume'])>0 and float(official[db]['official_volume'])>0
        clocks=ta.time()==dt.time(15,30) and tb.time()==dt.time(9);overnight=ta.date()!=tb.date()
        candidate=old[i]['reference_based_carry_requires_extra_assumption']=='True'
        eligible=candidate and overnight and same and nextdate and valid and vol and clocks
        tags=[]
        if not overnight:tags.append('INTRADAY_MISSING')
        if not same:tags.append('REFERENCE_ROLL_UNVERIFIED')
        if overnight and not nextdate:tags.append('MISSING_TRADING_DATES')
        if overnight and not clocks:tags.append('LOGGER_WINDOW_EDGE_MISSING')
        if not valid or not vol:tags.append('REFERENCE_VALIDITY_FAILED')
        reason='NORMAL_CLOSURE_APPROVED_ASSUMPTION' if eligible else ';'.join(tags) or 'CANDIDATE_NOT_APPROVED'
        links.append(dict(before=a['t'],after=b['t'],left_segment=seg['segment'],right_segment=segments[i+1]['segment'],old_candidate=candidate,rechecked_allowed=eligible,same_reference=same,consecutive_official_dates=nextdate,reference_traded_both=vol,reference_valid=valid,logger_edges_present=clocks,reason=reason,calendar_gap_minutes=(tb-ta).total_seconds()/60,actual_log_contract_confirmed=False))
        if not eligible:
            chains.append(dict(chain=chain,last=a['t'],end_reason=reason,next_observation=b['t']));chain+=1
    plan=dict(lookup=lookup,chains=chains,links=links)
    save(OUT/'carry_plan.json',plan);table(OUT/'boundary_recheck.csv',links);table(OUT/'chains.csv',chains);table(OUT/'input_integrity.csv',integrity)
    summary=dict(source_quotes=84717,prior_segments=246,prior_candidates=199,rechecked_allowed=sum(r['rechecked_allowed'] for r in links),chains=len(chains),no_raw_data_copied=True,integrity_checks=len(integrity),prior_results_changed=False)
    save(OUT/'preparation.json',summary);print(json.dumps(summary))

if __name__=='__main__':main()
