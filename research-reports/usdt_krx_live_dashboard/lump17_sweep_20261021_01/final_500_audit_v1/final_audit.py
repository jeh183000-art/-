from __future__ import annotations

import csv
import gzip
import hashlib
import json
import shutil
from pathlib import Path

import numpy as np

from package import manifest
from runner import ROOT, SOURCE_HASH, MARGIN_HASH, table, write_json, canonical


def read_csv(path):
    opener=gzip.open if path.name.endswith('.gz') else open
    with opener(path,'rt',encoding='utf8',newline='') as stream:return list(csv.DictReader(stream))


def close(a,b,tolerance=.01):
    assert abs(float(a)-float(b))<tolerance,(a,b,tolerance)


def main():
    out=ROOT/'publish_payloads/final_500_audit_v1'
    assert not out.exists();out.mkdir(parents=True)
    rows=[];checks=[];registrations=[];publications=[];rules={}
    for number in range(1,11):
        name=f'batch_{number:04d}'
        receipt=json.loads((ROOT/'publication'/f'{name}_results_verified.json').read_text())
        assert receipt['status']=='PUBLISHED_VERIFIED'
        publications.append(receipt)
        spec=json.loads((ROOT/'preregistration'/f'{name}.json').read_text())
        assert len(spec['conditions'])==50
        assert hashlib.sha256(canonical(spec['conditions'])).hexdigest()==spec['grid_sha256']
        registrations.extend(spec['conditions'])
        for candidate in spec['conditions']:
            cid=candidate['candidate_id'];rules[cid]=candidate['rule']
            folder=ROOT/'batches'/name/'candidates'/cid
            r=json.loads((folder/'result.json').read_text())
            assert r['rule_sha256']==candidate['rule_sha256']
            cycles=read_csv(folder/'cycles.csv.gz');fills=read_csv(folder/'fills.csv.gz')
            score=0.
            for cycle in cycles:
                close(cycle['contracts'],17);close(cycle['spot_quantity'],170000)
                close(cycle['spot_entry_notional'],float(cycle['entry_spot'])*170000)
                value=float(cycle['net'])/float(cycle['spot_entry_notional'])*100
                close(value,cycle['return_pct'],1e-10);score+=value
            close(score,r['score_pct'],1e-9)
            close(sum(float(c['net']) for c in cycles),r['net_realized'])
            assert len(cycles)==r['cycles']
            orders=read_csv(folder/'orders.csv.gz')
            for order in orders:
                close(order['requested_contracts'],17)
                assert int(float(order['filled_contracts'])) in (0,17)
            numbers=np.load(folder/'numeric_result.npz')
            account=np.load(folder/'full_account_ledger.npz')['ledger']
            residual=numbers['residual'];trades=numbers['trades']
            close(sum(float(f['spot_fee'])+float(f['future_fee']) for f in fills),r['fees_krw'])
            close(sum(float(f['spot_slippage'])+float(f['future_slippage']) for f in fills),r['slippage_krw'])
            close(float(np.sum(trades[:,11]))+residual[7],r['fees_krw'])
            close(float(np.sum(trades[:,12]))+residual[8],r['slippage_krw'])
            close(account[0,0,1],30000000)
            close(account[-1,1,5]-30000000,r['net_realized']+account[-1,1,6])
            close(np.nanmax(account[:,:,8]),r['mdd_krw'])
            assert np.nanmax(np.abs(account[:,:,7]))<=1
            if residual[0]:
                close(account[-1,1,6]-residual[9],residual[10])
                close(residual[10],r['residual_net_after_exit_cost'])
                close(score+residual[10]/(residual[3]*170000)*100,r['forced_terminal_score_pct'],1e-9)
                assert r['residual_contracts']==17
            else:
                assert r['residual_contracts']==0
                close(score,r['forced_terminal_score_pct'],1e-9)
            rows.append(r)
            checks.append(dict(candidate_id=cid,status='PASS_SAVED_CSV_NUMERIC_AND_ACCOUNT_CROSSCHECK',cycles=len(cycles),score_pct=score,contracts=17))
        print(json.dumps(dict(stage='FINAL_SAVED_LEDGER_AUDIT',batch=number,checked=len(rows))),flush=True)
    assert len(rows)==500 and len({r['candidate_id'] for r in rows})==500
    assert len({r['rule_sha256'] for r in registrations})==500
    assert 'f291d540cf087ae8142872153b7276cbb7c90b4ac551d98613d13fa640ac338c' not in {r['rule_sha256'] for r in registrations}
    assert not (ROOT/'worker.lock').exists()
    eligible=sorted([r for r in rows if r['feasible'] and r['cycles']>0],key=lambda r:r['score_pct'],reverse=True)
    sections={'overall':eligible,'min5':[r for r in eligible if r['cycles']>=5],
        'min10':[r for r in eligible if r['cycles']>=10],'no_residual':[r for r in eligible if r['residual_contracts']==0],
        'long_only':[r for r in eligible if rules[r['candidate_id']].get('allowed_direction',0)==1 and not r['borrow_unverified']]}
    table(out/'results_all_500.csv',rows)
    table(out/'validation_all_500.csv',checks)
    for name,selected in sections.items():table(out/f'top20_{name}.csv',selected[:20])
    for direction in ('long','reverse'):
        selected=[r for r in eligible if r[direction+'_cycles']>0]
        table(out/f'top20_{direction}_integrated_contribution.csv',sorted(selected,key=lambda r:r[direction+'_score_pct'],reverse=True)[:20])
    table(out/'ineligible.csv',[r for r in rows if not r['feasible']])
    table(out/'zero_completed.csv',[r for r in rows if r['cycles']==0])
    write_json(out/'settings_all_500.json',dict(conditions=registrations,controls=json.loads((ROOT/'preregistration/batch_0001.json').read_text())['controls']))
    write_json(out/'verified_batch_commits.json',publications)
    write_json(out/'best_rules.json',{key:dict(result=value[0],rule=rules[value[0]['candidate_id']]) if value else None for key,value in sections.items()})
    write_json(out/'checkpoint.json',dict(status='ALL_500_AUDITED_AND_BATCH_PUBLICATIONS_VERIFIED',new_conditions=500,completed_batches=10,next_batch=None,worker_stopped=True,final_oos_access=False))
    write_json(out/'provenance.json',dict(source_sha256=SOURCE_HASH,margin_sha256=MARGIN_HASH,input_status='INPUT_NOT_REMOTELY_REPRODUCIBLE',
        code_ref=json.loads((ROOT/'publication/code_ref.json').read_text()),verification_timeout='Batch4 first wrapper expired at55s; same commit retry passed all35 files without rerunning any simulation.',
        missing_borrow_cost='UNVERIFIED_NOT_INCLUDED',approved_scope='2026-01-01..10-15 KRX business dates, approved exploratory boundary observations',
        trailing_helper=dict(commit='d64eb691b0cf084f6748df6abdab5f4c9d8e0027',
            path='research-reports/usdt_krx_live_dashboard/single_set_hypotheses_20261020_01/preregistration/code/signals.py',
            sha256='b7d59904f3d70543b5e16e4a8479c467ac16710658737cac25264559314d8937',remote_bytes_hash_verified=True)))
    shutil.copy2(ROOT/'code/final_audit.py',out/'final_audit.py')
    shutil.copy2(ROOT/'code/record_publication.py',out/'record_publication.py')
    shutil.copy2(ROOT/'preregistration/batch_zz_control_registry.json',out/'baseline_control_dedup_registry.json')
    shutil.copy2(ROOT/'publication/code_ref.json',out/'strategy_code_ref.json')
    write_json(out/'environment.json',dict(python='3.12.0',numpy=np.__version__,mode='PAPER_EXPLORATORY',storage='D_ONLY'))
    table(out/'costs.csv',[{k:r[k] for k in ('candidate_id','fees_krw','slippage_krw','borrow_unverified')} for r in rows])
    best=eligible[0]
    best_rule=rules[best['candidate_id']]
    comparable={k:v for k,v in best_rule.items() if k not in ('long_entry_gap_pct','short_entry_gap_pct')}
    neighbours=[r for r in rows if {k:v for k,v in rules[r['candidate_id']].items() if k not in ('long_entry_gap_pct','short_entry_gap_pct')}==comparable
        and abs(rules[r['candidate_id']]['long_entry_gap_pct']-best_rule['long_entry_gap_pct'])<=.40000001
        and abs(rules[r['candidate_id']]['short_entry_gap_pct']-best_rule['short_entry_gap_pct'])<=.40000001]
    table(out/'best_entry_neighbours.csv',[dict(r,long_entry_gap_pct=rules[r['candidate_id']]['long_entry_gap_pct'],short_entry_gap_pct=rules[r['candidate_id']]['short_entry_gap_pct']) for r in neighbours])
    winner_batch=int(best['candidate_id'].split('-')[1]);folder=ROOT/'batches'/f'batch_{winner_batch:04d}'/'candidates'/best['candidate_id']
    for source,dest in [('cycles.csv.gz','best_cycles.csv'),('fills.csv.gz','best_fills.csv'),('period_contribution.csv','best_period_contribution.csv'),('residual.csv','best_residual.csv')]:
        table(out/dest,read_csv(folder/source))
    report='# 일괄 17계약 500조건 탐색 최종 결과\n\n'
    report+=f"500조건을 각각 한 번 실행했고 10개 배치의 전체 원장을 독립 검산·게시·원격 검증했습니다. 기준 전략은 저장된 원장으로 재검증하여 45사이클·+13.1522166079%·32,356,627.77원·MDD9,350,000원이 일치했습니다.\n\n이번 탐색 1위는 **{best['candidate_id']}**, 비용 차감 완료 사이클 수익률 단순합 **+{best['score_pct']:.10f}%**입니다. 계좌 투자수익률이 아니며 미청산 손익은 주 점수에서 제외합니다.\n\n"
    report+='|구분|후보|완료 사이클|승률 %|수익률 합계 %|실현 순이익 원|MDD 원|최대 평가손실 원|최소 초기증거금 여유 원|잔여 계약|\n|---|---|---|---|---|---|---|---|---|---|\n'
    for name,selected in sections.items():
        if selected:
            r=selected[0]
            report+=f"|{name}|{r['candidate_id']}|{r['cycles']}|{r['win_rate_pct']:.4f}|{r['score_pct']:.8f}|{r['net_realized']:,.2f}|{r['mdd_krw']:,.2f}|{r['maximum_open_loss_krw']:,.2f}|{r['minimum_initial_headroom_krw']:,.2f}|{r['residual_contracts']}|\n"
    report+='\n1위의 정확한 조건:\n```json\n'+json.dumps(rules[best['candidate_id']],ensure_ascii=False,indent=2)+'\n```\n'
    report+=f"\n기준 대비 점수 변화는 {best['score_pct']-13.15221660791525:+.8f}%p입니다. 1위 잔여 포지션 청산비용 차감 평가손익 {best['residual_net_after_exit_cost']:,.2f}원, 종료 가정청산 점수 {best['forced_terminal_score_pct']:.8f}%를 별도로 기록했습니다. 최소 유지증거금 여유는 {best['minimum_maintenance_headroom_krw']:,.2f}원입니다. 평균 보유 {best['average_hold_minutes']}분, 최장 보유 {best['longest_hold_minutes']}분입니다.\n"
    report+=f"\n1위의 통합 원장 내 정배 기여는 {best['long_cycles']}사이클·{best['long_score_pct']:+.8f}%p, 역배 기여는 {best['reverse_cycles']}사이클·{best['reverse_score_pct']:+.8f}%p입니다. 다른 독립 전략의 성과를 합친 값이 아닙니다. 인접 진입선 비교는 best_entry_neighbours.csv, 청산월·분기 기준 완료 사이클 점수 기여는 best_period_contribution.csv에 보관했습니다. 미청산 평가손익을 월별 실현 성과에 넣지 않았습니다.\n"
    report+='\n최초17계약·170,000 USDT, 추가진입 없음, 양방향 통합 한 묶음, 후보별 선물현금3,000만원과 외부입금/자동이체 없음 조건입니다. 현물 조달은 충분하다고 가정한 모델이며 실제 사용자 잔액이 아닙니다. 모든 실제 체결은 확인되지 않은 다음 연속 관측 분봉 시가 대용입니다. 수수료·각 레그 편도2bp·롤오버 양쪽 비용을 반영했습니다. 역배 차입 가능성과 차입비용은 미검증이므로 혼합형/역배 성과는 이론값입니다.\n\n7월6일~8월2일 증거금 일정 추론, 과거 호가·분중 평가손실 미관측 한계를 유지합니다. 전체 자료가 탐색용이므로 이 결과는 독립 OOS 검증이나 확정 최적 전략이 아닙니다. 종료 잔여, 관측 증거금 부족 후보, 완료0건은 분리했습니다.\n\n4배치의 첫 원격 검증은55초 실행 제한으로 끝났지만 같은 커밋의 재검증은 모든35파일이 일치했습니다. 시뮬레이션 재계산은 없었습니다. 이후 검증 프로세스를 짧게 나눠 대기하며 진행했습니다. Gateway·예약 작업·다른 연구·Final OOS·실거래는 변경/접근하지 않았습니다.\n\n## 배치별 검증 커밋\n\n|배치|신규 조건|커밋|\n|---|---|---|\n'
    for p in publications:report+=f"|{p['batch']}|50|{p['commit']}|\n"
    report+='\n배치별 원장 위치는 각 커밋의 research-reports/usdt_krx_live_dashboard/lump17_sweep_20261021_01/batches/batch_NNNN_results_v1 입니다. 모든 후보 원장은 압축·분할 TAR로 무손실 보관되며 재조립 SHA와 압축 CRC까지 검사했습니다. 원시 시세는 D:에 있어 INPUT_NOT_REMOTELY_REPRODUCIBLE이며 각 배치의 code_ref·schema·manifest가 재현과 검산에 필요한 참조를 제공합니다.\n'
    (out/'REPORT_KO.md').write_text(report,encoding='utf8')
    manifest(out)
    print(json.dumps(dict(status='FINAL_500_SAVED_LEDGER_AUDIT_PASS',best=best,output=str(out))),flush=True)


if __name__=='__main__':main()
