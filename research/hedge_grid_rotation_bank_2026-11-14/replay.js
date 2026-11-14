// Node.js: node replay.js input.json ; input keys candles, funding. Binance USD-M 1m kline arrays.
const fs=require('fs');
function sim(a,fr,c,extra=0,record=false){
const p=a.map(x=>+x[4]),o=a.map(x=>+x[1]),h=a.map(x=>+x[2]),l=a.map(x=>+x[3]),t=a.map(x=>+x[0]),sum=[0],n=a.length,fm=new Map(fr.map(x=>[Math.floor(+x.fundingTime/60000)*60000,x]));for(const x of p)sum.push(sum.at(-1)+x);
const q=.1,mf=.0002,tf=.0006,sl=.0001,tick=.01;
let L=0,S=0,cash=0,base=0,leg=null,fees=0,vol=0,orders=0,adds=0,closes=0,cycles=[],peak=0,dd=0,minNet=0,maxLots=0,maxGross=0,halt=0,stable=0,pairs=0,week=0,ledger=[],i=0,maxWait=0,openPairs=0,closePairs=0,closing=false,waitBars=0,pairGain=0,maxStuck=0;
const up=x=>Math.ceil(x/tick-1e-9)*tick,dn=x=>Math.floor(x/tick+1e-9)*tick;
function tr(side,k,x,m){if(!k)return;let buy=side==="L"?k>0:k<0,px=x*(1+(m?0:buy?sl:-sl)),v=Math.abs(k)*q*px,f=v*(m?mf:tf);cash+=(buy?-v:v)-f;fees+=f;vol+=v;orders++;if(k>0)adds++;else closes++;if(side==="L")L+=k;else S+=k;if(record)ledger.push([t[Math.min(i,n-1)],side,k*q,px,i===n?"terminal":m?"maker":"taker",f,L*q,S*q,cash]);}
const eq=x=>cash+(L-S)*q*x,net=x=>eq(x)-L*q*x*(1-(1-sl)*(1-tf))-S*q*x*((1+sl)*(1+tf)-1);
function complete(){const g=cash-leg.b;pairGain+=g;pairs++;maxWait=Math.max(maxWait,i-leg.i);if(leg.k>0)openPairs++;else closePairs++;leg=null;}
for(i=0;i<n;i++){
 const f=fm.get(t[i]);if(f){const z=-(L-S)*q*+f.markPrice*+f.fundingRate;cash+=z;if(record)ledger.push([t[i],"F",0,+f.markPrice,"funding",-z,L*q,S*q,cash]);}
 let acted=false;
 if(closing&&L===0&&S===0&&!leg){cycles.push(cash-base);base=cash;closing=false;}
 if(leg){let tp=c.tp;if(c.relax&&i-leg.i>=c.relax)tp=Math.max(.0019,tp*.5);const lim=leg.buy?up(leg.px*(1+tp)):dn(leg.px*(1-tp));if(leg.buy?o[i]<lim&&h[i]>lim*(1+extra)+1e-9:o[i]>lim&&l[i]<lim*(1-extra)-1e-9){tr(leg.other,leg.k,lim,true);complete();acted=true;}else{waitBars++;maxStuck=Math.max(maxStuck,i-leg.i);}}
 if(!acted&&!leg&&!halt&&i>=c.slow+1){const fast=(sum[i]-sum[i-c.fast])/c.fast,slow=(sum[i]-sum[i-c.slow])/c.slow,trend=fast/slow-1,ret=p[i-1]/p[i-6]-1;let sig=0;if(Math.abs(trend)>=c.th&&Math.sign(ret)===Math.sign(trend))sig=Math.sign(trend);
 if(sig){const b=dn(p[i-1]*(1-c.gap)),ss=up(p[i-1]*(1+c.gap)),U=sig<0&&o[i]<ss&&h[i]>ss*(1+extra)+1e-9,D=sig>0&&o[i]>b&&l[i]<b*(1-extra)-1e-9;if(U||D){let buy=D,k=closing&&L>0&&S>0?-1:1,side=buy?(k>0?"L":"S"):(k>0?"S":"L"),px=buy?b:ss,old=cash;tr(side,k,px,true);leg={side,other:side==="L"?"S":"L",buy,k,px,b:old,i};}}}
 if(Math.abs(L-S)>1||L<0||S<0)throw Error("inventory");
 maxLots=Math.max(maxLots,L+S);maxGross=Math.max(maxGross,(L+S)*q*p[i]);const e=eq(p[i]);peak=Math.max(peak,e);dd=Math.max(dd,peak-e);minNet=Math.min(minNet,net(p[i]));
 const shock=(h[i]-l[i])/o[i]>=.008||(i>=5&&Math.abs(p[i]/p[i-5]-1)>=.015);if(shock){halt=5;stable=0;}if(halt&&!shock){halt--;stable=(h[i]-l[i])/o[i]<.003?stable+1:0;if(!halt&&stable<3)halt=1;}
 if(!leg&&!closing&&L>=c.min&&net(p[i])-base>=c.target*(L+S)*q*p[i])closing=true;if(i===10079)week=net(p[i]);
}
const x=p.at(-1),expected=net(x),res=expected-base,open=[L*q,S*q];i=n;tr("L",-L,x,false);tr("S",-S,x,false);if(Math.abs(cash-expected)>1e-7||Math.abs(cash-cycles.reduce((s,x)=>s+x,0)-res)>1e-7)throw Error("audit");
return{net:cash,vol,orders,adds,closes,fees,cycles:cycles.length,wins:cycles.filter(x=>x>0).length,completed:cycles.reduce((s,x)=>s+x,0),res,open,maxLots,maxGross,dd,minNet,pairs,pairGain,openPairs,closePairs,maxWait,maxStuck,waitBars,week,ledger};
}
const c={"fast":15,"slow":60,"th":0.0005,"gap":0.0015,"tp":0.002,"min":5,"relax":0,"target":0.0001};
const {candles:a,funding:fr}=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
for(const extra of [0,.0003]){const {ledger,...r}=sim(a,fr,c,extra,true);console.log(JSON.stringify(r));fs.writeFileSync('ledger_'+extra+'.csv','timestamp_ms,side,qty_delta,price,event,fee_or_negative_funding,long_qty,short_qty,synthetic_cash\n'+ledger.map(x=>x.join(',')).join('\n')+'\n');}
