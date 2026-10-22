var fs=await import('node:fs/promises');
var root='D:/Codex_Research/usdt_krx_live_dashboard/studies/b_path_derivatives_20261022_05';
var out=root+'/publish_payloads/final_path_500_v2';
var parse=t=>{var l=t.trim().split(/\r?\n/),h=l.shift().split(',');return l.map(x=>{var a=x.split(',');if(a.length!==h.length)throw Error('CSV_SCHEMA');return Object.fromEntries(h.map((k,i)=>[k,a[i]]));});};
var monthly=parse(await fs.readFile(out+'/diagnostics/monthly_contribution.csv','utf8'));
var quarterly=parse(await fs.readFile(out+'/diagnostics/quarterly_contribution.csv','utf8'));
var leaders=JSON.parse(await fs.readFile(out+'/best_rules_and_results.json','utf8'));
var selected=Object.fromEntries(Object.values(leaders).map(x=>[x.result.candidate_id,x.result]));
var quote=v=>'"'+String(v??'').replaceAll('"','""')+'"';
var corrected=[];
for(var [id,result]of Object.entries(selected)){
 var legacy=out+'/'+id+'_period_contribution.csv';
 await fs.rename(legacy,out+'/'+id+'_period_contribution_legacy_labels.csv');
 var rows=[];
 for(var [type,source,key]of [['month',monthly,'exit_business_month'],['quarter',quarterly,'exit_business_quarter']]){
  var subset=source.filter(r=>r.candidate_id===id);
  if(subset.reduce((a,r)=>a+Number(r.cycles),0)!==result.cycles)throw Error('PERIOD_COUNT');
  if(Math.abs(subset.reduce((a,r)=>a+Number(r.score_pct),0)-result.score_pct)>1e-8)throw Error('PERIOD_SCORE');
  for(var r of subset)rows.push({candidate_id:id,period_type:type,period:r[key],cycles:r.cycles,score_pct:r.score_pct,net:r.net_krw});
 }
 var fields=['candidate_id','period_type','period','cycles','score_pct','net'];
 await fs.writeFile(legacy,fields.map(quote).join(',')+'\r\n'+rows.map(r=>fields.map(k=>quote(r[k])).join(',')).join('\r\n')+'\r\n',{flag:'wx'});
 corrected.push({candidate_id:id,corrected_file:id+'_period_contribution.csv',preserved_legacy_file:id+'_period_contribution_legacy_labels.csv'});
}
var record=JSON.parse(await fs.readFile(root+'/operations/reporting_date_correction.json','utf8'));
record.status='PASS_REPORT_DATE_CORRECTION';
record.independent_validation=JSON.parse(await fs.readFile(out+'/diagnostics/period_totals_independent_validation.json','utf8'));
record.corrected_selected_files=corrected;
record.authoritative_monthly='diagnostics/monthly_contribution.csv';
record.authoritative_quarterly='diagnostics/quarterly_contribution.csv';
await fs.writeFile(root+'/operations/reporting_date_correction.json',JSON.stringify(record,null,2));
await fs.writeFile(out+'/REPORTING_DATE_CORRECTION.json',JSON.stringify(record,null,2),{flag:'wx'});
await fs.copyFile(root+'/operations/reporting_date_correction.json',out+'/operations/reporting_date_correction.json');
for(var name of ['polish_final_v2.mjs','verify_corrected_periods.py'])await fs.copyFile(root+'/operations/'+name,out+'/operations/'+name);
var report=await fs.readFile(out+'/REPORT_KO.md','utf8');
var note='월·분기 표시 정정: 원장 거래일은 YYYYMMDD였는데 일부 기존 보조 period_contribution.csv에서 앞7자를 ISO월처럼 잘랐습니다. 매매·가격·손익·점수·MDD는 바뀌지 않았고 원본 원장과 배치 게시물도 수정하지 않았습니다. 이 최종본의 diagnostics/monthly_contribution.csv 및 quarterly_contribution.csv가 이전 보조기간 라벨을 대체합니다. 별도 strptime 파서로500조건·20,650사이클·월5000행·분기2000행의 건수·손익·수익률 합계를 검증했습니다. legacy_labels 파일은 추적용이며 월/분기 해석에 사용하지 않습니다.';
report=report.replace('월별 기여(청산 거래일 기준, 미청산평가 별도)\n','월별 기여(청산 거래일 기준, 미청산평가 별도)\n\n'+note+'\n');
await fs.writeFile(out+'/REPORT_KO.md',report);
var readme=await fs.readFile(out+'/README_REPRODUCE_KO.md','utf8');
readme=readme.replace('35개 Python 파일','전략·감사 Python 파일').replace('operations/study_diagnostics.py','operations/study_diagnostics_v2.py');
readme+='\n- 월/분기 라벨은 YYYYMMDD와 ISO를 모두 인식하는 수정본입니다. REPORTING_DATE_CORRECTION.json과 diagnostics/period_totals_independent_validation.json을 확인합니다. 원래 배치의 보조 기간 라벨은 수정하지 않았고 이 최종본의 수정집계가 권위자료입니다. 재현 후 operations/verify_corrected_periods.py로 별도 파서 검산을 실행합니다. 금융모형 재실행은 필요 없습니다.\n';
await fs.writeFile(out+'/README_REPRODUCE_KO.md',readme);
