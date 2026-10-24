"""Build a whitelisted immutable BTCUSDT 4h research publication, without upload."""
from pathlib import Path
import csv
import gzip
import hashlib
import json
import shutil
import pandas as pd

ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / 'results'
OUT = ROOT / 'publication'
PREFIX = 'research-reports/btc4h-nextcandle/20261024-v1/batches/b01_20261024T045816Z_e57afd05'
PARENT_COMMIT = 'eb0b824cb66b3c918cd39490ba266538ff4bede2'
PARENT_PREFIX = 'research-reports/btc15-nextcandle/20261024-v1/batches/b01_20261024T044340Z_1df738ca'


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def pct(value):
    return '해당 없음' if pd.isna(value) else f'{value*100:.2f}%'


def main():
    if OUT.exists():
        raise SystemExit('Existing publication must remain unchanged; use a new batch folder')
    required = ['results/comparison_15m_4h.csv', 'results/evaluation/monthly_selected_metrics.csv',
                'results/evaluation/threshold_60_distribution.csv', 'results/prediction_smoke/prediction.json',
                'results/prediction_smoke/validation.json', 'results/independent_audit.json']
    missing = [name for name in required if not (ROOT/name).exists()]
    if missing:
        raise SystemExit('Required frozen outputs are not ready: '+', '.join(missing))
    selection = json.loads((RESULTS/'selection.json').read_text())
    selected = selection['selected_model']
    audit = json.loads((RESULTS/'independent_audit.json').read_text())
    data_audit = json.loads((ROOT/'data/data_audit.json').read_text())
    cross = json.loads((ROOT/'data/comparison_15m_to_4h.json').read_text())
    freeze = json.loads((ROOT/'engine_freeze.json').read_text())
    assert audit['status']=='PASS' and audit['failed_count']==0
    assert selected=='logistic', 'This frozen batch selected logistic; do not silently replace it'
    assert digest(ROOT/'model.py')==selection['model_code_sha256']
    assert digest(ROOT/'settings.json')==selection['protocol_sha256']
    dev = pd.read_csv(RESULTS/'development/results.csv').set_index('model')
    ev = pd.read_csv(RESULTS/'evaluation/results.csv').set_index('model')
    th = pd.read_csv(RESULTS/'evaluation/thresholds.csv')
    th = th[th.model.eq(selected)].set_index('threshold')
    months = pd.read_csv(RESULTS/'evaluation/monthly_selected_metrics.csv')
    comparison = pd.read_csv(RESULTS/'comparison_15m_4h.csv')
    bootstrap = pd.read_csv(RESULTS/'independent_audit.bootstrap.csv')
    smoke = json.loads((RESULTS/'prediction_smoke/prediction.json').read_text())
    split = pd.read_csv(RESULTS/'evaluation/split_audit.csv')
    OUT.mkdir()
    roles = {}

    def copy(source, destination=None, role='evidence'):
        destination = source if destination is None else destination
        target = OUT/destination
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT/source, target)
        roles[destination] = role

    def add_csv(name, rows, columns, role):
        pd.DataFrame(rows, columns=columns).to_csv(OUT/name, index=False, lineterminator='\n')
        roles[name] = role

    for name in ['model.py', 'data_loader.py', 'audit_predictions.py', 'test_model.py', 'prepare_report.py']:
        copy(name, role='strategy_code' if name=='model.py' else 'verification_code')
    for name in ['README_KO.md', 'requirements.txt', 'preregistration.json', 'engine_freeze.json']:
        copy(name)
    copy('settings.json', role='settings')
    for name in ['data_audit.json', 'download_manifest.json', 'comparison_15m_to_4h.json',
                 'aggregation_field_discrepancies.csv', 'aggregation_window_discrepancies.csv']:
        copy('data/'+name, role='input_provenance')
    copy('results/environment.json', 'environment.json', role='environment')
    for name in ['selection.json', 'candidates.csv', 'feature_columns.json', 'development_run.log',
                 'evaluation_run.log', 'independent_audit.md', 'independent_audit.metrics.csv',
                 'independent_audit.bootstrap.csv', 'comparison_15m_4h.csv']:
        copy('results/'+name)
    write_json(OUT/'results/independent_audit_summary.json', {k:v for k,v in audit.items() if k!='checks'})
    roles['results/independent_audit_summary.json']='audit'
    (OUT/'results/independent_audit.json.gz').write_bytes(gzip.compress((RESULTS/'independent_audit.json').read_bytes(),mtime=0))
    roles['results/independent_audit.json.gz']='audit'
    frames=[]
    for phase in ['development','evaluation']:
        for name in ['results.csv','thresholds.csv','monthly_metrics.csv','calibration_bins.csv',
                     'split_audit.csv','split_audit.json','metric_notes.json']:
            copy(f'results/{phase}/{name}')
        copy(f'results/{phase}/predictions.csv.gz',role='prediction_ledger')
        frame=pd.read_csv(RESULTS/phase/'results.csv')
        frame.insert(0,'phase',phase)
        frames.append(frame)
        paths=sorted((RESULTS/phase/'predictions_monthly').glob('*.csv'))
        assert len(paths)==12
        for path in paths:
            copy(f'results/{phase}/predictions_monthly/{path.name}',role='prediction_ledger')
    pd.concat(frames,ignore_index=True).to_csv(OUT/'results.csv',index=False,lineterminator='\n')
    roles['results.csv']='results_csv'
    for name in ['monthly_selected_metrics.csv','threshold_60_distribution.csv']:
        copy('results/evaluation/'+name)
    copy('results/evaluation/research_model.joblib',role='model_artifact')
    for name in ['prediction.json','validation.json']:
        copy('results/prediction_smoke/'+name)
    add_csv('trades.csv',[],['trade_id','entry_time','exit_time','side','quantity','pnl'],'fills')
    add_csv('cycles.csv',[],['cycle_id','entry_time','exit_time','net_return'],'cycles')
    add_csv('costs.csv',[{'status':'NOT_APPLICABLE_CLASSIFICATION_ONLY','actual_orders':0,
        'trade_backtest_run':False,'roundtrip_fee_assumption_for_future_study':0.0012,
        'funding_evaluated':False,'slippage_evaluated':False}],
        ['status','actual_orders','trade_backtest_run','roundtrip_fee_assumption_for_future_study',
         'funding_evaluated','slippage_evaluated'],'costs')
    risks=[('trading_returns_PF_MDD','NOT_EVALUATED'),('2026_accuracy','NOT_EVALUATED'),
           ('live_order_latency','NOT_EVALUATED'),('threshold_60pct','44_SAMPLES_ALL_UP_ALL_2025Q1'),
           ('same_bar_count_lookbacks','96BARS_16DAYS_VS_1DAY_FOR_15M'),
           ('calendar_calibration','90DAYS_539_SAMPLES_PER_FOLD'),
           ('cross_timeframe_source_equality','4_WINDOWS_DIFFER_0_COLOR_DIFFERENCES'),
           ('2024_performance','USED_FOR_SELECTION'),('2025_in_prior_research','NOT_GLOBALLY_UNTOUCHED'),
           ('bootstrap','DAILY_BLOCK_HEURISTIC_BOTH_BENCHMARK_CIS_INCLUDE_ZERO')]
    add_csv('risks.csv',[{'item':a,'status':b} for a,b in risks],['item','status'],'risks')
    write_json(OUT/'checkpoint.json',{'study':'BTC4H_NEXTCANDLE_V1_20261024','execution':'COMPLETE',
        'classification_candidates':2,'selected_model':selected,'real_orders':0,'trade_backtests':0,
        'independent_audit':'PASS','publication':'REMOTE_VERIFICATION_REQUIRED',
        'prior_15m_artifacts_modified':False,'unrelated_studies_touched':False})
    roles['checkpoint.json']='checkpoint'
    write_json(OUT/'provenance.json',{
        'source':'https://data.binance.vision/data/futures/um/monthly/klines/BTCUSDT/4h/',
        'official_source_definition':'https://github.com/binance/binance-public-data',
        'source_archives':48,'official_archive_checksums_verified':48,
        'normalized_data_sha256':selection['data_sha256'],'model_code_sha256':selection['model_code_sha256'],
        'protocol_sha256':selection['protocol_sha256'],'execution_mode':'RESEARCH_CLASSIFICATION_ONLY',
        'remote_input_reproduction':'PUBLIC_OFFICIAL_URLS_AND_SHA256; fetch monthly archives with data_loader.py',
        'raw_inputs_uploaded':False,'predictions':'Full gzip CSV for each phase plus24 plaintext monthlyCSV shards',
        'simple_cycle_return_formula':'NOT_APPLICABLE: no cycles or trading simulation',
        'public_archive':'https://github.com/jeh183000-art/-','archive_prefix':PREFIX,
        'parent_15m_commit':PARENT_COMMIT,'parent_15m_prefix':PARENT_PREFIX,
        'parent_15m_data_sha256':cross['reference_15m_sha256'],
        'cross_interval_input':'Official4h canonical before fit; 15m aggregation diagnostic only',
        'cross_interval_mismatched_windows':cross['mismatched_windows_count'],
        'cross_interval_target_color_mismatches':cross['all_8766_target_color_mismatches'],
        'environment_scope':'Isolated cloudLinux; no user Windows C:/D: orWSL access',
        'live_service':False,'current_2026_validation':False})
    roles['provenance.json']='provenance'

    monthly_rows='\n'.join(f"| {r['month']} | {int(r['scored'])} | {pct(r['accuracy'])} | {int(r['selected55'])} | {pct(r['accuracy55'])} |" for r in months.to_dict('records'))
    threshold_rows='\n'.join(f"| {'전체' if t==.5 else f'확신도 {t*100:.0f}% 이상'} | {int(th.loc[t,'scored_count']):,} | {pct(th.loc[t,'coverage'])} | {pct(th.loc[t,'accuracy'])} | {int(th.loc[t,'predicted_up_count'])} / {int(th.loc[t,'predicted_down_count'])} |" for t in [.5,.55,.6])
    dev_rows='\n'.join(f"| {label} | {int(dev.loc[name,'scored_count']):,} | {pct(dev.loc[name,'accuracy'])} | {dev.loc[name,'log_loss']:.6f} |" for name,label in [('logistic','로지스틱 회귀'),('hist_gradient_boosting','부스팅')])
    baseline_rows='\n'.join(f"| {label} | {pct(ev.loc[name,'accuracy'])} |" for name,label in [('historical_bullish_rate','과거 양봉 빈도의 다수 방향'),('same_color_as_current','현재 봉과 같은 방향'),('opposite_color_to_current','현재 봉과 반대 방향'),(selected,'선택된 로지스틱 모델')])
    boot_rows='\n'.join(f"| {'과거 양봉 빈도' if r['baseline']=='historical_bullish_rate' else '현재 봉 반대 방향'} | {r['accuracy_difference']*100:+.3f}%p | {r['ci95_lower']*100:+.3f} ~ {r['ci95_upper']*100:+.3f}%p |" for r in bootstrap.to_dict('records'))
    source_rows='\n'.join(f"| {r['open_utc'][:16].replace('T',' ')} | {r['official_open']:g} / {r['aggregated_open']:g} | {r['relative_volume_shortfall_vs_official']*100:.6f}% | 없음 |" for r in cross['mismatched_windows'])
    # The comparison CSV is authoritative; format robustly regardless of its optional extra columns.
    comparison_text=comparison.to_csv(index=False,lineterminator='\n')
    selected_acc=ev.loc[selected,'accuracy']; selected55=th.loc[.55,'accuracy']
    parent_base=f'https://github.com/jeh183000-art/-/tree/{PARENT_COMMIT}/{PARENT_PREFIX}'
    report=f"""# BTCUSDT 4시간봉 다음 봉 예측 V1 검증 보고서

## 판정

**2025년 전체 적중률은 {pct(selected_acc)}, 확신도 55% 이상에서는 {pct(selected55)}였다.** 현재 봉의 반대 색상을 다음 봉으로 예측하는 단순 기준은 {pct(ev.loc['opposite_color_to_current','accuracy'])}로 모델보다 높았다. 이번 설정에서는 4시간봉 모델의 유용한 예측 우위를 확인하지 못했다.

확신도 60% 이상에서는 **44개 중 27개 적중, 61.36%**였지만, 모두 **2025년 1분기의 양봉 예측**이었다. 1월 15개 중 10개, 2월 15개 중 9개, 3월 14개 중 8개가 맞았고 4~12월에는 해당 예측이 없었다. 이 작은 집중 표본을 보고 조건을 새로 선택하거나 안정적인 61% 모델로 판정하지 않았다.

분류 정확도 연구이며 주문·매매 백테스트·사이클은 0건이다. 수익률·PF·MDD는 계산하지 않았다. trades.csv와 cycles.csv는 이를 반영한 헤더만 있는 파일이다.

## 예측 정의와 조건

현재 4시간봉이 마감되면 바로 다음 4시간봉의 종가와 **그 다음 봉의 시가**를 비교한다. 시가보다 높으면 양봉, 낮으면 음봉, 같으면 보합이다. 보합을 시간축에서 삭제하지 않고 이진 학습·채점에서만 제외하도록 구현했다. 이번 원본에는 보합이 없었다.

이전 15분봉의 38개 특징, 모델 두 개, 모델 파라미터, 2024년 log loss 선택 규칙, 2025년 분기 평가, 55%·60% 확신도 기준을 유지했다. 입력과 목표 간격을 4시간으로 바꿨으며 공식 4시간봉을 사전에 기준 자료로 고정했다.

lookback을 **같은 봉 수**로 유지했으므로 96봉은 4시간봉에서 16일, 15분봉에서 1일이다. 같은 달력 시간의 정보량을 맞춘 실험은 아니다. 확률 보정 기간은 90일로 동일하지만 4시간봉에서는 경계 제거 후 매 분기 {int(split.calibration_samples.min())}개 표본으로 더 적다.

## 원본 데이터와 교차 점검

- Binance USD-M BTCUSDT 무기한 선물의 공식 4시간봉, 2022-01-01~2025-12-31 UTC, **{data_audit['rows']:,}개**.
- 월별 ZIP 48개의 공식 SHA256 전부 통과. 누락·중복·잘못된 OHLC·보합·거래량 0인 4시간봉은 모두 0개.
- 최초 96개 봉은 lookback 확보를 위해 특징 학습에서 제외. 보간·사후 삭제 없음.
- 2026년 자료는 수집·평가하지 않았다. 기존 Final OOS·수집기·15분봉 결과는 변경하지 않았다.

기존 15분봉 16개씩을 UTC 4시간으로 합산해 비교했다. **8,766개 봉의 양봉·음봉 정답은 전부 같았지만 4개 구간의 일부 가격 또는 거래량 계열 값이 달랐다.** 정확한 값 일치 검사는 FAIL이며 공식 4시간봉 자체의 무결성 검사 통과와 구분한다.

| 시작 UTC | 공식 4h 시가 / 15m 합산 시가 | 합산 거래량의 공식 4h 대비 부족분 | 봉 색깔 변경 |
|---|---:|---:|---|
{source_rows}

2023-11-10에는 저가도 달랐고, 2022-07-16·2023-11-10·2025-01-29에는 거래량·거래대금·체결 수·매수 체결량 계열의 차이가 있었다. 필드별 차이와 상대오차는 `data/aggregation_field_discrepancies.csv`에 있다. 원인을 확정하지 않았고 공식 4시간봉을 합산값으로 대체하지 않았다. 정답이 같더라도 입력 특징값에는 영향을 줄 수 있다.

## 학습과 평가

초기 학습 이력은 2022~2023년이다. 각 평가 분기 직전 90일을 기본 모델 학습과 분리된 확률 보정에 사용한다. 기본 모델 학습 정답의 확정 시각은 보정 시작보다 앞서고, 보정 정답의 확정 시각은 평가 시작보다 앞서도록 엄격히 제한했다. 표준화는 기본 모델 학습 자료에서만 학습한다.

2024년 네 분기의 결합 log loss로 모델을 선택한 후 선택 파일·코드·자료·설정 해시를 고정했다. 2025년에는 선택된 모델만 과거 자료로 분기마다 재학습했다. 이전 2025년 분기는 이후 분기의 학습에 들어갈 수 있지만 미래 분기의 정답은 사용하지 않는다. 2025년이 사용자의 모든 과거 연구를 통틀어 처음 보는 자료라고 주장하지 않는다.

### 2024년 개발 비교

| 후보 | 평가 봉 | 적중률 | log loss |
|---|---:|---:|---:|
{dev_rows}

**로지스틱 회귀**가 선택됐다. 2024년 결과는 모델 선택에 사용했으므로 최종 성능으로 해석하지 않는다. 2025년 결과를 본 후 파라미터나 확신도 기준을 조정하지 않았다.

### 2025년 평가

| 예측 조건 | 평가 봉 수 | 전체 중 비중 | 적중률 | 양봉 예측 / 음봉 예측 |
|---|---:|---:|---:|---:|
{threshold_rows}

55% 기준은 하루 평균 {int(th.loc[.55,'selected_count'])/365:.3f}개 봉에서 충족했다. 이 조건에서 양봉 예측 330개의 적중률은 54.24%, 음봉 예측 103개의 적중률은 40.78%였다. 모델의 확신도는 실제 정답률의 보장이 아니다.

| 같은 시점의 단순 기준 | 2025년 적중률 |
|---|---:|
{baseline_rows}

선정 모델의 전체 balanced accuracy는 {pct(ev.loc[selected,'balanced_accuracy'])}, log loss는 {ev.loc[selected,'log_loss']:.6f}, Brier는 {ev.loc[selected,'brier']:.6f}, AUC는 {ev.loc[selected,'roc_auc']:.6f}다. 고정 p=0.5 기준은 동률을 양봉으로 처리하므로 항상 양봉을 예측하는 것과 같은 적중률이다. 동일·반대 색상 기준의 0/1은 결정 규칙 표현이며 보정된 확률이 아니다.

### 월별 결과

| 월 | 전체 평가 수 | 전체 적중률 | 55% 기준 평가 수 | 55% 기준 적중률 |
|---|---:|---:|---:|---:|
{monthly_rows}

빈 표본의 적중률은 해당 없음으로 표시한다. 60% 조건의 분포는 `results/evaluation/threshold_60_distribution.csv`에 모두 포함했다.

## 15분봉과 비교

기존 15분봉의 2025년 적중률은 전체 **52.46%**, 55% 조건 **56.07%**였고, 4시간봉은 각각 **50.96%, 51.04%**였다. 55% 조건의 평가 표본은 15분봉 6,786개, 4시간봉 433개다. 이번 설정에서 4시간봉으로 바꿔 적중률이 개선되지는 않았다. 예측 대상 시간과 lookback의 달력 길이가 다르므로 완전히 같은 문제의 순위로 단정하지 않는다.

정확한 비교표는 `results/comparison_15m_4h.csv`, 기존 결과는 [동결된 15분봉 커밋]({parent_base})에 있다.

## 독립 감사와 불확실성

의미 있는 단위 검사 **{freeze['tests_passed']}개**가 통과했다. 별도 감사 코드가 원본과 예측 원장을 대조해 **{audit['check_count']:,}개 검사, 실패 {audit['failed_count']}개**를 확인했다. 정답 정렬·시각 집합·선택·분할 경계·코드와 자료 해시·확률 지표·월별 및 기준별 집계를 허용오차 1e-9로 대조했다. 파일과 규칙의 일치에 관한 검사이며 실세계 실행 이력 전체를 독립적으로 증명하는 것은 아니다.

UTC 날짜 전체를 묶어 1,000회 재표집한 추가 진단은 다음과 같다. 두 구간 모두 0을 포함한다. 이 결과를 모델 선택이나 재조정에 사용하지 않았다.

| 비교 기준 | 모델 정확도 차이 | 일 단위 부트스트랩 95% 구간 |
|---|---:|---:|
{boot_rows}

이는 날짜 간 독립성을 가정한 보조 진단으로, 여러 날 이어지는 의존성·모든 과거 연구 탐색·미래 시장 변화를 충분히 반영하지 못한다.

## 사용 범위와 재현

저장 모델은 2025년 4분기 평가용 연구 모델이며 현재 2026년 실시간 서비스가 아니다. 과거 2025-10-01 UTC 00:00~04:00 예측의 양봉 확률은 {smoke['p_up_conditional_non_doji']*100:.6f}%로 55% 기준에서는 관망이다. 독립 추론 명령과 원장 확률 차이는 약 2.79e-13이었다. 검사 파일은 `results/prediction_smoke/validation.json`이다.

매매 수익률·PF·MDD·실제 펀딩·슬리피지는 계산하지 않았다. 후속 매매 검증에는 기존 왕복 수수료 0.12% 가정, 실제 펀딩, 체결 지연·슬리피지를 반영해야 한다. 2026년 추가 검증과 실시간 운용은 이번 범위에 포함하지 않았다.

개발·평가의 완전한 원장을 각각 gzip CSV로 저장했고, 같은 예측 행을 읽기 쉬운 월별 CSV 24개로도 제공한다. 모든 후보·기준선 결과, 코드, 설정, 모델, 원본 출처·체크섬, 교차 주기 차이, 전체 감사도 포함했다. 원시 시세는 중복 업로드하지 않는다. 전체 감사 JSON은 gzip으로 제공하며 요약 JSON도 함께 있다. `manifest.csv`는 LF 줄바꿈이며 자기 자신을 제외한 모든 파일의 바이트 수와 SHA256을 기록한다.

실행 환경은 이 대화에 제공된 클라우드 Linux다. 사용자 Windows C:/D: 또는 WSL에 접근하지 않았다. Windows 재현 시 기존 지시에 따라 D 드라이브의 Codex_Research 하위에 작업·데이터·출력 폴더를 둔다.

공개 예정 경로: `{PREFIX}`. 원격 업로드·바이트 검증 상태와 커밋 SHA는 검증 후 별도 보고한다.

## 공식 근거

- [Binance 공개 데이터](https://github.com/binance/binance-public-data)
- [시간순 검증](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html)
- [확률 보정](https://scikit-learn.org/stable/modules/calibration.html)
- [전처리와 정보 누출 방지](https://scikit-learn.org/stable/common_pitfalls.html)
"""
    (OUT/'REPORT_KO.md').write_text(report,encoding='utf-8')
    roles['REPORT_KO.md']='statistics_report'
    with (OUT/'manifest.csv').open('w',newline='',encoding='utf-8') as stream:
        writer=csv.DictWriter(stream,fieldnames=['path','role','bytes','sha256'],lineterminator='\n')
        writer.writeheader()
        for name,role in sorted(roles.items()):
            path=OUT/name
            writer.writerow({'path':name,'role':role,'bytes':path.stat().st_size,'sha256':digest(path)})
    print(json.dumps({'batch':str(OUT),'prefix':PREFIX,'files':len(roles)+1,
        'bytes':sum(p.stat().st_size for p in OUT.rglob('*') if p.is_file()),'model':selected,
        'accuracy':selected_acc,'accuracy55':selected55,'publication_status':'LOCAL_COMPLETE_PENDING_REMOTE'},ensure_ascii=False))


if __name__=='__main__':
    main()
