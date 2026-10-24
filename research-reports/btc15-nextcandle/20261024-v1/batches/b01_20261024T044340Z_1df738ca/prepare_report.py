"""Create an explicit public research batch from the completed fixed experiment."""
from pathlib import Path
import csv
import datetime
import gzip
import hashlib
import json
import shutil
import pandas as pd

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'publication'
RESULTS = ROOT / 'results'
PREFIX = 'research-reports/btc15-nextcandle/20261024-v1/batches/b01_20261024T044340Z_1df738ca'


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def main():
    if OUT.exists():
        raise SystemExit('Preserve completed archive: publication already exists')
    OUT.mkdir()
    roles = {}

    def copy(source, destination, role='evidence'):
        target = OUT / destination
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / source, target)
        roles[destination] = role

    def add_csv(name, rows, columns, role):
        pd.DataFrame(rows, columns=columns).to_csv(OUT / name, index=False)
        roles[name] = role

    for name in ['model.py', 'data_loader.py', 'audit_predictions.py', 'test_model.py', 'prepare_report.py']:
        copy(name, name, 'strategy_code' if name == 'model.py' else 'verification_code')
    for name in ['README_KO.md', 'requirements.txt', 'preregistration.json', 'engine_freeze.json']:
        copy(name, name)
    copy('settings.json', 'settings.json', 'settings')
    for name in ['data_audit.json', 'download_manifest.json']:
        copy('data/' + name, name, 'input_provenance')
    copy('results/environment.json', 'environment.json', 'environment')
    for name in ['selection.json', 'candidates.csv', 'feature_columns.json',
                 'development_run.log', 'evaluation_run.log', 'independent_audit.md',
                 'independent_audit.metrics.csv', 'independent_audit.bootstrap.csv']:
        copy('results/' + name, 'results/' + name)
    audit = json.loads((RESULTS / 'independent_audit.json').read_text())
    summary = {k: v for k, v in audit.items() if k != 'checks'}
    write_json(OUT / 'results/independent_audit_summary.json', summary)
    roles['results/independent_audit_summary.json'] = 'audit'
    (OUT / 'results/independent_audit.json.gz').write_bytes(gzip.compress((RESULTS / 'independent_audit.json').read_bytes(), mtime=0))
    roles['results/independent_audit.json.gz'] = 'audit'
    frames = []
    for phase in ['development', 'evaluation']:
        for name in ['results.csv', 'thresholds.csv', 'monthly_metrics.csv', 'calibration_bins.csv', 'split_audit.csv', 'split_audit.json', 'metric_notes.json']:
            copy(f'results/{phase}/{name}', f'results/{phase}/{name}')
        frame = pd.read_csv(RESULTS / phase / 'results.csv')
        frame.insert(0, 'phase', phase)
        frames.append(frame)
        for path in sorted((RESULTS / phase / 'predictions_monthly').glob('*.csv')):
            relative = f'results/{phase}/predictions_monthly/{path.name}.gz'
            target = OUT / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(gzip.compress(path.read_bytes(), mtime=0))
            roles[relative] = 'prediction_ledger'
    pd.concat(frames, ignore_index=True).to_csv(OUT / 'results.csv', index=False)
    roles['results.csv'] = 'results_csv'
    copy('results/evaluation/monthly_selected_metrics.csv', 'results/evaluation/monthly_selected_metrics.csv')
    copy('results/evaluation/research_model.joblib', 'results/evaluation/research_model.joblib', 'model_artifact')
    copy('results/prediction_smoke/prediction.json', 'results/prediction_smoke/prediction.json')
    add_csv('trades.csv', [], ['trade_id', 'entry_time', 'exit_time', 'side', 'quantity', 'pnl'], 'fills')
    add_csv('cycles.csv', [], ['cycle_id', 'entry_time', 'exit_time', 'net_return'], 'cycles')
    add_csv('costs.csv', [{'status': 'NOT_APPLICABLE_CLASSIFICATION_ONLY', 'actual_orders': 0,
                         'trade_backtest_run': False, 'roundtrip_fee_assumption_for_future_study': 0.0012,
                         'funding_evaluated': False, 'slippage_evaluated': False}],
            ['status', 'actual_orders', 'trade_backtest_run', 'roundtrip_fee_assumption_for_future_study', 'funding_evaluated', 'slippage_evaluated'], 'costs')
    add_csv('risks.csv', [
        {'item': 'trading_returns_PF_MDD', 'status': 'NOT_EVALUATED'},
        {'item': '2026_accuracy', 'status': 'NOT_EVALUATED'},
        {'item': 'live_order_latency', 'status': 'NOT_EVALUATED'},
        {'item': 'confidence_60pct', 'status': 'ONLY_16_NON_DOJI_SAMPLES_IN_2025'},
        {'item': 'selected_2024_model', 'status': 'DEVELOPMENT_SELECTION_NOT_FINAL_PERFORMANCE'},
        {'item': 'same_2025_period_in_prior_research', 'status': 'NOT_CLAIMED_GLOBALLY_UNTOUCHED'},
        {'item': 'daily_bootstrap', 'status': 'HEURISTIC_NO_MULTI_DAY_DEPENDENCE_GUARANTEE'}],
        ['item', 'status'], 'risks')
    write_json(OUT / 'checkpoint.json', {'study': 'BTC15_NEXTCANDLE_V1_20261024', 'execution': 'COMPLETE',
              'classification_models_tested': 2, 'real_orders': 0, 'trade_backtests': 0,
              'independent_audit': 'PASS', 'publication': 'REMOTE_VERIFICATION_REQUIRED',
              'unrelated_studies_touched': False})
    roles['checkpoint.json'] = 'checkpoint'
    selection = json.loads((RESULTS / 'selection.json').read_text())
    write_json(OUT / 'provenance.json', {
        'source': 'https://data.binance.vision/data/futures/um/monthly/klines/BTCUSDT/15m/',
        'official_source_definition': 'https://github.com/binance/binance-public-data',
        'source_archives': 48, 'official_archive_checksums_verified': 48,
        'normalized_data_sha256': selection['data_sha256'], 'model_code_sha256': selection['model_code_sha256'],
        'protocol_sha256': selection['protocol_sha256'], 'execution_mode': 'RESEARCH_CLASSIFICATION_ONLY',
        'remote_input_reproduction': 'PUBLIC_OFFICIAL_URLS_AND_SHA256; fetch monthly archives with data_loader.py',
        'raw_inputs_uploaded': False, 'predictions': 'Every forecast is included in 24 monthly gzip CSV shards',
        'simple_cycle_return_formula': 'NOT_APPLICABLE: no cycles or trading simulation',
        'public_archive': 'https://github.com/jeh183000-art/-', 'archive_prefix': PREFIX,
        'environment_scope': 'Isolated cloud Linux workspace; no Windows C:/D: or WSL access',
        'live_service': False, 'current_2026_model_validation': False})
    roles['provenance.json'] = 'provenance'

    dev = pd.read_csv(RESULTS / 'development/results.csv').set_index('model')
    ev = pd.read_csv(RESULTS / 'evaluation/results.csv').set_index('model')
    th = pd.read_csv(RESULTS / 'evaluation/thresholds.csv')
    th = th[th.model.eq('hist_gradient_boosting')].set_index('threshold')
    months = pd.read_csv(RESULTS / 'evaluation/monthly_selected_metrics.csv')
    acc = ev.loc['hist_gradient_boosting', 'accuracy'] * 100
    acc55 = th.loc[.55, 'accuracy'] * 100
    rows = '\n'.join(f"| {r['month']} | {int(r['scored']):,} | {r['accuracy']*100:.2f}% | {int(r['selected55']):,} | {r['accuracy55']*100:.2f}% |" for r in months.to_dict('records'))
    report = f'''# BTCUSDT 15분봉 다음 봉 예측 V1 검증 보고서

## 판정

연구용 예측 모델을 구현하고 2025년 시간순 후속 평가까지 완료했다. 전체 양봉·음봉 적중률은 **{acc:.2f}%**이며, 사전 고정한 확신도 55% 이상 표본에서는 **{acc55:.2f}%**다. 현재 봉의 반대 색상을 예측하는 단순 기준의 **{ev.loc['opposite_color_to_current', 'accuracy']*100:.2f}%**보다 전체 적중률이 **{(ev.loc['hist_gradient_boosting', 'accuracy']-ev.loc['opposite_color_to_current','accuracy'])*100:.3f}%p** 높다. 우위의 크기는 작다. 수익성·실시간 운용·2026년 성능은 검증하지 않았다.

이 보고서는 분류 정확도에 관한 것이다. 거래·사이클은 0건이며 수익률, PF, MDD는 해당하지 않는다. trades.csv와 cycles.csv는 이 사실을 반영한 헤더만 있는 파일이다.

## 예측 정의

현재 15분봉이 확정되면 다음 15분봉의 종가가 **그 다음 봉의 시가**보다 높은지 예측한다. 다음 종가와 현재 종가의 비교가 아니다. 예측에는 현재 확정 봉과 과거 자료만 쓴다. 보합은 별도 기록하고 이진 정확도 분모에서 제외하므로 확률은 ‘보합이 아닐 때 양봉일 조건부 확률’이다. 미래 보합을 미리 알고 선택하는 매매 전략이 아니다.

## 데이터와 실험 조건

- 종목: Binance USD-M BTCUSDT 무기한 선물, 거래가격 15분봉.
- 입력: 2022-01-01~2025-12-31 UTC, 140,256개 봉. 공식 ZIP 48개의 SHA256 전부 확인.
- 누락, 중복, 잘못된 OHLC는 0건. 전체 원본의 보합 봉은 148개.
- 최초 96개 lookback 봉과 거래량 0으로 입력 비율이 정의되지 않는 12개 봉은 특징 생성에서 제외. 그중 평가 시점에 영향을 준 2024년 봉은 4개이며, 2025년에는 이런 제외가 없다. 결측 보간은 하지 않았다.
- 입력 38개: 가격 변화, 몸통·꼬리, 이동평균 대비 가격, 변동성, 거래량, taker 매수 비율, UTC 시간 인코딩. OI·호가·청산·ADX는 사용하지 않았다.
- 모델 2개: 표준화+로지스틱 회귀, 작은 HistGradientBoostingClassifier. settings.json과 코드 해시를 학습 전에 고정했다.
- 최초 이력 2022~2023년, 2024년 네 분기 개발 비교. 각 분기 직전 90일은 별도 확률 보정에 쓰고 그 이전 자료로 모델을 학습했다.
- 2024년 결합 log loss가 낮은 부스팅을 선택했다. 2025년에는 선정 모델만 분기마다 과거로 재학습했다. 앞선 2025년 분기는 이후 분기 학습에 들어갈 수 있지만 미래 분기는 들어가지 않는다.
- 학습 정답 확정 시각 < 보정 시작, 보정 정답 확정 시각 < 평가 시작. 무작위 시계열 분할이나 전체 자료 표준화를 하지 않았다.
- 2026년 자료는 수집·평가하지 않았다. 기존 연구 Final OOS와 수집기에는 접근하지 않았다.

## 2024년 모델 선택 결과

| 후보 | 평가 봉 | 적중률 | 확률 오차 log loss |
|---|---:|---:|---:|
| 로지스틱 회귀 | 35,110 | {dev.loc['logistic','accuracy']*100:.2f}% | {dev.loc['logistic','log_loss']:.6f} |
| 부스팅 | 35,110 | {dev.loc['hist_gradient_boosting','accuracy']*100:.2f}% | {dev.loc['hist_gradient_boosting','log_loss']:.6f} |
| 현재 봉 반대 색상 | 35,110 | {dev.loc['opposite_color_to_current','accuracy']*100:.2f}% | 확률 모델이 아닌 결정 규칙 |

2024년은 선택에 사용했으므로 최종 성능으로 해석하지 않는다. 총 예측 35,132개 중 보합 22개를 이진 평가에서 제외했다. 평가 결과를 보고 설정이나 기준을 조정하지 않았다.

## 2025년 사전 고정 모델의 시간순 평가

| 예측 조건 | 예측 수(보합 포함) | 양봉·음봉 평가 수 | 전체 예측 중 비중 | 적중률 |
|---|---:|---:|---:|---:|
| 모든 봉 | 35,040 | 35,024 | 100.00% | {acc:.2f}% |
| 확신도 55% 이상 | 6,791 | 6,786 | {th.loc[.55,'coverage']*100:.2f}% | {acc55:.2f}% |
| 확신도 60% 이상 | 16 | 16 | {th.loc[.60,'coverage']*100:.4f}% | {th.loc[.60,'accuracy']*100:.2f}% |

‘확신도’는 모델이 예측한 방향의 확률이며 실제 정답률의 보장이 아니다. 55% 기준은 2025년 하루 평균 {6791/365:.2f}개 봉에서 충족했다. 60% 기준은 표본 16개로 매우 적으며 높게 설정할수록 실제 적중률이 좋아진다고 단정할 수 없다.

| 같은 시점의 단순 기준 | 2025년 적중률 |
|---|---:|
| 과거 양봉 비율에 따른 다수 방향 | {ev.loc['historical_bullish_rate','accuracy']*100:.2f}% |
| 현재 봉과 같은 방향 | {ev.loc['same_color_as_current','accuracy']*100:.2f}% |
| 현재 봉과 반대 방향 | {ev.loc['opposite_color_to_current','accuracy']*100:.2f}% |
| 학습된 부스팅 모델 | {acc:.2f}% |

고정 p=0.5 기준은 확률 동률을 UP으로 처리하므로 표의 정확도가 항상 양봉 예측과 같다. 실제 무작위 동전 던지기 실험이 아니다. 동일/반대 방향 기준의 0/1 숫자는 결정 규칙 표현이며 보정된 확률이 아니다.

선정 모델의 전체 log loss는 {ev.loc['hist_gradient_boosting','log_loss']:.6f}, Brier는 {ev.loc['hist_gradient_boosting','brier']:.6f}, AUC는 {ev.loc['hist_gradient_boosting','roc_auc']:.6f}다. 양봉 예측 적중률은 {ev.loc['hist_gradient_boosting','bullish_precision']*100:.2f}%, 음봉 예측 적중률은 {ev.loc['hist_gradient_boosting','bearish_precision']*100:.2f}%다.

## 월별 안정성

| 월 | 전체 평가 수 | 전체 적중률 | 55% 기준 평가 수 | 55% 기준 적중률 |
|---|---:|---:|---:|---:|
{rows}

55% 기준 월별 적중률은 {months.accuracy55.min()*100:.2f}%~{months.accuracy55.max()*100:.2f}%로 일정하지 않았다. 월별 수치는 추가 모델 선택이나 재조정에 쓰지 않았다.

## 독립 감사와 불확실성

미래정보 누출·정답 정렬·누락·보합·과거 추론 방지 단위 검사 9개가 통과했다. 별도 감사 코드가 모델 코드를 불러오지 않고 원본 캔들과 예측 원장을 대조했으며 **3,261개 검사, 실패 0건**, 집계 허용오차 1e-9를 확인했다. 감사는 파일/시각 규칙을 확인하며 실세계 실행 이력 전체를 독립적으로 증명하는 것은 아니다.

2025년 동일 UTC 날짜 묶음을 1,000회 재표집한 추가 진단에서, 부스팅의 정확도 차이 95% 구간은 과거 양봉 비율 기준 대비 +1.782~+3.132%p, 반대 색상 기준 대비 **+0.031~+1.137%p**였다. 후자의 하단은 0에 매우 가깝다. 이는 일별 독립성을 가정한 보조 진단이며 여러 날 이어지는 의존성, 모든 과거 연구 탐색, 미래 시장 변화를 보장하지 않는다.

## 실행 결과물과 사용 범위

`model.py`는 수집한 CSV로 학습·평가하고 저장된 모델로 다음 봉 확률을 출력한다. `results/evaluation/research_model.joblib`는 2025년 4분기 평가용 모델이며 현재 2026년 실전 모델이라고 주장하지 않는다. 실제 시세 연결이나 자동 주문은 없다. 오래된 입력은 관망 처리하고, 모델이 만들어지기 전의 과거 입력을 해당 모델로 예측하는 것은 차단한다.

과거 2025-10-01 00:00 UTC 예측 명령을 다시 실행했을 때 원장 확률과의 차이는 4.4e-13 이내였다. 이 예에서는 양봉 약 46.62%, 음봉 약 53.38%여서 55% 기준에 따라 관망이다. 현재 시세에 대한 예측 예시가 아니다.

방향을 맞혀도 작은 양봉의 수익보다 큰 음봉의 손실이 클 수 있고 비용이 발생하므로, 분류 적중률로 수익성을 판단할 수 없다. 별도 매매 검증 시에는 사용자가 지정한 왕복 수수료 0.12%와 실제 펀딩, 체결 지연 및 슬리피지를 반영해야 한다. 이번에는 관련 손익을 계산하지 않았다.

## 재현성과 저장 범위

원본 ZIP은 공식 URL과 SHA256으로 재현 가능하다. raw 시세를 GitHub에 중복 업로드하지 않았다. 월별 예측 gzip CSV 24개에 모든 예측이 포함되며 코드, 설정, 모든 후보 결과, 학습 경계, 감사 결과 및 모델 파일을 함께 제공한다. `manifest.csv`는 파일별 바이트 수와 SHA256을 담는다.

실행 환경은 이 대화에 제공된 클라우드 Linux 작업 공간이다. 사용자 Windows C:/D: 또는 WSL에 연결하거나 저장 설정을 바꾸지 않았다. 시작 시 가용 용량 약 28.7 GiB를 확인했다. Windows에서 재현할 때는 기존 지시에 따라 D:\\Codex_Research 아래에서 실행한다.

공개 저장 경로: `{PREFIX}`. 원격 업로드 완료 여부와 최종 커밋 SHA는 실제 커밋의 모든 파일을 재조회·해시 대조한 뒤 별도로 보고한다. 본 폴더의 기존 파일을 덮어쓰지 않고 새 결과 폴더를 사용한다.

## 공식 근거

- Binance 공개 데이터와 선물 캔들 컬럼: https://github.com/binance/binance-public-data
- 시간순 평가: https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html
- 확률 보정과 확률값 해석: https://scikit-learn.org/stable/modules/calibration.html
- 전처리 및 미래정보 누출 방지: https://scikit-learn.org/stable/common_pitfalls.html
'''
    (OUT / 'REPORT_KO.md').write_text(report, encoding='utf-8')
    roles['REPORT_KO.md'] = 'statistics_report'
    with (OUT / 'manifest.csv').open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=['path', 'role', 'bytes', 'sha256'])
        writer.writeheader()
        for name, role in sorted(roles.items()):
            path = OUT / name
            writer.writerow({'path': name, 'role': role, 'bytes': path.stat().st_size, 'sha256': digest(path)})
    print(json.dumps({'batch': str(OUT), 'prefix': PREFIX, 'files': len(roles)+1,
                      'bytes': sum(p.stat().st_size for p in OUT.rglob('*') if p.is_file())}))


if __name__ == '__main__':
    main()
