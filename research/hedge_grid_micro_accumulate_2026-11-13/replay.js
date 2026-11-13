// node replay.js input.json SOLUSDT|SUIUSDT; input: {candles,funding}
const fs=require('fs');
function simulate(a,f,q,tick,c,extra=0){
const p=a.map(x=>+x[4]),o=a.map(x=>+x[1]),h=a.map(x=>+x[2]),l=a.map(x=>+x[3]),t=a.map(x=>+x[0]),n=a.length,w=[0],rv=[0],fm=new Map(f.map(x=>[Math.floor(+x.fundingTime/60000)*60000,x]));
for(let i=1;i<n;i++){w.push(w[i-1]+Math.abs(p[i]-p[i-1]));rv.push(rv[i-1]+(h[i]-l[i])/o[i]);}
const mf=.0002,tf=.0006,sl=.0001;
let L=0,S=0,cash=0,base=0,leg=null,next=null,fees=0,vol=0,orders=0,adds=0,cycles=[],dd=0,peak=0,maxGross=0,maxLots=0,forced=0,paired=0,halt=0,stable=0,minNet=0,maxWait=0,double=0,ledger=[],i=0,closing=false,closePairs=0,openPairs=0;
function tr(side,k,x,m){if(!k)return;let buy=side==="L"?k>0:k<0,px=x*(1+(m?0:buy?sl:-sl)),v=Math.abs(k)*q*px,fee=v*(m?mf:tf);cash+=(buy?-v:v)-fee;fees+=fee;vol+=v;orders++;if(k>0)adds++;if(side==="L")L+=k;else S+=k;ledger.push([t[Math.min(i,n-1)],side,k*q,px,i===n?"terminal":m?"maker":"taker",fee,L*q,S*q,cash]);}
const eq=x=>cash+(L-S)*q*x,net=x=>eq(x)-L*q*x*(1-(1-sl)*(1-tf))-S*q*x*((1+sl)*(1+tf)-1);
const upRound=x=>Math.ceil(x/tick-1e-9)*tick,dnRound=x=>Math.floor(x/tick+1e-9)*tick;
function finish(){paired++;maxWait=Math.max(maxWait,i-leg.i);if(leg.close)closePairs++;else openPairs++;leg=null;}
function hitBuy(lim){return o[i]>lim&&l[i]<lim*(1-extra)-1e-9;}
function hitSell(lim){return o[i]<lim&&h[i]>lim*(1+extra)+1e-9;}
for(i=0;i<n;i++){
const ff=fm.get(t[i]);if(ff){const z=-(L-S)*q*+ff.markPrice*+ff.fundingRate;cash+=z;ledger.push([t[i],"F",0,+ff.markPrice,"funding",-z,L*q,S*q,cash]);}
let acted=false;if(next){if(next==="balance"){tr(leg.otherSide,leg.k,o[i],false);forced++;finish();}else if(next==="undo"){tr(leg.side,-leg.k,o[i],false);forced++;leg=null;}next=null;acted=true;}
if(closing&&!L&&!S&&!leg){cycles.push(cash-base);base=cash;closing=false;}
if(!acted&&i>=31){if(leg){let buy=leg.sell,lim=leg.other;if(c.reprice&&i-leg.i>=c.reprice){let x=buy?dnRound(p[i-1]*(1-c.gap)):upRound(p[i-1]*(1+c.gap));lim=buy?Math.max(lim,x):Math.min(lim,x);}if(buy?hitBuy(lim):hitSell(lim)){tr(leg.otherSide,leg.k,lim,true);finish();}}
else if(!halt){let eff=Math.abs(p[i-1]-p[i-31])/Math.max(1e-12,w[i-1]-w[i-31]),g=Math.max(c.gap,c.adapt*(rv[i-1]-rv[i-31])/30);
if((closing||eff<=c.er)&&Math.abs(p[i-1]/p[i-16]-1)<=.015){let mid=p[i-1],up=upRound(mid*(1+g)),dn=dnRound(mid*(1-g));let U=hitSell(up),D=hitBuy(dn),close=closing&&L>0&&S>0,k=close?-1:1,sellSide=close?"L":"S",buySide=close?"S":"L";
if(U&&D){tr(sellSide,k,up,true);tr(buySide,k,dn,true);paired++;double++;if(close)closePairs++;else openPairs++;}
else if(U||D){let side=U?sellSide:buySide,px=U?up:dn;tr(side,k,px,true);leg={side,otherSide:U?buySide:sellSide,k,sell:U,price:px,other:U?dn:up,i,close};}}}}
if(Math.abs(L-S)>1||L<0||S<0)throw Error("inventory");
maxLots=Math.max(maxLots,L+S);maxGross=Math.max(maxGross,(L+S)*q*p[i]);const e=eq(p[i]);peak=Math.max(peak,e);dd=Math.max(dd,peak-e);minNet=Math.min(minNet,net(p[i]));
let shock=(h[i]-l[i])/o[i]>=.008||(i>=5&&Math.abs(p[i]/p[i-5]-1)>=.015);if(shock){halt=5;stable=0;}if(halt&&!shock){halt--;stable=(h[i]-l[i])/o[i]<.003?stable+1:0;if(!halt&&stable<3)halt=1;}
if(i===n-1)break;if(!closing&&!leg&&L>=c.min&&eq(p[i])-base>=c.target*(L+S)*q*p[i])closing=true;
if(leg){let adv=leg.sell?p[i]/leg.price-1:1-p[i]/leg.price;if(adv>=c.stop||i-leg.i>=c.hold)next=c.undo?"undo":"balance";}
}
const x=p.at(-1),expected=net(x),res=expected-base,open=[L*q,S*q];i=n;tr("L",-L,x,false);tr("S",-S,x,false);if(Math.abs(cash-expected)>1e-7||Math.abs(cash-cycles.reduce((s,x)=>s+x,0)-res)>1e-7)throw Error("audit");
return {net:cash,vol,orders,adds,fees,cycles:cycles.length,wins:cycles.filter(x=>x>0).length,completed:cycles.reduce((s,x)=>s+x,0),res,open,maxLots,maxGross,dd,minNet,forced,paired,maxWait,double,closePairs,openPairs,ledger};
}
const x=[{"symbol":"SOLUSDT","q":0.1,"tick":0.01,"c":{"gap":0.0005,"adapt":2,"er":0.4,"hold":480,"stop":0.015,"min":20,"undo":true,"reprice":0,"target":0.0003},"train":{"net":0.5875319902139609,"vol":1660.1811338000005,"orders":147,"cycles":1,"wins":1,"completed":0.5029838761504575,"res":0.08454811406346385}},{"symbol":"SUIUSDT","q":11.5,"tick":0.0001,"c":{"gap":0.002,"adapt":0,"er":0.4,"hold":480,"stop":0.015,"min":5,"undo":false,"reprice":0,"target":0.0003},"train":{"net":0.2925041553139067,"vol":3119.947859505002,"orders":221,"cycles":6,"wins":6,"completed":1.7852694998319247,"res":-1.4927653445180327}}] .find(x=>x.symbol===process.argv[3]);
const d=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));const {ledger,...r}=simulate(d.candles,d.funding,x.q,x.tick,x.c);console.log(JSON.stringify(r));fs.writeFileSync('ledger.csv','timestamp_ms,side,qty_delta,price,event,fee_or_negative_funding,long_qty,short_qty,synthetic_cash\n'+ledger.map(x=>x.join(',')).join('\n')+'\n');
