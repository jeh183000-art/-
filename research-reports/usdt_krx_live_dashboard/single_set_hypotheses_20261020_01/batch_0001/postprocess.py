from __future__ import annotations
import csv, gzip, hashlib, json, platform, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
B = ROOT / 'batch_0001'
P = ROOT / 'publication_payload'

def read(name):
    with (B/name).open(encoding='utf-8', newline='') as f:
        return list(csv.DictReader(f))

def write(name, rows):
    with (P/name).open('x', encoding='utf-8', newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)

def main():
    P.mkdir()
    rows=read('results.csv'); cycles=read('cycles.csv')
    eligible=sorted([r for r in rows if int(r['completed_cycles'])],key=lambda r:float(r['score_pct']),reverse=True)
    for minimum in (1,5,10):
        subset=[r for r in eligible if int(r['completed_cycles'])>=minimum]
        write(f'ranking_min_{minimum}_cycles.csv', subset)
    zero=[r for r in rows if not int(r['completed_cycles'])]
    write('zero_completed_cycles.csv',zero)
    for r in rows:
        cc=[c for c in cycles if c['candidate_id']==r['candidate_id']]
        assert len(cc)==int(r['completed_cycles'])
        if cc:
            assert abs(sum(float(c['cycle_return_pct']) for c in cc)-float(r['score_pct']))<1e-10
            for c in cc:
                assert abs(float(c['cycle_return_pct'])-100*float(c['net'])/abs(float(c['entry_spot'])*10000))<1e-10
    fields='entry target recovery window fraction confirm max_hold gap_stop pnl_profit pnl_stop stall'.split()
    neighbors=[]
    for i,a in enumerate(rows):
        for b in rows[i+1:]:
            if a['family']==b['family'] and a['direction']==b['direction']:
                changed=[k for k in fields if a[k]!=b[k]]
                if len(changed)==1:
                    neighbors.append(dict(a=a['candidate_id'],b=b['candidate_id'],changed=changed[0],a_score=a['score_pct'],b_score=b['score_pct']))
    write('neighbor_comparison.csv',neighbors)
    for name in ('results.csv','cycles.csv','trades.csv.gz','residuals.csv','monthly.csv','risk_extremes.csv.gz','costs.csv','validation.json','READY.json'):
        if name=='cycles.csv':
            with gzip.open(P/'cycles.csv.gz','wb') as out:
                out.write((B/name).read_bytes())
        else:
            shutil.copyfile(B/name,P/name)
    shutil.copyfile(ROOT/'postprocess.py',P/'postprocess.py')
    reference={'commit':'d64eb691b0cf084f6748df6abdab5f4c9d8e0027','path':'research-reports/usdt_krx_live_dashboard/single_set_hypotheses_20261020_01/preregistration','code_sha256':json.loads((ROOT/'preregistration.json').read_text())['code_sha256']}
    (P/'strategy_code_ref.json').write_text(json.dumps(reference,indent=2),encoding='utf-8')
    shutil.copyfile(ROOT/'preregistration.json',P/'settings.json')
    (P/'environment.json').write_text(json.dumps({'python':platform.python_version(),'platform':platform.platform(),'numpy':'2.2.6','numba':'0.61.2','pandas':'3.0.1','runtime':'existing Python312; process-only D cache/temp','data_access':'Approved exploration only; input originals remain local D, INPUT_NOT_REMOTELY_REPRODUCIBLE','execution':'next observed contiguous minute open proxy; no orderbook fill verification'},indent=2),encoding='utf-8')
    bests={label:next((r for r in eligible if str(r['direction'])==direction),None) for label,direction in [('long','1'),('reverse','-1'),('combined','0')]}
    for label,direction in [('long','1'),('reverse','-1'),('combined','0')]:
        write('ranking_'+label+'.csv',[r for r in eligible if r['direction']==direction])
    summary={'conditions':len(rows),'completed_cycles_total':len(cycles),'zero_cycle_conditions':len(zero),'overall_best':eligible[0],'direction_best':bests,'min5_best':next(r for r in eligible if int(r['completed_cycles'])>=5),'min10_best':next(r for r in eligible if int(r['completed_cycles'])>=10),'ledger_return_audit':'PASS','worker_stopped':not (ROOT/'worker.lock').exists()}
    (P/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['# 固定1セット研究・第1バッチ'.replace('固定1セット研究・第1バッチ','고정 1세트 연구 첫 50조건'),'', '2026년 승인 탐색 자료의 PAPER 결과입니다. 독립 검증 성과나 실제 체결 수익이 아닙니다.', '', '|순위|조건|방법|방향|완료 사이클|비용 차감 수익률 합계|승률|MDD(원)|잔여 순평가손익(원)|','|---|---|---|---|---:|---:|---:|---:|---:|']
    for i,r in enumerate(eligible[:20],1):
        lines.append(f"|{i}|{r['candidate_id']}|{r['family']}|{r['direction']}|{r['completed_cycles']}|{float(r['score_pct']):.6f}%|{float(r['win_rate_pct']):.2f}%|{float(r['mdd_krw']):,.0f}|{float(r['residual_net_after_close_cost_krw']):,.0f}|")
    lines += ['', '## 규칙과 해석', '', '정확한 50개 조건은 settings.json, 전체 성과와 보유시간·평가손실·잔여계약은 results.csv에 보존했습니다. 평균·중앙값·분포는 현재 봉을 제외한 과거 관측치만 사용합니다. 첫 봉의 기존 괴리는 소급 진입하지 않으며 계약 교체 시 기준을 다시 준비합니다.', '', '각 후보는 테더 10,000개와 반대방향 달러선물 1계약만 보유합니다. 보유 중 추가 신호는 무시하며 청산 후만 재진입합니다. 롤오버는 이전 계약 청산 후 새 계약 1개로 교체하고 양쪽 비용을 차감합니다.', '', '주 점수는 각 완료 사이클 순손익 / 최초 현물 진입금액 절대값 ×100의 반올림 전 합계입니다. 초기자본·증거금·순이익 금액으로 순위를 바꾸지 않았습니다. 완료0건은 별도 파일이며 잔여 손익은 주 점수에서 제외했습니다. score_with_hypothetical_final_close_pct는 마지막 관측가격으로 잔여를 청산한다고 가정한 보조 점수입니다.', '', '현물 편도0.05%, 선물 편도600원+명목금액0.0003157%, 각 포지션 편도 슬리피지2bp를 적용했습니다. 선물 롤오버 양방향 비용도 포함했습니다. 무기한 펀딩은 해당하지 않습니다. 역배의 USDT 현물 차입 가능성·차입비용은 미검증이므로 역배와 혼합형은 이론값입니다.', '', 'MDD와 최대 평가손실은 관측 시가·종가·정산가 기준 원화 손실이며 미관측 분중 극값을 보장하지 않습니다. 신호 다음 연속 관측분 시가를 체결 대용값으로 사용했습니다. 결측 구간을 보간하지 않고 그 직전 미체결 신호는 취소했습니다.', '', '## 검증과 비교', '', '10개 합성 단위검사 통과. 50조건 모두 수량상한·원장 수수료·슬리피지·손익 대조를 통과했습니다. 완료 사이클 원장의 수익률과 결과 점수도 독립 재집계했습니다. monthly.csv와 neighbor_comparison.csv는 기간별 및 한 변수만 다른 이웃조건 비교입니다. 완료5회·10회 이상 순위는 별도 CSV입니다.', '', '새 연구 첫 배치이므로 이전 최고 후보는 없습니다. 기존 무제한 다중계약 연구와는 노출제약이 달라 동일 순위로 비교하지 않습니다. 높은 점수라도 잔여손실·표본수·기간집중을 함께 보아야 합니다. 최적화 후 독립 검증은 아직 하지 않았습니다.', '', '원본 데이터와 기존 엔진은 수정하지 않았습니다. 공유 원본의 해시는 settings.json, 신규 코드 원격 버전은 strategy_code_ref.json에 있습니다. 원본 시장자료는 D에만 보관되어 공개 GitHub 단독으로 전체 재실행할 수 없습니다. 원본을 가진 환경에서 code/bootstrap.py run으로 재현할 수 있으며 기존 완료 폴더 덮어쓰기는 금지됩니다.', '', '첫50조건만 실행하고 워커를 종료했습니다. 다음 배치·수집기·예약작업·Gateway 변경은 수행하지 않았습니다.']
    (P/'REPORT_KO.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    with (P/'REPORT_KO.md').open('a',encoding='utf-8') as out:
        out.write('\n## 주요 후보 규칙과 위험\n\n')
        out.write('전체 최고 S1-050: 음수 방향 −1.0% 하향 통과 시 정배, 양수 방향 +1.0% 상향 통과 시 역배 진입. 해당 진입 신호 괴리에서 0.5%p 유리하게 회복하면 다음 유효분 시가로 청산합니다. 두 방향 합쳐 보유는 1세트입니다. 정배 최고 S1-037: −1.0% 하향 도달 후 관측 저점에서 0.1%p 반등을 확인해 진입하고, 확인 신호 괴리보다 0.5%p 회복하면 청산합니다. 역배 최고 S1-016: +0.8% 상향 통과 후 진입, 신호 괴리보다 0.5%p 하락 시 청산합니다.\n\n')
        for label,r in [('전체',eligible[0]),('정배',bests['long']),('역배',bests['reverse'])]:
            out.write(f"{label} {r['candidate_id']}: 평균 보유 {float(r['average_hold_minutes'])/60:.2f}시간, 최장 {float(r['longest_hold_minutes'])/1440:.2f}일, 최대 평가손실 {float(r['max_evaluation_loss_krw']):,.0f}원, MDD {float(r['mdd_krw']):,.0f}원, 잔여 {r['residual_sets']}세트 / 청산비용 차감 평가손익 {float(r['residual_net_after_close_cost_krw']):,.0f}원, 종료 청산 가정 합계 {float(r['score_with_hypothetical_final_close_pct']):.6f}%.\n\n")
        out.write('완료5회 이상 및10회 이상에서도 전체 최고는 S1-050입니다. 아래는 청산일의 KRX 거래월에 귀속한 완료 사이클 수익률 합계입니다. 미실현 월별 평가변화는 monthly.csv에 별도 있습니다.\n\n|월|전체 최고|정배 최고|역배 최고|\n|---|---:|---:|---:|\n')
        months=read('monthly.csv')
        for month in sorted({r['business_month'] for r in months}):
            values=[next(r['completed_cycle_score_pct'] for r in months if r['candidate_id']==c and r['business_month']==month) for c in [eligible[0]['candidate_id'],bests['long']['candidate_id'],bests['reverse']['candidate_id']]]
            out.write('|'+month+'|'+'|'.join(f'{float(x):.6f}%' for x in values)+'|\n')
        out.write('\n고빈도 평균·분포 회귀 조건의 다수는 비용 후 손실입니다. 최고가 일부 복귀폭 조건에 집중되어 있으며, 넓은 탐색 첫50개에서 발견한 후보이므로 전체 가능한 규칙의 최적값으로 확정하지 않습니다.\n')
    roles={'strategy_code_ref.json':'strategy_code','settings.json':'settings','results.csv':'results_csv','trades.csv.gz':'fills','costs.csv':'costs','REPORT_KO.md':'statistics_report','environment.json':'environment'}
    manifest={'study_id':ROOT.name,'batch_id':'batch_0001','status':'LOCAL_VALIDATED','files':[{'path':p.name,'role':roles.get(p.name,'supporting'),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(P.iterdir())]}
    (P/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    write('manifest.csv',manifest['files']+[{'path':'manifest.json','role':'supporting','bytes':(P/'manifest.json').stat().st_size,'sha256':hashlib.sha256((P/'manifest.json').read_bytes()).hexdigest()}])
    print(json.dumps(summary,ensure_ascii=False))

if __name__=='__main__': main()
