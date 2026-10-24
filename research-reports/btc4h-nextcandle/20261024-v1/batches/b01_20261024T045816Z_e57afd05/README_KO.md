# BTCUSDT 4시간봉 다음 봉 방향 예측 V1

현재 4시간봉이 확정된 시점에, 바로 다음 4시간봉의 종가가 **그 다음 봉의 시가**보다 높은지 예측하는 연구용 모델이다. 예를 들어 UTC 00:00~04:00 봉 마감 후 04:00~08:00 봉의 양봉·음봉을 예측한다. 다음 종가와 현재 종가를 비교하는 문제가 아니다.

## 이번 연구의 범위

이전 15분봉 연구의 모델 두 개, 38개 특징 정의, 봉 수 기준 lookback, 확률 보정 및 모델 선택 규칙을 유지하고 입력·목표 간격을 4시간으로 바꿨다. 96봉은 15분봉에서 1일, 4시간봉에서는 16일이므로 같은 달력 시간의 정보량을 맞춘 실험은 아니다. 확률 보정 구간은 두 실험 모두 90일이며, 4시간봉에서는 경계 제거 후 매 분기 539개 표본이다.

공식 4시간봉 2022~2025년 자료로 초기 학습 후 2024년 두 모델을 비교했다. 2024년 log loss로 로지스틱 회귀를 선택해 고정하고 2025년 각 분기에 과거 자료만 사용해 평가했다. 설정을 바꾸거나 60% 확신도 결과를 보고 새 승자를 선택하지 않았다.

2025년 전체 적중률은 50.96%, 55% 확신도 이상 표본의 적중률은 51.04%였다. 60% 조건은 44개에서 61.36%였으나 **전부 2025년 1분기의 양봉 예측**이었다. 이 작은 집중 표본을 안정적인 61% 모델로 해석할 수 없다. 자세한 수치와 단순 기준 비교는 `REPORT_KO.md`에 있다.

## 데이터와 재현

Python 및 패키지 버전은 `environment.json`과 `requirements.txt`에 기록한다. Windows에서는 기존 사용자 지시에 따라 `D:\Codex_Research\btc4h_nextcandle` 아래에 작업·데이터·출력 폴더를 둔다. 이번 실행은 별도 클라우드 Linux 작업 공간에서 수행했으며 사용자 Windows C:/D: 또는 WSL에 접근하지 않았다.

공식 원본 수집:

```bash
python data_loader.py --start 2022-01 --end 2025-12 --out data
```

다시 학습·평가할 때에는 완료된 폴더를 덮어쓰지 말고 새 폴더를 사용한다.

```bash
python model.py --data data/BTCUSDT_4h_2022-01_2025-12.csv.gz --out rerun_results --phase development
python model.py --data data/BTCUSDT_4h_2022-01_2025-12.csv.gz --out rerun_results --phase evaluation
```

완료된 `results/`와 원본을 대상으로 독립 감사 옵션을 확인한다.

```bash
python audit_predictions.py --help
```

저장된 2025년 4분기 연구 모델의 과거 예측 재현:

```bash
python model.py --predict-model results/evaluation/research_model.joblib --data data/BTCUSDT_4h_2022-01_2025-12.csv.gz --asof 2025-10-01T00:00:00Z --out prediction_example
```

이 예는 2025-10-01 UTC 00:00~04:00 봉에 대한 과거 예측이다. 현재 시세 예측이나 실시간 주문 서비스가 아니다. 입력 봉 또는 요청 시각이 저장 모델의 가용시점보다 과거이면 추론을 차단하며, 오래된 입력의 예측은 관망 처리한다.

## 원본 주기 간 차이

공식 4시간봉을 사전에 기준 자료로 정했다. 기존 15분봉 16개씩을 UTC 4시간으로 합산한 자료와 비교했을 때 8,766개 봉의 색깔은 전부 같지만 4개 구간에서 시가·저가 또는 거래량 계열 값이 달랐다. `data/comparison_15m_to_4h.json` 및 두 상세 CSV에 차이를 그대로 남겼다. 공식 4시간봉에 합산값을 덮어쓰거나 해당 구간을 사후 삭제하지 않았다. 차이의 원인은 확정하지 않았다.

기존 15분봉 CSV를 가진 경우 선택적인 교차 점검:

```bash
python data_loader.py --start 2022-01 --end 2025-12 --out data --compare-15m ../btc15_nextcandle/data/BTCUSDT_15m_2022-01_2025-12.csv.gz
```

이 비교의 정확한 값 일치 검사는 FAIL이며 공식 4시간봉 자체의 품질 검사 실패와 구분한다. 공개 묶음에는 원본 시세를 중복 저장하지 않고 공식 다운로드 URL·체크섬·정규화 파일 해시를 포함한다.

## 결과물

- `results.csv`: 개발·평가의 모든 모델 및 기준선 결과
- `results/*/predictions.csv.gz`: 각 단계의 완전한 예측 원장
- `results/*/predictions_monthly/*.csv`: 월별로 쉽게 열람할 수 있는 동일 예측 행
- `results/comparison_15m_4h.csv`: 기존 15분봉과 4시간봉의 동일 기준 비교
- `results/evaluation/threshold_60_distribution.csv`: 60% 기준 표본의 시간·방향 분포
- `results/independent_audit_summary.json`, `results/independent_audit.json.gz`: 독립 감사 요약과 전체 검사
- `settings.json`, `preregistration.json`, `engine_freeze.json`: 사전 고정한 조건과 해시
- `manifest.csv`: 모든 공개 파일의 바이트 수 및 SHA256

보합 봉은 시간축에서 삭제하지 않고 분류 채점에서만 제외하도록 설계했다. 이번 4시간봉 원본에는 보합이 없었다. 모델의 출력 확률은 실제 정답률의 보장이 아니다.

분류 적중률은 매매 승률·수익률이 아니다. 매매 백테스트, 주문, 수익률, PF, MDD, 실제 펀딩·슬리피지 계산, 2026년 자료 평가 및 실시간 운용은 수행하지 않았다. 후속 매매 연구에서는 기존 가정인 왕복 수수료 0.12%와 실제 펀딩·체결 지연·슬리피지를 별도로 반영해야 한다.

공식 자료:

- https://github.com/binance/binance-public-data
- https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html
- https://scikit-learn.org/stable/modules/calibration.html
- https://scikit-learn.org/stable/common_pitfalls.html
