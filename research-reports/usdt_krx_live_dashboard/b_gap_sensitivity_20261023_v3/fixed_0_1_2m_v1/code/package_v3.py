# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
# Run: python -B package_v3.py; packages existing results, no simulation.
from pathlib import Path
import csv
import gzip
import hashlib
import json
import platform
import shutil
ROOT=Path(__file__).resolve().parents[1]
PUB=ROOT/'publish_payload'

def read(path:Path)->list[dict[str,str]]:
    with path.open(encoding='utf-8-sig',newline='') as stream:
        return list(csv.DictReader(stream))

def write(path:Path,rows:list[dict])->None:
    with path.open('x',encoding='utf8',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)

def save(name:str,value:dict)->None:
    (PUB/name).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf8')

def main()->None:
    PUB.mkdir(exist_ok=False)
    for name in ('README_KO.md','gap_policy.py','run_gap_sensitivity.py','test_gap_policy.py','test_gap_engine.py','audit_v3.py','package_v3.py'):
        (PUB/'code').mkdir(exist_ok=True);shutil.copyfile(ROOT/'code'/name,PUB/'code'/name)
    for name in ('preregistration.json','download_verification.json','tests.json','execution.json'):
        shutil.copyfile(ROOT/name,PUB/name)
    shutil.copyfile(ROOT/'manifest.json',PUB/'delivery_manifest.json')
    for path in (ROOT/'audit').iterdir():
        shutil.copyfile(path,PUB/path.name)
    summary=json.loads((ROOT/'results/summary.json').read_text(encoding='utf8'))
    shutil.copyfile(ROOT/'results/sensitivity_comparison.csv',PUB/'sensitivity_comparison.csv')
    save('summary.json',summary)
    archives=[];comparison=[];costs=[];parity=[]
    for limit in range(3):
        source=ROOT/f'results/MISSING_{limit}M'
        target=PUB/f'MISSING_{limit}M';target.mkdir()
        shutil.copyfile(source/'boundaries.csv',target/'boundaries.csv')
        groups=[]
        for variant in ('B-RECOVERY-ONLY','B-DUAL-CONTROL'):
            detail=source/variant;dest=target/variant;dest.mkdir()
            for name in ('fills','cycles','residuals','signals','gap_events'):
                shutil.copyfile(detail/f'{name}.csv',dest/f'{name}.csv')
            data=(detail/'observed_valuation_ledger.csv').read_bytes()
            packed=gzip.compress(data,compresslevel=9,mtime=0)
            assert gzip.decompress(packed)==data
            (dest/'observed_valuation_ledger.csv.gz').write_bytes(packed)
            archives.append(dict(path=(dest/'observed_valuation_ledger.csv.gz').relative_to(PUB).as_posix(),
                compressed_bytes=len(packed),uncompressed_bytes=len(data),
                uncompressed_sha256=hashlib.sha256(data).hexdigest(),roundtrip_equal=True))
            cycles=[r for r in read(detail/'cycles.csv') if r['scope']=='CONDITIONAL_CHAIN']
            residuals=[r for r in read(detail/'residuals.csv') if r['scope']=='CONDITIONAL_CHAIN']
            s=next(r for r in summary['results'] if r['variant']==variant and r['allowed_missing_minutes']==limit)
            comparison.append(dict(limit=limit,variant=variant,independent_chains=s['independent_chains'],
                entries=s['conditional_entries'],completed=len(cycles),win_rate_pct=100*sum(float(r['net'])>0 for r in cycles)/len(cycles),
                closed_net_sum_NOT_ANNUAL=s['conditional_completed_net_krw_sum_NOT_ANNUAL'],
                cycle_return_sum_pct_NOT_ANNUAL=s['conditional_completed_return_pct_sum_NOT_ANNUAL'],
                censored_opens=len(residuals),gap_exposed_completed=sum(r['gap_exposed']=='True' for r in cycles),
                intraday_gap_exposed_completed=sum(int(r['intraday_gap_count'])>0 for r in cycles),
                edge_gap_exposed_completed=sum(int(r['edge_gap_count'])>0 for r in cycles),
                worst_independent_chain_mdd_krw=s['worst_conditional_chain_observed_mdd'],
                maximum_observed_open_loss_krw=s['worst_conditional_chain_open_loss'],
                residual_net_sum_NOT_SINGLE_ACCOUNT=sum(float(r['hypothetical_liquidation_net']) for r in residuals),
                worst_residual_net_krw=min(float(r['hypothetical_liquidation_net']) for r in residuals),
                annual_prefix_last=s['annual_prefix_last'],annual_prefix_realized_net=s['annual_prefix_realized_net'],
                annual_prefix_last_total_observed=s['annual_prefix_last_total_observed'],annual_prefix_mdd=s['annual_prefix_mdd'],
                annual_prefix_last_open_net=s['annual_prefix_last_total_observed']-s['annual_prefix_realized_net'],
                average_completed_hold_minutes=sum(float(r['holding_minutes']) for r in cycles)/len(cycles),
                longest_completed_hold_minutes=max(float(r['holding_minutes']) for r in cycles)))
            fills=read(detail/'fills.csv')
            costs.append(dict(limit=limit,variant=variant,scope='CONDITIONAL_CHAIN',
                paid_fees=sum(float(r['spot_fee'])+float(r['future_fee']) for r in fills if r['scope']=='CONDITIONAL_CHAIN'),
                paid_slippage=sum(float(r['spot_slippage'])+float(r['future_slippage']) for r in fills if r['scope']=='CONDITIONAL_CHAIN'),
                roll_events=0,roll_validation='UNAVAILABLE_STOP_AT_REFERENCE_CHANGE',borrowing_cost='UNVERIFIED_NOT_CONFIRMED_ZERO'))
            groups.append([tuple((k,r[k]) for k in ('scope','chain','cycle','entry_t','exit_t','net','return_pct','fees','slippage')) for r in read(detail/'cycles.csv')])
        assert groups[0]==groups[1]
        parity.append(dict(limit=limit,primary_and_control_economic_cycles_equal=True))
    write(PUB/'results.csv',comparison);write(PUB/'costs.csv',costs);write(PUB/'archive_verification.csv',archives)
    save('control_comparison.json',dict(results=parity))
    save('settings.json',dict(mode='2025_CONDITIONAL_QUOTE_LOG_PAPER_MISSING_GAP_SENSITIVITY',
        tolerances=[0,1,2],order_window='09:00..15:30 actually observed logger times',
        entry_long_cross=-.97,entry_reverse_cross=.85,recovery_pp=.6,control_pnl_pct=.7,
        contracts=17,quantity_usdt=170000,initial_future_cash=30000000,
        spot_fee_per_side=.0005,future_fee_per_contract_side=600,future_notional_fee_per_side=.000003157,
        extra_slippage_each_leg_side=.0002,quantity_depth_and_borrow_margin_verified=False,
        normal_closures_carry=True,pending_orders_canceled_at_gap=True,fill_only_next_observed_60s=True,
        session_edge_limit_applies_individually_to_each_end=True,roll_prices_fabricated=False,
        missing_marks_fabricated=False,source_identity='USER_APPROVED_REFERENCE_CONTRACT_HYPOTHESIS_ONLY'))
    save('environment.json',dict(python=platform.python_version(),platform=platform.platform(),working_root=str(ROOT),
        temp=str(ROOT/'tmp'),packages_added=False,strategy_source_modified=False))
    save('provenance.json',dict(code_commit='e07a4fc955118406102cb33ef46c040980175c05',
        baseline_commit='72cc8eb39044f0ccc056cf9e1b1ffe637e5dbf74',
        source_data_commit='c8469e29cbaf67368e4e0fff42de1d2a6fb779d4',
        inputs=json.loads((ROOT/'preregistration.json').read_text()),
        input_access='INPUT_NOT_REMOTELY_REPRODUCIBLE; third-party raw quotes retained D-only',
        original_inputs_changed=False,final_oos_accessed=False))
    save('checkpoint.json',dict(status='LOCAL_COMPLETE_AUDITED_AWAITING_REMOTE_VERIFY',completed_tolerances=[0,1,2],
        both_variants_complete=True,more_work_scheduled=False,annual_result_certified=False))
    lines=['# 2025년 B 장중 누락 허용 v3 — 조건부 PAPER',
        '', '1. 전달된 원본 코드 5개는 크기·SHA-256이 모두 일치하며 수정하지 않았다.',
        '2. 합성 테스트 2개와 실제 자료의 0분 기준 재현이 통과했다.',
        '3. 완료 거래는 0분 8회, 1분 10회, 2분 11회다.',
        '4. 누락을 허용하자 관측 MDD와 최대 평가손실도 커졌다.',
        '5. 1분 완료 3회, 2분 완료 4회는 누락 노출 거래로 따로 보존했다.',
        '6. 독립 구간의 진단 합계를 한 계좌의 연간 수익률로 해석하면 안 된다.',
        '7. 실제 월물·시간대·차입·17계약 체결 깊이·증거금은 여전히 미검증이다.', '',
        '| 누락 허용 | 독립 구간 | 진입 | 완료 | 승률 | 완료 순손익 진단합(원) | 사이클 수익률 진단합 | 중단·잔여 | 누락 노출 완료 | 최악 구간 관측 MDD(원) | 최대 관측 평가손실(원) |',
        '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
    for r in comparison[::2]:
        lines.append(f"| {r['limit']}분 | {r['independent_chains']} | {r['entries']} | {r['completed']} | {r['win_rate_pct']:.1f}% | {r['closed_net_sum_NOT_ANNUAL']:,.2f} | {r['cycle_return_sum_pct_NOT_ANNUAL']:+.8f}% | {r['censored_opens']} | {r['gap_exposed_completed']} | {r['worst_independent_chain_mdd_krw']:,.2f} | {r['maximum_observed_open_loss_krw']:,.2f} |")
    lines += ['', '위 금액·수익률 합계는 서로 별도 초기현금에서 시작한 독립 구간의 완료 거래 진단합이다. 연간 자산·연간 수익률·운용 가능 성과가 아니다. 미청산 평가손익은 results.csv와 period_results.csv에 별도 보존했다. 승률은 완료 거래만의 비율이며 중단·잔여 손실을 제외한다.',
        '', '## 한 계좌의 검증 가능한 앞부분',
        '| 허용 | 마지막 관측 | 완료 순손익 | 열린 포지션 평가손익 | 합산 관측 순손익 | 관측 MDD |',
        '|---|---|---:|---:|---:|---:|']
    for r in comparison[::2]:
        lines.append(f"| {r['limit']}분 | {r['annual_prefix_last']} | {r['annual_prefix_realized_net']:,.2f} | {r['annual_prefix_last_open_net']:,.2f} | {r['annual_prefix_last_total_observed']:,.2f} | {r['annual_prefix_mdd']:,.2f} |")
    lines += ['', '0분은 1월 10일 장중 결측에서, 1·2분은 1월 20일 뒤 참조 월물 변경에서 열린 포지션 추적이 중단된다. 이후 독립 구간을 앞부분 계좌에 합치지 않았다.',
        '', '## 기준 재현 및 검산',
        '0분: 47구간·199정상 이월·26진입·8완료·18미청산. 최초 거래 순이익 1,006,055.4538430077원, 앞부분 계좌 MDD 7,530,766.978399001원 일치. 이전 커밋의 모든 사이클과 현금·평가·누적MDD 경로까지 대조했다.',
        '기존 Decimal 회계 검산기와 누적 MDD 모듈을 재사용했다. 총 162개 계좌/구간 그룹, 532,176개 관측 평가 행을 독립 검산했다. ANNUAL_PREFIX는 같은 거래의 별도 연속계좌 보기이므로 CONDITIONAL_CHAIN과 더하면 중복 집계다.',
        '', '## 장중·세션 끝 누락 효과',
        '1분 허용: 장중 19경계/19분, 세션 끝·시작 11경계/합계11분 연결. 2분 허용: 장중 22경계/합계25분, 세션 끝·시작 11경계/합계11분 연결. 정상 휴장 이월199개와는 별개다. 세션 양끝 허용치는 각각 적용되지만 실제 연결 경계의 합계 최대 누락은 1분이었다.',
        '1분의 누락 노출 완료3개 중 장중 노출1개, 세션 끝 노출3개로 서로 겹친다. 따라서 완료 증가를 순수 장중 누락 효과로 부르지 않는다. 세부 내역은 gap_exposed_cycles.csv, boundary_summary.csv 및 각 boundaries.csv 참조.',
        '원래 감사의 월물 변경11개 중 2025-05-19→06-17 경계는 장기공백이 겹쳐 v3에서 MISSING_OFFICIAL_TRADING_DATES로 먼저 분류됐다. 나머지10개는 REF_CHANGE_UNVERIFIED_ROLL이다. 11개 모두 연결하지 않았으며 참조 월물 변경을 통과한 거래는 없다.',
        '', '## 보존·실행 방법·한계',
        '원본 B의 진입선·회복폭·수량·초기현금·수수료·2bp 추가 슬리피지는 그대로다. +0.7% 대조군은 별도 실행했고 완료 거래의 경제적 경로가 주 검증과 같았다. 청산 사유 라벨은 RECOVERY/BOTH 차이를 보존했다.',
        '미관측 야간·누락분 가격/주문/평가 경로는 만들지 않았다. 호가 잔량, 차입비용, 실제 월물, 일일정산, 초기/유지증거금 및 롤오버 가격은 검증하지 않았다. 참조 월물 변경에서 중단하며 임의 롤오버하지 않았다. 이 현금 원장을 증거금 적격 판정으로 사용할 수 없다.',
        'D:에 보존된 preregistration.json의 입력과 원본 README 명령으로 빈 신규 --out 폴더에서 재현한다. 기존 입력을 다시 다운로드하지 않았고, 제3자 가격 원문/전체 정규화 자료는 공개 게시하지 않는다. 공개 코드는 고정되어 있지만 입력은 D: 전용이므로 INPUT_NOT_REMOTELY_REPRODUCIBLE이다.',
        '전체 체결·사이클·신호·잔여·연결 이벤트는 정책/버전별 CSV, 전체 관측 평가 원장은 손실 없는 gzip으로 제공한다. archive_verification.csv가 압축 해제 바이트와 해시를 기록한다. 기존 결과·Final OOS·Gateway·수집기는 변경하지 않았다.']
    (PUB/'REPORT_KO.md').write_text('\n'.join(lines)+'\n',encoding='utf8')
    print(json.dumps(dict(status='PACKAGED',files=sum(p.is_file() for p in PUB.rglob('*')),comparison=comparison),ensure_ascii=False))

if __name__=='__main__':
    main()
