// Node.js: node backtest.js input.json; input keys candles, funding. Candle bars are Binance USD-M kline arrays.
const fs=require('fs');
function test(a,fr,makerFee=.0002,fillExtra=0,drop=0){
 const fm=new Map(fr.map(x=>[Math.floor(+x.fundingTime/60000)*60000,x])),p=a.map(x=>+x[4]),o=a.map(x=>+x[1]),h=a.map(x=>+x[2]),l=a.map(x=>+x[3]),t=a.map(x=>+x[0]),n=p.length;let walk=[0];for(let i=1;i<n;i++)walk[i]=walk[i-1]+Math.abs(p[i]-p[i-1]);
 let L=0,S=0,cash=0,fees=0,vol=0,orders=0,anchor=0,anchorAt=0,pending="start",halt=0,stable=0,base=0,cycles=[],cs=0,dd=0,peak=0,forced=0,stops=0,paused=0,funding=0,limit=0,maxDiff=0,maxHold=0,lastBalance=0,maxGross=0,weekMark=0,miss=0,i=0,ledger=[];
 function tr(side,d,price,maker){if(!d)return;const buy=side==="L"?d>0:d<0,sl=maker?0:.0001,fee=maker?makerFee:.0006,px=price*(1+(buy?sl:-sl)),v=Math.abs(d)*px;cash+=(buy?-v:v)-v*fee;fees+=v*fee;vol+=v;orders++;if(maker)limit++;if(side==="L")L+=d;else S+=d;ledger.push([t[Math.min(i,n-1)],i===n?"terminal":maker?"maker":"taker",side,d,px,v*fee,L,S,cash]);}
 const eq=x=>cash+(L-S)*x, net=x=>eq(x)-L*x*(1-(1-.0001)*(1-.0006))-S*x*((1+.0001)*(1+.0006)-1);
 function dir(up){if(up&&L>=S)return S<10?["S",1]:L>1?["L",-1]:null;if(!up&&S>=L)return L<10?["L",1]:S>1?["S",-1]:null;return null;}
 for(i=0;i<n;i++){
  const f=fm.get(t[i]);if(f){const z=-(L-S)*+f.markPrice*+f.fundingRate;cash+=z;funding+=z;ledger.push([t[i],"funding","",0,+f.markPrice,-z,L,S,cash]);}
  let acted=false;
  if(pending){const x=pending;pending=null;if(x==="start"){base=cash;cs=i;tr("L",5,o[i],false);tr("S",5,o[i],false);anchor=o[i];anchorAt=i;acted=true;}else if(x==="exit"){tr("L",-L,o[i],false);tr("S",-S,o[i],false);cycles.push({gain:cash-base,min:i-cs});anchor=o[i];anchorAt=i;acted=true;}else{tr(x[0],x[1],o[i],false);anchor=o[i];anchorAt=i;acted=true;forced++;}}
  if(!acted&&L&&S&&!halt&&i>=31){
   const er=Math.abs(p[i-1]-p[i-31])/Math.max(1e-12,walk[i-1]-walk[i-31]);const drift=Math.abs(p[i-1]/p[i-16]-1);
   if(L===S&&i-anchorAt>=30){anchor=p[i-1];anchorAt=i;}
   const up=Math.ceil(anchor*1.01*100-1e-9)/100,dn=Math.floor(anchor*.99*100+1e-9)/100,U=dir(true),D=dir(false);
   const gate=L!==S||(er<=.35&&drift<=.015);
   const u=gate&&U&&up>p[i-1]&&h[i]>up*(1+fillExtra)+1e-9,d=gate&&D&&dn<p[i-1]&&l[i]<dn*(1-fillExtra)-1e-9;
   if(u||d){if(drop&&((i*7919+37)%100)<drop)miss++;else{const isUp=u&&(!d||p[i-1]<p[i-2]),x=isUp?U:D,px=isUp?up:dn;tr(x[0],x[1],px,true);anchor=px;anchorAt=i;}}
  }
  if(Math.abs(L-S)>1||L>10||S>10||L<0||S<0)throw Error("balance");maxDiff=Math.max(maxDiff,Math.abs(L-S));maxGross=Math.max(maxGross,(L+S)*p[i]);if(L===S){lastBalance=i;}else maxHold=Math.max(maxHold,i-lastBalance);const e=eq(p[i]);peak=Math.max(peak,e);dd=Math.max(dd,peak-e);if(i===10079)weekMark=net(p[i]);
  const shock=(h[i]-l[i])/o[i]>=.008||(i>=5&&Math.abs(p[i]/p[i-5]-1)>=.015);
  if(shock){if(!halt)stops++;halt=5;stable=0;}if(halt){paused++;if(!shock){halt--;stable=(h[i]-l[i])/o[i]<.003?stable+1:0;if(!halt&&stable<3)halt=1;if(!halt){anchor=p[i];anchorAt=i;}}}
  if(i===n-1)break;
  if(L&&S&&net(p[i])-base>=2){pending="exit";continue;}
  if(halt){if(L!==S)pending=L>S?["S",1]:["L",1];continue;}
  if(!L&&!S)pending="start";
 }
 const q=p.at(-1),expected=net(q),res=L||S?expected-base:0,open=[L,S];i=n;tr("L",-L,q,false);tr("S",-S,q,false);if(Math.abs(cash-expected)>1e-7||Math.abs(cash-cycles.reduce((z,x)=>z+x.gain,0)-res)>1e-7)throw Error("audit");
 return {makerFee,fillExtra,drop,net:cash,weekMark,secondChange:cash-weekMark,vol,fees,orders,cycles:cycles.length,wins:cycles.filter(x=>x.gain>0).length,completed:cycles.reduce((z,x)=>z+x.gain,0),res,open,dd,rebate50:cash+fees*.5,forced,stops,paused,maxDiff,maxHold,maxGross,limit,funding,maxCycle:Math.max(0,...cycles.map(x=>x.min)),miss,ledger};
}
const {candles:a,funding:fr}=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
for(const args of [[],[.0003],[.0002,.0002],[.0002,.0005],[.0002,0,10],[.0002,0,20]]){const {ledger,...r}=test(a,fr,...args);console.log(JSON.stringify(r));if(!args.length)fs.writeFileSync('ledger.csv','timestamp_ms,event,side,qty_delta,fill_price,fee_or_negative_funding,long_qty,short_qty,synthetic_cash\n'+ledger.map(z=>z.join(',')).join('\n')+'\n');}
