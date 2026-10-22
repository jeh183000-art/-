# /// script
# requires-python = ">=3.12"
# dependencies = ["numpy==2.2.6"]
# ///
# How to run: imported by fixed_rule_run.py; Decimal checks are independent of float execution.
from __future__ import annotations
from decimal import Decimal as D
from typing import Mapping
import numpy as np
from model import Q,INITIAL_F,Quote,Variant,Book,frozen_drawdowns
from simulator import SegmentRun,run_segment


def audit_run(quotes:list[Quote],result:SegmentRun,initial:Book)->Mapping[str,float|int|bool]:
    """Replay cash and liquidation marks from source-side quotations, not simulator fee helpers."""
    sc=D(str(initial.spot_cash));fc=D(str(initial.future_cash));held=0;sp=D(0);fp=D(0);cyc=0;cost=D(0);realized=D(str(initial.realized));closed=[];at=0;equities=[];maxdiff=0.
    events=result.fills
    for i,q in enumerate(quotes):
        while at<len(events) and events[at]['t']==q.t.isoformat():
            e=events[at];d=int(e['direction']);kind=e['kind'];assert int(e['contracts'])==17 and float(e['quantity_usdt'])==170000
            assert i>0 and e['signal_t']==quotes[i-1].t.isoformat() and (q.t-quotes[i-1].t).total_seconds()==60
            entering=kind=='ENTRY'
            buying_spot=(d==1)==entering
            s=D(str(q.sa if buying_spot else q.sb));f=D(str(q.fb if buying_spot else q.fa));qty=D(170000)
            sf=s*qty*D('.0005');ff=D(17)*D(600)+f*qty*D('.000003157');ss=s*qty*D('.0002');fs=f*qty*D('.0002')
            for key,value in (('spot_fee',sf),('future_fee',ff),('spot_slippage',ss),('future_slippage',fs),('spot_notional',s*qty),('future_notional',f*qty)):
                diff=abs(float(value)-float(e[key]));maxdiff=max(maxdiff,diff);assert diff<.00001
            if entering:
                assert held==0
                held=d;sp=s;fp=f;cyc=int(e['cycle']);cost=sf+ff+ss+fs
                sc-=D(d)*s*qty+sf+ss;fc-=ff+fs
            else:
                assert kind=='EXIT' and held==d and cyc==int(e['cycle'])
                sg=D(d)*(s-sp)*qty;fg=D(d)*(fp-f)*qty;net=sg+fg-cost-sf-ff-ss-fs
                closed.append((cyc,float(net),float(net/(sp*qty)*100)))
                sc+=D(d)*s*qty-sf-ss;fc+=fg-ff-fs;realized+=net;held=0
            assert abs(float(sc)-float(e['spot_cash']))<.0001 and abs(float(fc)-float(e['future_cash']))<.0001
            at+=1
        m=result.marks[i];open_net=D(0);fu=D(0);reserve=D(0)
        if held:
            s=D(str(q.sb if held==1 else q.sa));f=D(str(q.fa if held==1 else q.fb));qty=D(170000)
            fu=D(held)*(fp-f)*qty
            reserve=s*qty*D('.0007')+D(10200)+f*qty*(D('.000003157')+D('.0002'))
            open_net=D(held)*(s-sp)*qty+fu-cost-reserve
        total=realized+open_net
        assert abs(float(total)-float(m['combined_pnl']))<.0001
        assert abs(float(open_net)-float(m['open_net_after_close_cost']))<.0001
        assert abs(float(fu)-float(m['future_unrealized']))<.0001
        assert abs(float(sc)-float(m['spot_cash']))<.0001 and abs(float(fc)-float(m['future_cash']))<.0001
        assert int(m['contracts']) in (0,17) and int(m['held_direction'])==held
        equities.append(INITIAL_F+float(total))
    assert at==len(events) and len(closed)==len(result.cycles)
    for (cycle,net,score),r in zip(closed,result.cycles):
        assert cycle==r['cycle'] and abs(net-r['net'])<.0001 and abs(score-r['return_pct'])<1e-10
    trace=frozen_drawdowns(equities)
    peak=INITIAL_F;mdd=0.
    for value,(p,dd,maximum) in zip(equities,trace):
        peak=max(peak,value);mdd=max(mdd,peak-value)
        assert abs(p-peak)<.0001 and abs(dd-(peak-value))<.0001 and abs(maximum-mdd)<.0001
    return dict(passed=True,checked_quotes=len(quotes),events=len(events),completed_cycles=len(closed),maximum_fee_difference_krw=maxdiff,mdd_krw=mdd)


def regressions()->Mapping[str,int|bool]:
    """Given causal synthetic quotes, verify direction, costs, timing, missing exits and cumulative DD."""
    from datetime import datetime,timedelta
    from dataclasses import replace
    q=[]
    for i,g in enumerate([0.,-1.1,-1.2,-.4,-.3,0.,1.1,1.2,.4,.3,0.]):
        mid=1000*(1+g/100)
        q.append(Quote(datetime(2025,1,3,9)+timedelta(minutes=i),mid+.5,mid-.5,1000.1,999.9,g,'SYNTHETIC',i+1,'SYNTHETIC',1))
    r=run_segment(q,Variant('TEST',None),Book());proof=audit_run(q,r,Book())
    assert len(r.cycles)==2 and r.cycles[0]['direction']==1 and r.cycles[1]['direction']==-1
    assert all(e['t']!=e['signal_t'] for e in r.fills)
    assert all(e['contracts']==17 for e in r.fills)
    partial=run_segment(q[:3],Variant('TEST',None),Book())
    assert len(partial.cycles)==0 and partial.residual is not None
    assert len(run_segment(q[:2],Variant('TEST',None),Book()).fills)==0
    damaged=[dict(e) for e in r.fills];damaged[0]['future_fee']+=1
    try:audit_run(q,replace(r,fills=tuple(damaged)),Book())
    except AssertionError:fee_tamper_rejected=True
    else:fee_tamper_rejected=False
    assert fee_tamper_rejected
    values=[100.,120.,110.,90.,105.,125.,115.,80.,130.]
    # The frozen function is initialized at30m, so shift the known synthetic series to that base.
    tr=frozen_drawdowns([INITIAL_F+x-100 for x in values]);np.testing.assert_allclose(tr[:,2],[0,0,10,30,30,30,30,45,45])
    prefix=run_segment(q[:8],Variant('TEST',None),Book())
    assert list(prefix.fills)==[e for e in r.fills if e['t']<=q[7].t.isoformat()]
    return dict(passed=True,synthetic_completed_cycles=2,fee_tamper_rejected=True,prefix_invariance=True,mdd_monotone=True,next_observation_only=True)
