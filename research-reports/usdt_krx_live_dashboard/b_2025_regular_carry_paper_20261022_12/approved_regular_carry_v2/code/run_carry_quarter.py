# /// script
# requires-python = ">=3.12"
# dependencies = ["numpy==2.2.6"]
# ///
# How to run: python -B code/bootstrap.py run_carry_quarter.py 1, then2,3,4.
import datetime as dt,json,sys
from common import ROOT,PRIOR,OUT,sha,table,save
from model import Quote,Variant
from carry_engine import State,advance,residual
from carry_audit import tests,verify_through


def main()->None:
    quarter=int(sys.argv[1]);assert quarter in (1,2,3,4)
    dest=OUT/f'quarter_{quarter}';assert not dest.exists();dest.mkdir()
    frozen=json.loads((ROOT/'preregistration/execution_hashes.json').read_text())
    for r in frozen['code']:assert sha((ROOT/'code'/r['path']).read_bytes())==r['sha256']
    assert sha((PRIOR/'data_local/segments.jsonl').read_bytes())==frozen['source_quotes_sha256']
    plan=json.loads((OUT/'carry_plan.json').read_text());ends={r['chain']:r for r in plan['chains']}
    assert sha((OUT/'carry_plan.json').read_bytes())==frozen['carry_plan_sha256']
    if quarter==1:
        checkpoint={vid:{'annual':dict(active=True,chain=0,state=State().encode()),'period':dict(ended=True,chain=0,state=State().encode())} for vid in ('B-RECOVERY-ONLY','B-DUAL-CONTROL')}
        save(dest/'regression_tests.json',tests())
    else:checkpoint=json.loads((OUT/f'quarter_{quarter-1}/checkpoint.json').read_text())
    contexts={vid:{scope:dict(**{k:v for k,v in c.items() if k!='state'},state=State.restore(c['state'])) for scope,c in modes.items()} for vid,modes in checkpoint.items()}
    observations=[]
    with (PRIOR/'data_local/segments.jsonl').open(encoding='utf8') as f:
        for line in f:
            segment=json.loads(line);chain=plan['lookup'][str(segment['segment'])]
            for r in segment['quotes']:
                m=int(r['t'][5:7])
                if (quarter-1)*3<m<=quarter*3:observations.append((Quote.parse(r),chain))
    fills=[];cycles=[];marks=[];signals=[];residuals=[];monthly=[]
    for month in range((quarter-1)*3+1,quarter*3+1):
        for q,chain in [x for x in observations if x[0].t.month==month]:
            for variant in (Variant('B-RECOVERY-ONLY',None),Variant('B-DUAL-CONTROL',.7)):
                modes=contexts[variant.id];pc=modes['period']
                if pc['chain']!=chain:
                    assert pc['ended'];modes['period']=dict(ended=False,chain=chain,state=State());pc=modes['period']
                for scope,ctx in (('CONDITIONAL_CHAIN',pc),('ANNUAL_PREFIX',modes['annual'])):
                    if scope=='ANNUAL_PREFIX' and not ctx['active']:continue
                    ctx['chain']=chain;state=ctx['state'];r=advance(state,q,variant)
                    ident=dict(variant=variant.id,scope=scope,chain=chain)
                    for values,destination in ((r.fills,fills),(r.cycles,cycles),(r.signals,signals)):
                        for row in values:destination.append(dict(**ident,**row))
                    marks.append(dict(**ident,**r.mark))
                    if q.t.isoformat()==ends[chain]['last']:
                        rem=residual(state,ends[chain]['end_reason'])
                        if rem is not None:
                            residuals.append(dict(**ident,**rem))
                            if scope=='ANNUAL_PREFIX':ctx.update(active=False,censored_at=q.t.isoformat(),reason=ends[chain]['end_reason'])
                        else:state.prev=None;state.pending_entry=None;state.pending_exit=None
                        if scope=='CONDITIONAL_CHAIN':ctx['ended']=True
        for vid in ('B-RECOVERY-ONLY','B-DUAL-CONTROL'):
            chosen=lambda r:r['variant']==vid and r['scope']=='CONDITIONAL_CHAIN' and r.get('t',r.get('exit_t',r.get('last_observed_t',''))).startswith(f'2025-{month:02}')
            fs=[r for r in fills if chosen(r)];cs=[r for r in cycles if chosen(r)];rs=[r for r in residuals if chosen(r)]
            monthly.append(dict(month=f'2025-{month:02}',variant=vid,entries=sum(r['kind']=='ENTRY' for r in fs),completed_cycles=len(cs),recovery_exit_cycles=sum(r['exit_reason'] in ('RECOVERY','BOTH') for r in cs),cycles_with_normal_carry=sum(r['normal_closure_bridges']>0 for r in cs),completed_cycle_score_pct=sum(r['return_pct'] for r in cs),completed_cycle_net_krw=sum(r['net'] for r in cs),unverifiable_risk_or_end_opens=len(rs),annual_return_certified=False))
        print(json.dumps(dict(month=f'2025-{month:02}',results=monthly[-2:]),ensure_ascii=False),flush=True)
    for name,rows in (('fills',fills),('cycles',cycles),('marks',marks),('signals',signals),('residuals',residuals),('monthly',monthly)):table(dest/f'{name}.csv',rows)
    snapshots=[]
    for vid,modes in contexts.items():
        for scope,c in modes.items():
            rem=residual(c['state'],'QUARTER_CHECKPOINT_ONLY_NOT_CENSOR')
            if rem is not None and (c.get('active',True) and not c.get('ended',False)):snapshots.append(dict(variant=vid,scope=scope,chain=c['chain'],**rem))
    table(dest/'quarter_open_checkpoints.csv',snapshots)
    encoded={vid:{scope:{**{k:v for k,v in c.items() if k!='state'},'state':c['state'].encode()} for scope,c in modes.items()} for vid,modes in contexts.items()}
    (dest/'checkpoint.json').write_text(json.dumps(encoded,ensure_ascii=False,indent=2,default=lambda value:value.isoformat()),encoding='utf8')
    verify_through(quarter)
    print(json.dumps(dict(quarter=quarter,status='VERIFIED',quarter_boundary_accounts_preserved=len(snapshots))))

if __name__=='__main__':main()
