// Node.js: node scale_backtest.js input.json ; input keys candles,funding (Binance USD-M minute arrays and funding records).
const fs=require('fs');
function sim(a,fr,scale,stress){
const fm=new Map(fr.map(x=>[Math.floor(x.fundingTime/60000)*60000,x])),p=a.map(x=>+x[4]),o=a.map(x=>+x[1]),h=a.map(x=>+x[2]),l=a.map(x=>+x[3]),t=a.map(x=>+x[0]),v=a.map(x=>+x[7]),w=[0],n=a.length;
for(let i=1;i<n;i++)w[i]=w[i-1]+Math.abs(p[i]-p[i-1]);
let L=0,S=0,cash=0,fees=0,vol=0,orders=0,anchor=0,at=0,next="start",halt=0,stable=0,base=0,cycles=[],cs=0,dd=0,peak=0,forced=0,paused=0,maxGross=0,maxDiff=0,maxCycle=0,makerVol=0,minEq=0,maxShare=0,miss=0,i=0,slippageCost=0,ledger=[];
const priorVol=()=>Math.max(1,v[Math.max(0,i-1)]);
function sl(q,px){return .0001+(stress?.0005*Math.sqrt(Math.abs(q)*px/priorVol()/.01):0);}
function tr(s,q,px,m){if(!q)return;let buy=s==="L"?q>0:q<0,fee=m?.0002:.0006,slip=m?0:sl(q,px),price=px*(1+(buy?slip:-slip)),val=Math.abs(q)*price;cash+=(buy?-val:val)-val*fee;fees+=val*fee;vol+=val;orders++;slippageCost+=Math.abs(q)*px*slip;if(m)makerVol+=val;if(s==="L")L+=q;else S+=q;maxShare=Math.max(maxShare,val/Math.max(1,v[Math.min(i,n-1)]));ledger.push([t[Math.min(i,n-1)],i===n?"terminal":m?"maker":"taker",s,q,price,val*fee,L,S,cash]);}
const eq=x=>cash+(L-S)*x,net=x=>eq(x)-L*x*(1-(1-sl(L,x))*(1-.0006))-S*x*((1+sl(S,x))*(1+.0006)-1);
function dir(up){if(up&&L>=S)return S<5*scale?["S",scale]:L>scale?["L",-scale]:null;if(!up&&S>=L)return L<5*scale?["L",scale]:S>scale?["S",-scale]:null;return null;}
for(i=0;i<n;i++){
const f=fm.get(t[i]);if(f){const z=-(L-S)*+f.markPrice*+f.fundingRate;cash+=z;ledger.push([t[i],"funding","",0,+f.markPrice,-z,L,S,cash]);}
let acted=false;if(next){let x=next;next=null;if(x==="start"){base=cash;cs=i;tr("L",5*scale,o[i],false);tr("S",5*scale,o[i],false);anchor=o[i];at=i;}else if(x==="exit"){tr("L",-L,o[i],false);tr("S",-S,o[i],false);cycles.push(cash-base);maxCycle=Math.max(maxCycle,i-cs);anchor=o[i];at=i;}else{tr(x[0],x[1],o[i],false);anchor=o[i];at=i;forced++;}acted=true;}
if(!acted&&L&&S&&!halt&&i>=31){let eff=Math.abs(p[i-1]-p[i-31])/Math.max(1e-12,w[i-1]-w[i-31]),drift=Math.abs(p[i-1]/p[i-16]-1);if(L===S&&i-at>=30){anchor=p[i-1];at=i;}const up=Math.ceil(anchor*1.007*100-1e-9)/100,dn=Math.floor(anchor*.993*100+1e-9)/100,U=dir(true),D=dir(false),gate=L!==S||(eff<=.35&&drift<=.015);const extra=stress?.0005:0,u=gate&&U&&up>p[i-1]&&up>o[i]&&h[i]>up*(1+extra)+1e-9,down=gate&&D&&dn<p[i-1]&&dn<o[i]&&l[i]<dn*(1-extra)-1e-9;if(u||down){const upFirst=u&&(!down||p[i-1]<p[i-2]),x=upFirst?U:D,px=upFirst?up:dn;if(stress&&scale*px/priorVol()>.01)miss++;else{tr(x[0],x[1],px,true);anchor=px;at=i;}}}
if(Math.abs(L-S)>scale||L>5*scale||S>5*scale||L<0||S<0)throw Error("inventory");maxGross=Math.max(maxGross,(L+S)*p[i]);maxDiff=Math.max(maxDiff,Math.abs(L-S));const z=eq(p[i]);peak=Math.max(peak,z);dd=Math.max(dd,peak-z);minEq=Math.min(minEq,z);
const shock=(h[i]-l[i])/o[i]>=.008||(i>=5&&Math.abs(p[i]/p[i-5]-1)>=.015);if(shock){halt=5;stable=0;}if(halt){paused++;if(!shock){halt--;stable=(h[i]-l[i])/o[i]<.003?stable+1:0;if(!halt&&stable<3)halt=1;if(!halt){anchor=p[i];at=i;}}}
if(i===n-1)break;if(L&&S&&net(p[i])-base>=4*scale)next="exit";else if(halt){if(L!==S)next=L>S?["S",scale]:["L",scale];}else if(!L&&!S)next="start";
}
let q=p.at(-1),expected=net(q),res=L||S?expected-base:0,open=[L,S];tr("L",-L,q,false);tr("S",-S,q,false);if(Math.abs(cash-expected)>1e-5||Math.abs(cash-cycles.reduce((x,y)=>x+y,0)-res)>1e-5)throw Error("audit");
return {scale,stress,net:cash,vol,fees,orders,cycles:cycles.length,wins:cycles.filter(x=>x>0).length,completed:cycles.reduce((a,b)=>a+b,0),res,open,dd,minEq,maxGross,maxDiff,forced,paused,maxCycle,makerVol,maxShare,miss,slippageCost,rebate50:cash+fees*.5,ledger};
}
const {candles:a,funding:fr}=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
for(const scale of [1,10,50,100,250])for(const stress of [false,true]){const {ledger,...r}=sim(a,fr,scale,stress);console.log(JSON.stringify(r));if(scale===250&&stress)fs.writeFileSync('ledger_250.csv','timestamp_ms,event,side,qty_delta,fill_price,fee_or_negative_funding,long_qty,short_qty,synthetic_cash\n'+ledger.map(z=>z.join(',')).join('\n')+'\n');}
