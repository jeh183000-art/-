from collections import Counter

import numpy as np

Q=170000.


def verify_book(v,trades,events,residual,ledger,orders,slippage=2.):
    n=len(v[0]);size=3*n
    ds=np.zeros(size);df=np.zeros(size);dp=np.zeros(size);completed=np.zeros(size)
    resets=np.zeros(size);reset_mask=np.zeros(size,dtype=bool)
    spot_resets=np.zeros(size);spot_mask=np.zeros(size,dtype=bool)
    gains={};costs={};entries={};closed=set();kinds=Counter()
    held=0;basis=0.;sid=0
    for e in events:
        kind,i,cid,d=map(int,e[:4]);s,f=e[4:6]
        assert kind in (1,2,3,4,5) and d in (-1,1)
        at=3*i+(2 if kind==5 else 0)
        assert abs(s-(v[15][i] if kind==5 else v[5][i]))<1e-8
        assert abs(f-(v[14][i] if kind==5 else v[10][i] if kind==3 else v[7][i]))<1e-8
        assert int(e[12])==int(v[11][i] if kind==3 else v[3][i])
        sf=s*Q*.0005 if kind in (1,2) else 0.
        ff=17*600+f*Q*.000003157 if kind!=5 else 0.
        ss=s*Q*slippage/10000 if kind in (1,2) else 0.
        fs=f*Q*slippage/10000 if kind!=5 else 0.
        np.testing.assert_allclose(e[8:12],[sf,ff,ss,fs],rtol=0,atol=.001)
        fg=0.
        if kind==1:
            assert held==0 and cid not in entries
            assert i>0 and int(e[13])==i-1 and v[12][i]
            held=d;sid=cid;entries[cid]=(i,d,s,f)
            gains[cid]=0.;costs[cid]=0.
            ds[at]-=d*s*Q;dp[at]+=d
            spot_mask[at]=True;spot_resets[at]=s
        else:
            assert held==d and cid==sid
            if kind in (2,3,5):fg=d*(basis-f)*Q
            if kind==2:
                assert i>entries[cid][0] and int(e[13])==i-1 and v[12][i]
                sg=d*(s-entries[cid][2])*Q
                assert abs(sg-e[6])<.001
                gains[cid]+=sg;ds[at]+=d*s*Q;dp[at]-=d
                held=0;closed.add(cid)
            else:assert abs(e[6])<1e-8
            if kind in (3,4):assert v[9][i]
            if kind==5:assert v[13][i]
        if kind in (1,4,5):
            basis=f;resets[at]=f;reset_mask[at]=True
        assert abs(fg-e[7])<.001
        gains[cid]+=fg;costs[cid]+=sf+ff+ss+fs
        ds[at]-=sf+ss;df[at]+=fg-ff-fs
        kinds[kind]+=1
        if kind==2:completed[at]+=gains[cid]-costs[cid]
    position=np.cumsum(dp)
    assert np.all(np.abs(position)<=1)
    scash=np.cumsum(ds);fcash=30000000.+np.cumsum(df)
    latest=np.maximum.accumulate(np.where(reset_mask,np.arange(size),0))
    bases=resets[latest]
    latest_spot=np.maximum.accumulate(np.where(spot_mask,np.arange(size),0))
    entry_spot=spot_resets[latest_spot]
    sm=np.column_stack([v[5],v[6],np.where(v[13],v[15],v[6])]).ravel()
    fm=np.column_stack([v[7],v[8],np.where(v[13],v[14],v[8])]).ravel()
    fu=position*(bases-fm)*Q
    initial=(position!=0)*fm*Q*np.repeat(v[16],3)
    maintenance=(position!=0)*fm*Q*np.repeat(v[17],3)
    total=scash+position*sm*Q+fcash+fu
    realized=np.cumsum(completed)
    opennet=total-30000000.-realized
    drawdown=np.maximum.accumulate(np.maximum(0,total-30000000.))-(total-30000000.)
    mdd=np.maximum.accumulate(drawdown)
    finance=-scash+np.where(position==-1,(entry_spot+sm)*Q,0)
    expected=np.column_stack([scash,fcash,fu,initial,fcash+fu-maintenance,total,opennet,position,mdd,fcash+fu-initial,np.maximum(0,finance)])
    mask=np.ones((n,3),dtype=bool);mask[:,2]=v[13]
    flat=mask.ravel();actual=ledger.reshape(-1,11)
    assert np.all(np.isnan(actual[~flat]))
    delta=float(np.max(np.abs(actual[flat]-expected[flat])))
    assert delta<.01,('VECTOR_BANK_LEDGER_DIFFERENCE',delta)
    expected_settles=np.flatnonzero(v[13]&(position.reshape(n,3)[:,1]!=0))
    actual_settles=events[events[:,0]==5,1].astype(int)
    assert np.array_equal(expected_settles,actual_settles)
    before=np.concatenate(([0],position.reshape(n,3)[:-1,2]))
    roll_rows=np.flatnonzero(v[9]&(before!=0))
    assert np.array_equal(roll_rows,events[events[:,0]==3,1].astype(int))
    assert np.array_equal(roll_rows,events[events[:,0]==4,1].astype(int))
    assert len(closed)==len(trades)
    for t in trades:
        cid=int(t[17]);assert cid in closed
        np.testing.assert_allclose([t[1],t[4],t[5],t[6]],entries[cid],rtol=0,atol=1e-8)
        assert abs(t[13]-(gains[cid]-costs[cid]))<.001
        assert abs(t[11]+t[12]-costs[cid])<.001
    for order in orders:
        i=int(order[0]);at=3*i
        available=fcash[at]-df[at]
        fee=17*600+v[7][i]*Q*.000003157;slip=v[7][i]*Q*slippage/10000
        required=v[7][i]*Q*v[16][i]
        assert order[3]==17 and order[4] in (0,17)
        assert abs(order[6]-available)<.001
        assert (order[4]==17)==(available-fee-slip>=max(0,required)-1e-7)
    last=3*(n-1)+1
    if residual[0]:
        assert held!=0 and int(residual[0])==sid
        cost=sm[last]*Q*.0005+17*600+fm[last]*Q*.000003157+(sm[last]+fm[last])*Q*slippage/10000
        assert abs(residual[9]-cost)<.001
        assert abs(residual[10]-(opennet[last]-cost))<.001
    else:assert held==0
    return dict(status='PASS_INDEPENDENT_VECTOR_CASH_REPLAY',max_difference_krw=delta,
        settlement_events=len(actual_settles),roll_pairs=len(roll_rows),entry_bundles=kinds[1],completed_cycles=len(closed))
