# /// script
# requires-python = "==3.12.0"
# dependencies = ["numpy==2.2.6"]
# ///
# Run: python -B code/bootstrap.py ../operations/finalize_v2.py
import csv
import gzip
import hashlib
import importlib.metadata
import json
import shutil
from pathlib import Path

import numpy as np
from runner import ROOT, SOURCE_HASH, MARGIN_HASH, table, write_json
from package import manifest

PRIOR=ROOT.parent/'lump17_sweep_20261021_01'


def main():
    out=ROOT/'publish_payloads/final_1000_comparison_v2'
    assert not out.exists();out.mkdir(parents=True)
    old=[json.loads(p.read_text()) for p in sorted((PRIOR/'batches').glob('batch_*/candidates/*/result.json'))]
    new=[json.loads(p.read_text()) for p in sorted((ROOT/'batches').glob('batch_*/candidates/*/result.json'))]
    assert len(old)==len(new)==500
    rules={}
    for root in (PRIOR,ROOT):
        for p in sorted((root/'preregistration').glob('batch_*.json')):
            for r in json.loads(p.read_text())['conditions']:rules[r['candidate_id']]=r['rule']
    rows=[dict(r,study='ORIGINAL_500') for r in old]+[dict(r,study='NEW_EXTENSION_500') for r in new]
    assert len({r['candidate_id'] for r in rows})==1000
    table(out/'results_all_1000.csv',rows)
    table(out/'results_new_500.csv',new)
    write_json(out/'settings_all_1000.json',rules)
    receipts=[json.loads((ROOT/'publication'/f'batch_{i:04d}_results_verified.json').read_text()) for i in range(1,11)]
    assert all(r['status']=='PUBLISHED_VERIFIED' for r in receipts)
    write_json(out/'verified_batch_commits.json',receipts)
    batch_best=[dict(batch=i,**json.loads((ROOT/'publish_payloads'/f'batch_{i:04d}_results_v1/publication_summary.json').read_text())['batch_best']) for i in range(1,11)]
    table(out/'batch_best_summary.csv',batch_best)
    write_json(out/'batch_best_rules.json',{r['candidate_id']:rules[r['candidate_id']] for r in batch_best})
    eligible=sorted([r for r in rows if r['feasible'] and r['cycles']>0],key=lambda r:r['score_pct'],reverse=True)
    groups=dict(overall=eligible,min10=[r for r in eligible if r['cycles']>=10],
        no_residual=[r for r in eligible if r['residual_contracts']==0],
        long_only=[r for r in eligible if rules[r['candidate_id']].get('allowed_direction',0)==1],
        reverse_only=[r for r in eligible if rules[r['candidate_id']].get('allowed_direction',0)==-1])
    leaders={};summary=[]
    for name,items in groups.items():
        table(out/f'top20_{name}.csv',items[:20])
        if items:
            r=items[0];leaders[name]=dict(result=r,rule=rules[r['candidate_id']])
            summary.append(dict(category=name,**r))
    table(out/'best_categories.csv',summary)
    table(out/'zero_completed.csv',[r for r in rows if not r['cycles']])
    table(out/'account_ineligible.csv',[r for r in rows if not r['feasible']])
    table(out/'open_residuals.csv',[r for r in rows if r['residual_contracts']])
    table(out/'ranking_unrestricted_paper.csv',sorted([r for r in rows if r['cycles']],key=lambda r:r['score_pct'],reverse=True)[:20])
    audits=[]
    for p in sorted((ROOT/'batches').glob('batch_*/candidates/*/audit.json')):
        record=json.loads(p.read_text());proof=record['vector_replay']
        assert record['status']=='PASS' and proof['cumulative_mdd_nondecreasing']
        audits.append(dict(candidate_id=p.parent.name,account_audit_status=record['status'],**proof))
    assert len(audits)==500
    table(out/'validation_all_new_500.csv',audits)
    # Detailed already-calculated ledgers for category winners; never resimulate old candidates.
    winners={x['result']['candidate_id'] for x in leaders.values()}
    for cid in winners:
        source=(PRIOR if cid.startswith('L17') else ROOT)/'batches'/f'batch_{int(cid.split("-")[1]):04d}'/'candidates'/cid
        for name in ('cycles','fills','orders'):
            with gzip.open(source/f'{name}.csv.gz','rb') as stream,(out/f'{cid}_{name}.csv').open('xb') as target:shutil.copyfileobj(stream,target)
        shutil.copy2(source/'period_contribution.csv',out/f'{cid}_period_contribution.csv')
        # Supplemental final close assumption, charged exit costs; not a verified historical fill.
        account=np.load(source/'full_account_ledger.npz')['ledger'];raw=np.load(source/'numeric_result.npz')
        residual=raw['residual'];trace=account[:,:,5];terminal_net=float(account[-1,1,5]-30000000.-residual[9])
        forced_mdd=max(float(np.nanmax(account[:,:,8])),max(30000000.,float(np.nanmax(trace)))-(terminal_net+30000000.))
        leaders[next(k for k,x in leaders.items() if x['result']['candidate_id']==cid)]['terminal_assumed_mdd_krw']=forced_mdd
    write_json(out/'best_rules_and_results.json',leaders)
    costs=[{k:r[k] for k in ('candidate_id','fees_krw','slippage_krw','borrow_unverified')} for r in new]
    table(out/'costs.csv',costs)
    shutil.copy2(ROOT/'publication/code_ref.json',out/'strategy_code_ref.json')
    shutil.copy2(ROOT/'drawdown_tests_v2.json',out/'drawdown_tests_v2.json')
    shutil.copytree(ROOT/'anchor_audit_v2',out/'anchor_audit')
    shutil.copytree(ROOT/'operations',out/'operations',ignore=shutil.ignore_patterns('__pycache__','*.out','*.err','finalize.py'))
    actual_mdd=json.loads((ROOT/'actual_mdd_audit/validation.json').read_text())
    assert actual_mdd['status']=='PASS_ACTUAL_RECORDED_MDD_NONDECREASING'
    shutil.copytree(ROOT/'actual_mdd_audit',out/'actual_mdd_audit')
    (out/'code').mkdir()
    loader=ROOT.parents[1]/'shared/approved_20261016_01/paper_engine.py'
    assert hashlib.sha256(loader.read_bytes()).hexdigest()=='668896092b40c87c30cae77624cc26b95afef51af7154c5cc2d225dfdf2cfa8b'
    shutil.copy2(loader,out/'code/input_loader_frozen.py')
    write_json(out/'dependency_versions.json',{name:importlib.metadata.version(name) for name in ('numpy','numba','llvmlite','pandas')})
    write_json(out/'feature_source_reference.json',dict(commit='d64eb691b0cf084f6748df6abdab5f4c9d8e0027',path='research-reports/usdt_krx_live_dashboard/single_set_hypotheses_20261020_01/preregistration/code/signals.py',sha256='b7d59904f3d70543b5e16e4a8479c467ac16710658737cac25264559314d8937'))
    write_json(out/'settings.json',dict(contracts=17,spot_quantity=170000,futures_cash=30000000,additional_entries=False,
        simultaneous_opposite=False,external_deposits=False,slippage_bp_per_leg_per_side=2,new_conditions=500,old_conditions=500,
        score='sum(unrounded completed cycle net / abs(initial spot entry notional) * 100)',open_pnl_excluded=True))
    write_json(out/'environment.json',dict(python='3.12.0',numpy='2.2.6',numba='0.61.2',storage='D_ONLY',mode='PAPER_EXPLORATORY',
        static_type_checker='Not installed; original environment preserved; runtime numeric and ledger audits used'))
    write_json(out/'provenance.json',dict(approved_market_input_sha256=SOURCE_HASH,margin_sha256=MARGIN_HASH,
        raw_data='INPUT_NOT_REMOTELY_REPRODUCIBLE',scope='Approved exploratory KRX business dates 2026-01-01..10-15 plus necessary night boundaries',
        protected_oos_access=False,common_engine_unchanged=True,
        limitations=['Historical orderbook absent: next contiguous observed minute OPEN is fill proxy',
            'Reverse borrowing availability and cost unverified','Jul06-Aug02 margin schedule inferred from adjacent official schedules',
            'Monthly/quarter results use same exploratory sample, not independent validation',
            'MDD uses observed OPEN/CLOSE/settlement marks; unobserved intraminute adverse prices excluded']))
    table(out/'batch_publication_index.csv',[dict(batch=i+1,commit=r['commit'],remote=r['remote'],files=r['files']) for i,r in enumerate(receipts)])
    best=groups['overall'][0];newbest=max([r for r in new if r['feasible'] and r['cycles']],key=lambda r:r['score_pct'])
    report='# 일괄17계약 후속500조건 최종 비교\n\n'
    report+='현재 낙폭·누적 MDD 합성 검사와 기존 두 후보 전체 원장 재검산을 통과했습니다.\n'
    report+='기존500조건은 재계산하지 않고 보존했으며 신규500조건을50개씩 사전등록·실행했습니다.\n'
    report+='모든 신규 후보의 체결·정산·롤오버·현금·증거금 및 누적 MDD를 두 독립 방식으로 대조했습니다.\n'
    report+=f"전체 최고는 {best['candidate_id']}, 완료{best['cycles']}회, 비용 차감 수익률 합계 {best['score_pct']:+.8f}%입니다.\n"
    report+=f"기존 최고17.0956518029% 대비 변화는 {best['score_pct']-17.095651802927925:+.8f}%p입니다.\n"
    report+='잔여 포지션과 가정 청산 손익은 주 점수에서 분리했으며 역배는 차입 미검증 이론값입니다.\n'
    report+='모든 배치 원격 바이트·SHA 검증 완료 후500조건에서 종료하며 실제 주문·Final OOS 접근은 없습니다.\n\n'
    report+='|구분|후보|완료|수익률 합계%|실현 순이익 원|MDD 원|최대 평가손실 원|최소 초기증거금 여유 원|잔여|\n|---|---|---:|---:|---:|---:|---:|---:|---:|\n'
    for name,x in leaders.items():
        r=x['result'];report+=f"|{name}|{r['candidate_id']}|{r['cycles']}|{r['score_pct']:+.8f}|{r['net_realized']:,.2f}|{r['mdd_krw']:,.2f}|{r['maximum_open_loss_krw']:,.2f}|{r['minimum_initial_headroom_krw']}|{r['residual_contracts']}|\n"
    report+='\n주 순위는 완료 사이클 순손익 / 현물 최초 진입 명목 절대값 ×100의 반올림 전 단순합계입니다. 계좌 수익률이 아닙니다. 조건이유·정확한 규칙·승률·평균/최장 보유기간·현물 필요조달·최소 유지증거금 여유·진입 거절·잔여 가정청산 점수는 전체 CSV 및 best_rules_and_results.json에 있습니다. 유지증거금 부족/롤 자금 부족 후보는 계좌조건 통과 순위에서 제외하고 별도 원장과 무제한 PAPER 순위에 남겼습니다.\n\n'
    report+='비용은 현물 편도0.05%, 선물 계약당편도600원+청산율0.0003157%, 각 레그편도2bp, 롤 양쪽 비용입니다. 선물3천만원에서 정산손익을 누적하며 외부입금/계좌자동이체/추가진입은 없습니다. 현물 조달은 충분하다고 가정합니다. 역배 차입비 미포함으로 실전가능 수익을 입증하지 않습니다.\n\n'
    report+='|신규 배치|커밋 SHA|\n|---|---|\n'
    for i,r in enumerate(receipts,1):report+=f"|{i:04d}|{r['commit']}|\n"
    report+='\n|신규 배치|배치 최고|사이클|승률%|수익률합계%|순이익 원|MDD 원|최대 관측 평가손실 원|최소 초기증거금 여유 원|잔여|\n|---|---|---:|---:|---:|---:|---:|---:|---:|---:|\n'
    for r in batch_best:
        report+=f"|{r['batch']}|{r['candidate_id']}|{r['cycles']}|{r['win_rate_pct']:.2f}|{r['score_pct']:+.8f}|{r['net_realized']:,.2f}|{r['mdd_krw']:,.2f}|{r['maximum_open_loss_krw']:,.2f}|{r['minimum_initial_headroom_krw']:,.2f}|{r['residual_contracts']}|\n"
    report+='\n마지막 미등록50조건은 등록기v2에서 손익 익절·손익 손절·세션·회복 정체·분당 거래량 축을10조건씩 사전등록했습니다. 기존v1 등록기와 이전 조건·엔진·검산기·비용은 보존했습니다. 마지막 배치의 최초 원격 검증에서 git show 종료128이 한 번 발생했으나 동일 객체 단독조회와 fresh fetch 후 동일 커밋37파일 전체 검증은 통과했습니다. 최초 Git 내부 오류 원인은 확정하지 못했으며 전략 재계산·자료 수정·중복 게시 없이 검증만 재시도했습니다.\n'
    report+='\n원장 전체는 각 배치 archive_parts.json에 기재한 분할 TAR로 무손실 보관했습니다. 모든 member SHA와100개 NPZ의 CRC를 배치별 검사했습니다. 변동이 없는 승인 원시 입력과 공통 매매 엔진은 중복 업로드하지 않고 해시·기존 원격 경로를 참조합니다. 원시 입력은 D:전용이므로 공개 파일만으로 시세를 포함한 완전 재실행이 가능하다는 주장은 하지 않습니다. 미래 자료를 읽지 않는 기존 trailing 통계와 기존 매매 엔진을 유지했습니다. 가격 대용값, 차입, 증거금 일정 추론, 표본 최적화 및 분중 미관측 MDD 한계는 그대로입니다.\n'
    (out/'REPORT_KO.md').write_text(report,encoding='utf8')
    write_json(out/'checkpoint.json',dict(status='ALL_500_BATCHES_PUBLISHED_VERIFIED_FINAL_REPORT_PENDING',new_conditions=500,total_comparison_conditions=1000,
        workers_running=False,next_batch=None,best=best,new_best=newbest,prior_best_changed=best['score_pct']>17.095651802927925+1e-10))
    manifest(out)
    print(json.dumps(dict(output=str(out),best=best,new_best=newbest,leaders=leaders,conditions=500)),flush=True)


if __name__=='__main__':main()
