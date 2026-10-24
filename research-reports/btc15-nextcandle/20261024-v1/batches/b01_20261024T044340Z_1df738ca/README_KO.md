# BTCUSDT 15분봉 다음 봉 방향 예측 V1

## 무엇을 예측하나

현재 15분봉이 확정된 시점의 정보로 바로 다음 15분봉의 `종가 > 시가` 여부를 예측한다. 다음 종가와 현재 종가를 비교하는 문제가 아니다. 출력은 보합이 아닌 다음 봉에 대한 양봉 조건부 확률, 음봉 조건부 확률, 예측 방향 및 55% 신뢰도 기준 충족 여부다. 확률은 추정치이며 적중을 보장하지 않는다.

이 프로젝트는 분류 모델의 연구용 첫 버전이다. 거래 주문, 실시간 서비스, 매매 백테스트는 실행하지 않는다. 다음 봉의 첫 체결 시가에 실제로 주문할 수 있다고 가정하지 않는다. 기존 연구의 Final OOS나 수집기에는 접근하지 않는다.

## 고정된 실험

- Binance USD-M BTCUSDT 무기한 선물의 공식 15분봉 월별 자료를 사용한다.
- 입력 자료는 2022-01-01부터 2025-12-31까지이며 원본 ZIP 48개의 공식 SHA256을 확인한다.
- 현재 봉을 포함한 과거의 가격 변화, 캔들 몸통과 꼬리, 이동평균 대비 가격, 변동성, 거래량, 매수 체결량 비율, 시간 정보 등 38개 특징을 만든다.
- 후보는 로지스틱 회귀와 작은 히스토그램 부스팅 모델 두 개뿐이다. 세부 설정은 `settings.json`에 사전 고정했다.
- 최초 학습 이력은 2022~2023년이다. 각 평가 분기 직전 90일을 확률 보정에 쓰며, 그보다 앞선 자료로 기본 모델을 학습한다.
- 2024년 네 분기를 시간순으로 예측한 뒤, 전체 확률 오차(log loss)가 작은 모델을 선택한다.
- 선택을 고정한 뒤 2025년 네 분기를 순서대로 평가한다. 매 분기 과거로 재학습하므로 이전 2025년 분기는 이후 분기의 학습에 들어갈 수 있다. 미래 분기의 정답은 사용하지 않는다.
- 2026년 자료는 이번 실험에서 수집하거나 평가하지 않는다.
- 모델 학습/보정 경계에서는 해당 시점에 정답이 아직 알려지지 않은 행을 제외한다.
- 보합은 시간축에서 삭제하지 않는다. 예측을 기록하고, 양봉/음봉 이진 분류 점수 계산에서만 제외한다.
- 자신감 50%, 55%, 60% 세 기준을 모두 보고한다. 결과를 본 뒤 기준을 고르거나 바꾸지 않는다.

## 실행 환경

Python 3.11 이상을 권장한다. 정확한 실행 버전은 결과의 `environment.json`을 참고한다. 필요한 패키지는 `requirements.txt`에 있다.

Windows 재현 시 작업 폴더와 데이터/출력/임시 경로를 모두 사용자가 지정한 `D:\Codex_Research\btc15_nextcandle` 아래에 둔다. C: 또는 WSL 디스크로 대체하지 않는다. 이번 최초 실행은 대화에 제공된 별도의 클라우드 Linux 작업 공간에서 수행했으며 사용자의 Windows C:/D:나 WSL 상태를 확인하거나 변경하지 않았다.

공식 자료 수집:

```bash
python data_loader.py --start 2022-01 --end 2025-12 --out ./data
```

학습·평가 재현(새 결과 폴더 사용):

```bash
python model.py --data data/BTCUSDT_15m_2022-01_2025-12.csv.gz --out rerun_results --phase development
python model.py --data data/BTCUSDT_15m_2022-01_2025-12.csv.gz --out rerun_results --phase evaluation
```

저장 모델의 과거 시점 예측 재현(현재 시세 예측이 아님):

```bash
python model.py --predict-model results/evaluation/research_model.joblib --data data/BTCUSDT_15m_2022-01_2025-12.csv.gz --asof 2025-10-01T00:00:00Z --out prediction_example
```

공개 패키지는 월별 예측 CSV를 gzip으로 저장한다. 원래 학습기가 만든 전체 원장은 같은 행을 담는 월별 파일의 결합으로 확인할 수 있다. 보고서의 예측 횟수는 봉 수이며 거래 횟수가 아니다. 결과 폴더를 덮어쓰지 않도록 학습기는 완료된 개발/평가의 재실행을 거부한다.

모델의 모든 명령행 옵션:

```bash
python model.py --help
```

연구 결과를 재현할 때에는 원본을 수정하지 않은 새 결과 폴더를 사용한다. 데이터 출처 및 체크섬은 `download_manifest.json`, 원본 품질 검사는 `data_audit.json`, 사전 설정은 `settings.json` 및 `preregistration.json`에 기록한다.

## 결과 해석

적중률은 평가 대상의 실제 양봉·음봉과 방향 예측이 일치한 비율이다. 양봉을 항상 예측하거나 현재 봉의 반대 방향을 예측하는 단순 기준과도 비교해야 한다. 55% 이상 확신한 표본만 보면 적중률이 달라지므로, 해당 표본 수와 전체에서 차지하는 비율을 함께 확인한다.

모델이 60%를 출력했다고 실제로 60% 맞는 것은 아니다. `calibration_bins.csv`는 예측 확률 구간별 실제 양봉 빈도를 확인하기 위한 자료다. 2024년은 모델 선택에 사용했으므로 그 결과를 최종 실력으로 해석하지 않는다. 2025년 역시 이 V1의 시간순 후속 평가일 뿐, 사용자의 모든 과거 연구를 통틀어 처음 보는 자료라고 주장하지 않는다.

방향 예측 적중률은 매매 승률 또는 수익률이 아니다. 수익성 판단에는 별도의 진입/청산 조건, 실제 체결 지연, 사용자가 정한 왕복 수수료 0.12%, 실제 펀딩, 슬리피지가 필요하다. 이 분류 실험에는 PF, MDD, 수익률이 없다.

## 공식 자료

- Binance 공개 데이터 및 컬럼 설명: https://github.com/binance/binance-public-data
- Binance 데이터: https://data.binance.vision/
- 시간순 검증: https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html
- 확률 보정: https://scikit-learn.org/stable/modules/calibration.html
- 데이터 누출 방지: https://scikit-learn.org/stable/common_pitfalls.html

결과 CSV와 모든 예측 원장, 사용 코드 및 검증 보고서는 지정된 GitHub 연구 경로에 함께 보관한다. 공개 원시 시세 ZIP은 중복 업로드하지 않으며 공식 다운로드 URL과 SHA256으로 재현한다. 비공개 계좌 자료나 인증 정보는 사용하지 않는다.
