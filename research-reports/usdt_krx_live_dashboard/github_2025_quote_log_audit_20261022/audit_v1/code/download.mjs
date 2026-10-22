import fs from 'node:fs/promises';
import crypto from 'node:crypto';
import path from 'node:path';
const root=path.resolve(import.meta.dirname,'..');
const tree=JSON.parse(await fs.readFile(root+'/metadata/source_tree.json','utf8'));
if(tree.truncated) throw new Error('Truncated source inventory');
const hash=b=>crypto.createHash('sha256').update(b).digest('hex');
const entries=tree.tree.filter(x=>x.type==='blob'&&/^(future|spot)_result_2025-\d{2}-\d{2}\.txt$/.test(x.path));
const inventory=[];
for(let month=1;month<=12;month++) {
 const mm='2025-'+String(month).padStart(2,'0');
 const list=entries.filter(x=>x.path.includes(mm));
 await fs.mkdir(root+'/raw/'+mm,{recursive:true});
 for(const item of list) {
  const dest=root+'/raw/'+mm+'/'+item.path;
  let content=null;let reused=false;let status=0;let attempts=0;
  try {const old=await fs.readFile(dest); if(old.length===item.size&&crypto.createHash('sha1').update(Buffer.concat([Buffer.from('blob '+old.length+'\0'),old])).digest('hex')===item.sha){content=old;reused=true;status=200;}}
  catch(e){if(e.code!=='ENOENT')throw e;}
  while(content===null&&attempts<3) {
   attempts++;
   try { const response=await fetch('https://raw.githubusercontent.com/kimp741/data/'+tree.sha+'/'+item.path,{signal:AbortSignal.timeout(30000)});status=response.status;
    if(response.ok){const b=Buffer.from(await response.arrayBuffer());const blob=crypto.createHash('sha1').update(Buffer.concat([Buffer.from('blob '+b.length+'\0'),b])).digest('hex');if(b.length!==item.size||blob!==item.sha)throw new Error('Source byte/blob mismatch');await fs.writeFile(dest,b,{flag:'wx'});content=b;}
   }catch(e){if(e.message==='Source byte/blob mismatch')throw e;}
   if(content===null)await new Promise(r=>setTimeout(r,attempts*1000));
  }
  inventory.push({path:item.path,month:mm,bytes:item.size,blob_sha:item.sha,source_commit:tree.sha,status,attempts,reused,sha256:content?hash(content):'',downloaded:content!==null});
 }
 await fs.writeFile(root+'/metadata/download_inventory.json',JSON.stringify(inventory,null,2));
 console.log(JSON.stringify({month:mm,files:list.length,downloaded:inventory.filter(x=>x.month===mm&&x.downloaded).length,bytes:list.reduce((s,x)=>s+x.size,0)}));
}
