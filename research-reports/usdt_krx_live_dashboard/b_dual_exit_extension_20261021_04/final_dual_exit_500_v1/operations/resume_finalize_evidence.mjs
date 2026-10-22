var fs = await import('node:fs/promises');
var crypto = await import('node:crypto');
var root = 'D:/Codex_Research/usdt_krx_live_dashboard/studies/b_dual_exit_extension_20261021_04';
var out = root + '/publish_payloads/final_dual_exit_500_v1';
var checkRows = [];
for (var batch = 1; batch <= 8; batch++) {
  var batchName = 'batch_' + String(batch).padStart(4, '0');
  var inventoryFile = root + '/publish_payloads/' + batchName + '_results_v1/archive_inventory.csv';
  var lines = (await fs.readFile(inventoryFile, 'utf8')).trim().split(/\r?\n/);
  if (lines.shift() !== 'bytes,path,sha256' || lines.length !== 450) throw new Error('INVENTORY_INVALID');
  for (var line of lines) {
    var cells = line.split(',');
    if (cells.length !== 3 || !/^candidates\/BD-\d{2}-\d{3}\/[a-z_.0-9]+$/.test(cells[1])) throw new Error('INVENTORY_PATH_INVALID');
    var bytes = await fs.readFile(root + '/batches/' + batchName + '/' + cells[1]);
    var digest = crypto.createHash('sha256').update(bytes).digest('hex');
    if (bytes.length !== Number(cells[0]) || digest !== cells[2]) throw new Error('OLD_400_FILE_CHANGED:' + cells[1]);
    checkRows.push({batch, path:cells[1], bytes:bytes.length, sha256:digest, status:'PASS'});
  }
}
var quote = x => '"' + String(x ?? '').replaceAll('"','""') + '"';
var csvText = (rows, headers) => headers.map(quote).join(',') + '\r\n' +
  rows.map(r => headers.map(k => quote(r[k])).join(',')).join('\r\n') + '\r\n';
