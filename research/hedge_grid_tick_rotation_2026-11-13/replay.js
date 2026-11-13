// node replay.js trades.json (array of Binance USD-M aggregate trade records)
const fs=require('fs');
function simulate(a,c,extra=0,record=false){
 const q=.1,fee=.0002,tf=.0006,sl=.0001,tick=.01;
 let L=0,S=0,cash=0,base=0,fees=0,vol=0,orders=0,adds=0,reduces=0,cycles=[],dd=0,peak=0,minNet=0,maxLots=0,quote=null,leg=null,closing=false,haltUntil=0,ptr=0,forced=0,pairs=0,good=0,bad=0,maxWait=0,ledger=[],makerVol=0,matchedOpen=0,matchedClose=0;
 const up=x=>Math.ceil(x/tick-1e-8)*tick,dn=x=>Math.floor(x/tick+1e-8)*tick;
 function trade(side,k,p,m,t){if(!k)return;const buy=side==="L"?k>0:k<0,px=p*(1+(m?0:buy?sl:-sl)),v=Math.abs(k)*q*px,f=v*(m?fee:tf);cash+=(buy?-v:v)-f;fees+=f;vol+=v;orders++;if(k>0)adds++;else reduces++;if(m)makerVol+=v;if(side==="L")L+=k;else S+=k;if(record)ledger.push([t,side,k*q,px,m?"maker":"taker",f,L*q,S*q,cash]);}
 const eq=p=>cash+(L-S)*q*p,net=p=>eq(p)-L*q*p*(1-(1-sl)*(1-tf))-S*q*p*((1+sl)*(1+tf)-1);
 function done(t){const g=cash-leg.b;pairs++;if(g>=0)good++;else bad++;if(leg.k>0)matchedOpen++;else matchedClose++;maxWait=Math.max(maxWait,t-leg.t);leg=null;quote=null;}
 function make(p,t){let k=closing&&L&&S?-1:1;quote={sell:up(p+c.gap*tick),buy:dn(p-c.gap*tick),ready:t+100,time:t,k};}
 for(let i=0;i<a.length;i++){const x=a[i],p=+x.p,t=+x.T,v=+x.q,buy=!x.m,sell=x.m;
 while(ptr+1<i&&a[ptr+1].T<=t-60000)ptr++;
 if(t-a[ptr].T>=10000&&Math.abs(p/+a[ptr].p-1)>=.008){haltUntil=t+60000;quote=null;}
 if(leg){
 const hit=t>=leg.ready&&v>=q&&(leg.sell?sell&&p<leg.p-extra*tick-1e-9:buy&&p>leg.p+extra*tick+1e-9);
 if(hit){trade(leg.other,leg.k,leg.p,true,t);done(t);}
 else if(t>=leg.ready&&(t-leg.t>=c.hold*1000||(leg.sell?p/leg.first-1:1-p/leg.first)>=c.stop)){trade(leg.other,leg.k,p,false,t);forced++;done(t);}
 else if(c.reprice&&t-leg.t>=c.reprice*1000&&t-leg.updated>=c.refresh*1000){const newP=leg.sell?dn(p-c.skew*tick):up(p+c.skew*tick);leg.p=leg.sell?Math.max(leg.p,newP):Math.min(leg.p,newP);leg.ready=t+100;leg.updated=t;}
 }else if(quote&&t>=quote.ready&&v>=q&&t>=haltUntil){
 const U=buy&&p>quote.sell+extra*tick+1e-9,D=sell&&p<quote.buy-extra*tick-1e-9;
 if(U||D){const k=quote.k,px=U?quote.sell:quote.buy,b=cash,side=U?(k<0?"L":"S"):(k<0?"S":"L"),other=U?(k<0?"S":"L"):(k<0?"L":"S");
 trade(side,k,px,true,t);const otherP=U?Math.min(quote.buy,dn(px-c.pair*tick)):Math.max(quote.sell,up(px+c.pair*tick));
 leg={other,k,sell:U,first:px,p:otherP,t,b,ready:t+100,updated:t};quote=null;
 }}
 if(closing&&!L&&!S&&!leg){cycles.push(cash-base);base=cash;closing=false;quote=null;}
 if(!leg&&!closing&&L>=c.min&&net(p)-base>=c.target*(L+S)*q*p){closing=true;quote=null;}
 if(!leg&&t>=haltUntil&&(!quote||t-quote.time>=c.refresh*1000))make(p,t);
 if(Math.abs(L-S)>1||L<0||S<0)throw Error("inventory");
 maxLots=Math.max(maxLots,L+S);const e=eq(p);peak=Math.max(peak,e);dd=Math.max(dd,peak-e);minNet=Math.min(minNet,net(p));
 }
 const x=a.at(-1),p=+x.p,expected=net(p),res=expected-base,open=[L*q,S*q];trade("L",-L,p,false,x.T);trade("S",-S,p,false,x.T);if(Math.abs(cash-expected)>1e-7||Math.abs(cash-cycles.reduce((s,x)=>s+x,0)-res)>1e-7)throw Error("audit");
 return {net:cash,vol,orders,adds,reduces,fees,cycles:cycles.length,wins:cycles.filter(x=>x>0).length,completed:cycles.reduce((s,x)=>s+x,0),res,open,dd,minNet,maxLots,pairs,good,bad,forced,maxWait,makerVol,matchedOpen,matchedClose,ledger};
}
const c={"gap":1,"pair":3,"refresh":2,"hold":10,"min":1,"reprice":5,"skew":1,"stop":0.008,"target":0.0001};
const a=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));const {ledger,...r}=simulate(a,c,0,true);console.log(JSON.stringify(r));fs.writeFileSync('ledger.csv','timestamp_ms,side,qty_delta,fill_price,type,fee,long_qty,short_qty,synthetic_cash\n'+ledger.map(x=>x.join(',')).join('\n')+'\n');
