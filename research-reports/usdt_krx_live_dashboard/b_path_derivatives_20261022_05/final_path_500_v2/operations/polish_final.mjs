var fs=await import('node:fs/promises');
var crypto=await import('node:crypto');
var root='D:/Codex_Research/usdt_krx_live_dashboard/studies/b_path_derivatives_20261022_05';
var out=root+'/publish_payloads/final_path_500_v1';
var leaders=JSON.parse(await fs.readFile(out+'/best_rules_and_results.json','utf8'));
var best=leaders.score_only.result;
var rule=leaders.score_only.rule;
var base=JSON.parse(await fs.readFile(root+'/control_regression/CONTROL_B/result_repaired.json','utf8'));
var plan=JSON.parse(await fs.readFile(out+'/all_500_preregistration.json','utf8'));
var baseRule=JSON.parse(await fs.readFile(root+'/baseline/registry.json','utf8')).B.rule;
var rows=[];
for(var n=1;n<=10;n++){
 var folder=root+'/batches/batch_'+String(n).padStart(4,'0')+'/candidates';
 for(var id of await fs.readdir(folder))rows.push(JSON.parse(await fs.readFile(folder+'/'+id+'/result.json','utf8')));
}
var byid=Object.fromEntries(rows.map(r=>[r.candidate_id,r]));
var canon=o=>JSON.stringify(Object.fromEntries(Object.entries(o).sort(([a],[b])=>a.localeCompare(b))));
var waits=[{id:'BF-09-027',minutes:0,cycles:base.cycles,score:base.score_pct,net:base.net_realized,residual:0}];
for(var c of plan.conditions){
 var r={...c.rule};var minutes=r.cooldown_minutes;delete r.cooldown_minutes;
 if(minutes!==undefined&&canon(r)===canon(baseRule)){
  var q=byid[c.candidate_id];waits.push({id:q.candidate_id,minutes,cycles:q.cycles,score:q.score_pct,net:q.net_realized,residual:q.residual_contracts});
 }
}
var parseCsv=t=>{
 var lines=t.trim().split(/\r?\n/),h=lines.shift().split(',');
 return lines.map(line=>{var cells=line.split(',');if(cells.length!==h.length)throw Error('UNEXPECTED_QUOTED_CSV');return Object.fromEntries(h.map((k,i)=>[k,cells[i]]));});
};
var pathRows=parseCsv(await fs.readFile(out+'/diagnostics/baseline_cycle_path_comparison.csv','utf8'));
var delta=pathRows.find(r=>r.candidate_id===best.candidate_id);
var months=parseCsv(await fs.readFile(out+'/diagnostics/monthly_contribution.csv','utf8')).filter(r=>r.candidate_id===best.candidate_id).sort((a,b)=>a.exit_business_month.localeCompare(b.exit_business_month));
var num=(v,d=0)=>Number(v).toLocaleString('en-US',{minimumFractionDigits:d,maximumFractionDigits:d});
var pct=(v,d=8)=>(Number(v)>=0?'+':'')+Number(v).toFixed(d)+'%';
var report='# B 개선형 경로 파생 500조건 — 최종 결과\n\n';
report+='- 신규500조건을 다섯 방향100조건씩, 50조건 단위로 모두 실행·검산·게시했습니다.\n';
report+='- 기준 BF-09-027의 순손익 익절 +0.7%는 그대로 보존했고 CONTROL의8개 배열이 원본과 정확히 일치했습니다.\n';
report+='- 우선 합격은 '+rows.filter(r=>r.goal_qualified).length+'개이며 최고는 청산 후1시간 대기형 '+best.candidate_id+'입니다.\n';
report+='- 완료사이클 수익률 합계 '+pct(best.score_pct,10)+'로 기준보다 '+Number(best.score_pct-base.score_pct).toFixed(10)+'%p, 순이익 '+num(best.net_realized-base.net_realized,2)+'원 높았습니다.\n';
report+='- 완료42회·잔여0·MDD935만원·초기/유지/롤 자금부족 및 진입거절0으로, 사전등록 합격기준을 충족했습니다.\n';
report+='- 기준과40사이클이 같고2사이클이 달랐습니다. 신규500조건의 실제 경로는369개이며 여러 독립 표본으로 해석하지 않습니다.\n';
report+='- 같은 탐색자료 내의 작은 개선입니다. 역배 차입/비용과 실제17계약 호가체결은 미검증이고 Final OOS는 열지 않았습니다.\n\n';
report+='최고 후보의 정확한 규칙\n\n';
report+='1. 정배: 실제 종가 괴리율이 −0.97%를 하향 통과하면 테더170,000 USDT 롱+달러선물17계약 숏.\n';
report+='2. 역배: +0.85% 상향 통과하면 테더170,000 USDT 숏+달러선물17계약 롱. 차입 가능성/비용 미검증 이론형.\n';
report+='3. 실제 진입 확인 신호봉에서 유리하게0.6%p 회복 또는 두포지션의 비용차감 평가수익률+0.7%에 전량 청산. 같은 봉에서 둘 다 충족되면 동시발동으로 기록.\n';
report+='4. 실제 전량 청산 후60분 동안 진입 신호를 받지 않음. 대기 중 신호는 버리고, 이후 새 임계값 통과만 허용. 보유 중 추가진입/반대진입 없음.\n';
report+='5. 신호 후 다음 연속 관측1분봉 시가를 체결대용값으로 사용. 선물초기현금3천만원, 후보 내 손익누적, 추가입금/계좌자동이체 없음. 증거금 부족17계약은 전량거절.\n\n';
report+='|항목|기준 B|최고 후보|\n|---|---:|---:|\n';
for(var [label,key,d]of [['수익률 합계(%)','score_pct',10],['완료 사이클','cycles',0],['승률(%)','win_rate_pct',2],['실현 순이익(원)','net_realized',2],['MDD(원)','mdd_krw',2],['최대 평가손실(원)','maximum_open_loss_krw',2],['평균 보유(분)','average_hold_minutes',2],['최장 보유(분)','longest_hold_minutes',0],['잔여 계약','residual_contracts',0],['최소 초기증거금 여유(원)','minimum_initial_headroom_krw',2],['최소 유지증거금 여유(원)','minimum_maintenance_headroom_krw',2],['현물 조달 필요액 모형 추정(원)','spot_financing_proxy_krw',0]]){
 report+='|'+label+'|'+num(base[key],d)+'|'+num(best[key],d)+'|\n';
}
report+='|PF|완료손실 없음(∞ 상태)|완료손실 없음(∞ 상태)|\n';
report+='\n최고 후보의 평균/최장 보유는 '+(best.average_hold_minutes/1440).toFixed(5)+'/'+(best.longest_hold_minutes/1440).toFixed(5)+'일입니다. 장기 보유 위험은 줄지 않았습니다. 평가손실은 원엔진의 기지급 비용 반영 기준이며, 잔여평가는 예상청산비용까지 차감합니다.\n\n';
report+='청산 신호: 회복 단독 '+best.exit_gap_only+'회, 순손익 익절 단독 '+best.exit_profit_only+'회, 동시 '+best.exit_gap_profit_both+'회. 원본 +0.7%를 없애거나 바꾸지는 않았습니다. 최고 후보의 원화 수수료 '+num(best.fees_krw,2)+'원과 슬리피지 '+num(best.slippage_krw,2)+'원은 순이익에 차감됐고 롤오버 비용도 포함됩니다.\n\n';
report+='대기시간 인접 비교(다른 규칙 동일)\n\n|후보|대기 분|완료|수익률 합계|순이익 원|잔여|\n|---|---:|---:|---:|---:|---:|\n';
for(var r of waits.sort((a,b)=>a.minutes-b.minutes))report+='|'+[r.id,r.minutes,r.cycles,pct(r.score,10),num(r.net,2),r.residual].join('|')+'|\n';
report+='\n기준과 동일한 실제 진입·청산 구간 '+delta.identical_parent_cycles+'회, 바뀐 신규 구간 '+delta.new_unmatched_cycles+'회, 대체된 기준 구간 '+delta.parent_unmatched_cycles+'회입니다. 바뀐 구간들의 수익률 합계차 '+Number(delta.score_change_pp).toFixed(10)+'%p가 전체 개선을 설명합니다. 표본 두사이클의 개선이어서60분이 다른 기간에도 우수하다고 결론내릴 수 없습니다.\n\n';
report+='같은 양방향 포트폴리오에서 정배 기여 '+pct(best.long_score_pct,10)+'('+best.long_cycles+'회), 역배 기여 '+pct(best.reverse_score_pct,10)+'('+best.reverse_cycles+'회)입니다. 전용 방향 전략을 별도로 다시 실행한 값은 아닙니다.\n\n';
report+='월별 기여(청산 거래일 기준, 미청산평가 별도)\n\n|월|완료|수익률 합계|순이익 원|\n|---|---:|---:|---:|\n';
for(var r of months)report+='|'+[r.exit_business_month+(r.exit_business_month==='2026-10'?' (15일까지)':''),r.cycles,pct(r.score_pct,8),num(r.net_krw,2)].join('|')+'|\n';
report+='\n닫힌 거래가 없는 달의0은 성과집계이며 가격 보간이 아닙니다. 최고후보의 상위3/5개 양의 사이클 수익률 비중은 '+best.top3_positive_return_share_pct.toFixed(4)+'%/'+best.top5_positive_return_share_pct.toFixed(4)+'%입니다. 순이익을 분모로 한 집중도와 이웃조건 전체는 diagnostics/에 있습니다.\n\n';
report+='다섯 가설 방향별 최고(기존 검산기 적격·완료 사이클 존재)\n\n|가설|후보|완료|수익률 합계|MDD 원|잔여|\n|---|---|---:|---:|---:|---:|\n';
var labels={1:'방향별 진입·회복',2:'청산 조건 효과',3:'확인·재진입 대기',4:'과거 시장상태',5:'보유·손실 위험 제한'};
for(var category=1;category<=5;category++){
 var ids=new Set(plan.conditions.filter(c=>c.category===category).map(c=>c.candidate_id));
 var r=rows.filter(x=>ids.has(x.candidate_id)&&x.feasible&&x.cycles).sort((a,b)=>b.score_pct-a.score_pct)[0];
 report+='|'+[labels[category],r.candidate_id,r.cycles,pct(r.score_pct,8),num(r.mdd_krw,2),r.residual_contracts].join('|')+'|\n';
}
var old=await fs.readFile(out+'/REPORT_KO.md','utf8');
var tail=old.slice(old.indexOf('|구분|'));
report+='\nその他 비교와 방법·한계\n\n'.replace('その他','추가')+tail;
report+='\n최고 후보의 작은 비압축 원장: '+best.candidate_id+'_cycles.csv / '+best.candidate_id+'_fills.csv / '+best.candidate_id+'_orders.csv / '+best.candidate_id+'_cash_margin_snapshot.csv. 현금·증거금 CSV는 모든 현금 변동 및 선택한 위험 극값을 담은211행 스냅샷입니다. 전체369,010개 평가시점 원장은 각 배치의 손실 없는 NPZ/TAR에 그대로 있습니다.\n';
await fs.writeFile(out+'/REPORT_KO.md',report);
var counts={new_conditions:500,goal_qualified:rows.filter(r=>r.goal_qualified).length,zero_completed:rows.filter(r=>!r.cycles).length,ineligible:rows.filter(r=>!r.feasible).length,open_residual_conditions:rows.filter(r=>r.residual_contracts).length,unique_execution_paths:369,score_tolerance_pp:1e-8,baseline_profit_target_pct:.7,best_id:best.candidate_id,score_delta_B_pp:best.score_pct-base.score_pct,net_delta_B_krw:best.net_realized-base.net_realized,source_raw_status:'INPUT_NOT_REMOTELY_REPRODUCIBLE',final_oos_access:false};
await fs.writeFile(out+'/final_summary.json',JSON.stringify(counts,null,2),{flag:'wx'});
await fs.writeFile(out+'/README_REPRODUCE_KO.md',
'# 재현·원격 검증 자료 안내\n\n'+
'- 모든 전략 코드는 strategy_code_ref.json의 고정 커밋 f7f6e40b21dd30231f426a735687a7904f72cce1에 있습니다. 공통 검산기·통계·입력 로더의 정확한8a33… 경로와SHA는 external_dependencies.json에 있습니다.\n'+
'- all_500_preregistration.json에 전체순서·조건·코드 해시가 있습니다. 22개 전략/검산/기준 코드에 변경이 없는지 registration_audit에서 확인했습니다. 원본 B의0.7%는 그대로입니다.\n'+
'- Python3.12.0 / NumPy2.2.6 / Numba0.61.2 / pandas3.0.1을 보존했습니다. 코드와 운영후처리32개 Python 파일은 no-excuse 검사도 통과했습니다. 기존 실행환경에 패키지를 새로 설치하지 않았습니다.\n'+
'- 데이터 원본은 D: 승인 탐색 사본에만 있습니다. source/margin SHA는 provenance.json에 있으며 INPUT_NOT_REMOTELY_REPRODUCIBLE입니다. 원시가격부터 재생하려면 같은 D: 입력이 필요합니다. 보호 Final OOS는 읽거나 게시하지 않았습니다.\n'+
'- batch_publication_index.csv의10개 불변 커밋에서 manifest.csv, archive_parts.json, archive_inventory.csv와 full_ledgers.tar.partNNN을 받습니다. 순서대로 연결한 TAR의 SHA를 검사하고 각멤버SHA 및NPZ CRC를 확인합니다. 후보당10파일의 전체원장을 보존했습니다.\n'+
'- 원장원본은 NPZ(전체 OPEN/CLOSE/SETTLEMENT 현금·증거금·평가)와 CSV.gz(체결·사이클·주문), exit_attribution.csv입니다. ledger_schema.json의 행/열 정의를 따릅니다. 최고후보의 비압축 CSV와211행 현금변동/위험극값 스냅샷은 이 폴더에 별도로 제공합니다. 스냅샷은 전체 분별원장을 대체하지 않습니다.\n'+
'- operations/verify_actual_mdd.py, verify_registry_final.py, verify_all_metrics.py, study_diagnostics.py는 저장된 원장 대조만 합니다. code/bootstrap.py를 통해 새D: 검증 사본에서 실행하며 이미생성된 감사폴더를 덮어쓰지 않습니다. 연구 runner를 다시 실행할 필요가 없습니다.\n'+
'- operations/codex_orchestration_v2.json은 Codex 도구 환경에서 단일워커·중복방지·게시/재조회 검증 순서를 복구하는 참조입니다. 일시적 GitHub 통신 오류만 같은 게시물로최대3회재시도하고 금융/해시 불일치는즉시중단합니다. Gateway나 수집기를 시작하지 않습니다.\n'+
'- batch 내부 checkpoint는 게시 전 동결시점 상태이며 실제게시검증은 batch_publication_index.csv와 로컬 publication/*_verified.json으로 확인합니다. CONTROL1회는신규500개에포함하지않았습니다. 합성테스트도 실제시장거래로집계하지않았습니다.\n',
{flag:'wx'});