await fs.writeFile(out + '/old_400_preservation.csv', csvText(checkRows,['batch','path','bytes','sha256','status']), {flag:'wx'});
await fs.writeFile(out + '/resume_verification.json', JSON.stringify({
 status:'PASS', base_commit:'7540f012a0dce2c5dc98a82aef40bd6f98a0344e',
 existing_conditions_recomputed:0, existing_conditions:400, preserved_candidate_files:checkRows.length,
 comparison:'bytes and SHA256 against original published batch archive member inventories',
 new_executed_batches:[9,10],new_executed_conditions:100,final_total:500,
 original_B_files_preserved:9, protected_oos_access:false,
 gateway_collectors_or_schedules_changed:false
},null,2),{flag:'wx'});
await fs.copyFile(root + '/RESUME_0400_TO_0500.json', out + '/RESUME_0400_TO_0500.json');
var allRows = [];
for (var batch = 1; batch <= 10; batch++) {
  var folder = root + '/batches/batch_' + String(batch).padStart(4, '0') + '/candidates';
  for (var cid of (await fs.readdir(folder)).sort()) allRows.push(JSON.parse(await fs.readFile(folder+'/'+cid+'/result.json','utf8')));
}
if (allRows.length !== 500 || new Set(allRows.map(x=>x.candidate_id)).size !== 500) throw new Error('CONDITION_COUNT_INVALID');
var ordered = [...allRows].sort((a,b) => Number(b.cycles>0)-Number(a.cycles>0) || b.score_pct-a.score_pct || a.candidate_id.localeCompare(b.candidate_id));
var eligible = ordered.filter(x=>x.feasible && x.cycles>0);
var eligibleRank = new Map(eligible.map((x,i)=>[x.candidate_id,i+1]));
var fullRanking = ordered.map((r,i)=>({rank_all_completed:r.cycles>0?i+1:'',rank_eligible:eligibleRank.get(r.candidate_id)??'',...r}));
await fs.writeFile(out+'/ranking_all_500.csv',csvText(fullRanking,['rank_all_completed','rank_eligible',...Object.keys(allRows[0])]),{flag:'wx'});
var summary = {
 conditions:500,completed_cycle_zero:allRows.filter(x=>!x.cycles).length,
 eligible_completed:eligible.length,ineligible:allRows.filter(x=>!x.feasible).length,
 goal_qualified:allRows.filter(x=>x.goal_qualified).length,score_strictly_above_B:allRows.filter(x=>x.score_pct>16.7054302006977).length,
 baseline_score_pct:16.7054302006977,top20:eligible.slice(0,20),
 no_residual_best:eligible.find(x=>!x.residual_contracts),
 min42_best:eligible.find(x=>x.cycles>=42),
 margin_free_best:eligible.find(x=>x.margin_shortage_free),
 open_residual_conditions:allRows.filter(x=>x.residual_contracts>0).length
};
await fs.writeFile(out+'/final_ranking_summary.json',JSON.stringify(summary,null,2),{flag:'wx'});
var report = '\n\n재개 작업과 최종 순위\n\n';
report += '기준 커밋 7540f012a0dce2c5dc98a82aef40bd6f98a0344e의 완료400조건은 재계산하지 않았습니다. 기존 후보 파일3600개를 원래 게시된 원장 인벤토리의 바이트·SHA-256과 대조해 모두 동일함을 확인했습니다. 9·10배치 신규100조건만 실행했습니다.\n\n';
report += '신규500조건 중 기준 B보다 높은 점수를 기록한 후보는 '+summary.score_strictly_above_B+'개, 모든 합격 목표를 충족한 후보는 '+summary.goal_qualified+'개입니다. 최고는 BD-04-041로 기준 B와 정확히 동률이며 성과 개선에 실패했습니다. B의 원본과 조건은 변경하지 않았습니다.\n\n';
report += '아래는 기존 검산기 feasible 요건을 충족하고 완료사이클이 있는 후보의 순위입니다. 유지/초기증거금 부족 및 진입거절0인 더 엄격한 순위는 top20_margin_shortage_free.csv로 별도 제공합니다. 전체500개 점수순(부적격 포함)과 eligible 순위는 ranking_all_500.csv에 함께 기록했습니다. 완료0건은 순위에서 제외됩니다.\n\n';
report += '|순위|후보|완료|비용차감 수익률 합계%|실현 순이익 원|MDD 원|잔여 계약|\n|---:|---|---:|---:|---:|---:|---:|\n';
for (var [i,r] of eligible.slice(0,20).entries()) report += '|'+[i+1,r.candidate_id,r.cycles,r.score_pct.toFixed(10),r.net_realized.toFixed(2),r.mdd_krw.toFixed(2),r.residual_contracts].join('|')+'|\n';
report += '\n9배치 결과 SHA: 084756b40f53817b54979c9ada76928d27cbf403, 10배치 결과 SHA: 86fd1c501fbdec3fef0b5df4075a8bed0fb137fd. 각 결과38개 파일의 원격 바이트와SHA-256을 재조회해 검증했습니다. 최종 집계는 전략 재시뮬레이션이 아닌 저장된 결과·체결·사이클·계좌 원장 대조입니다.\n';
await fs.appendFile(out+'/REPORT_KO.md',report);
await fs.writeFile(out+'/README_REPRODUCE_KO.md',
'# 저장 자료 검증 방법\n\n'+
'1. strategy_code_ref.json의 고정 커밋에서 신규 연구 코드13개와 기존 공통 엔진·검산기·입력 로더를 받습니다. 설정과 비용은 변경하지 않습니다.\n'+
'2. batch_publication_index.csv의 각 불변 커밋에서 manifest와 archive_inventory, ledger.part*.bin 및 직접CSV를 받습니다. 배치 폴더의 verify_archive.py로 연결 TAR의 모든 멤버 SHA와 NPZ CRC를 검사합니다. 분할 파일 이름과 정확한 연결 순서는 각 배치의 archive 관련 JSON/CSV를 따릅니다.\n'+
'3. 원장은 batch_0001..0010/candidates/<ID>/에 복원할 수 있습니다. 각 후보의 cycles·fills·orders와 full_account_ledger, numeric_result, audit, residual, period_contribution, result를 보존합니다.\n'+
'4. 새 D: 검증 복사본에서 code/bootstrap.py를 통해 operations/verify_actual_mdd.py, verify_registrations.py, verify_all_metrics.py를 실행합니다. 이미 있는 감사 폴더는 덮어쓰지 않도록 새 작업 사본을 사용합니다. 전략 runner를 재실행할 필요가 없습니다.\n'+
'5. operations/resume_finalize_evidence.mjs는 기존400조건의 게시 인벤토리와 파일보존을 대조하고 저장된500조건을 점수순으로 정렬한 이번 후처리 코드입니다. 이미 생성된 산출물은 덮어쓰지 않습니다.\n'+
'6. 원시 가격자료는 D: 공통 경로의 승인 탐색 사본에만 있습니다. provenance.json의 SHA로 식별하며 INPUT_NOT_REMOTELY_REPRODUCIBLE입니다. 원시 가격부터 완전 재현하려면 해당D: 입력이 필요합니다. 보호 Final OOS나 인증정보를 게시하지 않았습니다.\n'+
'7. 순위는 완료사이클별 비용차감 순손익 / 최초 현물진입 명목금액 절대값 *100의 반올림 전 단순합입니다. 미청산은 별도이며 강제종료 가정 점수도 결과CSV에서 확인할 수 있습니다.\n',
{flag:'wx'});
