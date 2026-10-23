# B 전략 2025 누락분봉 조건부 PAPER 개선 v3

## 무엇을 개선했나

기존 GitHub 기준 커밋 `72cc8eb39044f0ccc056cf9e1b1ffe637e5dbf74`의 B 전략에 대한 **독립 비교 실행기**이다. 기존 코드나 원본을 덮어쓰지 않는다.

- **0분(엄격), 1분, 2분 누락 허용**을 처음부터 고정한 민감도 비교로 실행한다. 성적이 가장 좋은 조건을 고르는 최적화가 아니다.
- 실제 관측 가격만 사용한다. 없는 분봉의 가격, 청산, 손익을 생성하지 않는다.
- 장중 1~2분 누락 시 포지션을 유지하되, 누락된 시간에 진입·청산 주문을 체결하지 않는다.
- 누락 직전 미체결 주문은 취소한다. 첫 재관측 가격에서 보유 포지션의 청산 조건만 재검사하고 다음 실제 연속 관측가격에 모의 체결한다.
- 누락을 통과한 완료 거래는 `gap_exposed=true`로 구분한다. **검증된 실제 거래나 안정적 수익이 아니다.**
- 같은 공식 참조 월물의 정상 정규장 종료 후 다음 공식 거래일 연결을 유지한다. 정규장 시작/끝 1~2분 누락도 별도 표시한다.
- 공식 **참조** 월물이 바뀌는 경계, 공식 거래일이 빠진 경계, 2분 초과 누락 등은 여전히 추적 중단한다.
- 전략 B 조건(−0.97%/＋0.85% 진입, 신호 기준 유리한 0.6%p 회복), 수량(17계약·170,000 USDT), 3천만원 선물 초기 현금, 비용 및 보조익절 대조군을 변경하지 않는다.
- 같은 2025년 로그에서 원본 실행값인 **47연결구간·199정상 이월·26진입·8완료·18미청산** 및 첫 거래 +1,006,055.45원을 엄격 모드가 재현하지 못하면 `AssertionError`로 중단한다. 결과를 채택하지 않는다.
- 3개 누락 민감도 × 2개 고정 전략 버전의 결과·전체 관측 평가 원장·신호·체결·미청산 기록을 새 D: 폴더에 생성한다.

## 실행 전제

2025년 가격 원문과 정규화 자료가 이미 사용자의 **D 드라이브**에 있어야 한다. **이 ChatGPT 실행 환경에는 해당 원본이 없으므로 실제 2025년 수익률을 계산하지 않았다.** 제공한 두 테스트는 합성 가격 테스트다.

절대 미검증 사항: 제3자 로그 선물 계약·거래소·시간대·호가 의미, 주문 깊이·잔량, 테더 숏 차입, 선물 증거금, 야간 위험, 실제 월물 교체, 일일정산. 이 새 연구는 **2025년 1년 공식 검증이 아니다.**

## PC에서의 실행 (Codex)

세 파일 `gap_policy.py`, `run_gap_sensitivity.py`, `test_gap_policy.py`, `test_gap_engine.py`를 동일한 새 D: 연구 코드 폴더에 둔다.

먼저 합성 테스트 두 개를 실행한다.

```powershell
python -B test_gap_policy.py
python -B test_gap_engine.py
```

다음은 예시이며, 실제 PC 파일이 있음을 Codex가 읽기 전용으로 확인해야 한다.

```powershell
python -B run_gap_sensitivity.py `
  --input "D:/Codex_Research/usdt_krx_live_dashboard/studies/b_2025_quote_paper_20261022_11/data_local/segments.jsonl" `
  --official "D:/Codex_Research/archive/c_drive_migration_20261020/codex_workspace/files-pasted-by-the-user-codex/outputs/usdt_krx_live_dashboard/data/krx_2025_full_1m/contract_selection.csv" `
  --out "D:/Codex_Research/usdt_krx_live_dashboard/studies/b_2025_gap_sensitivity_v3"
```

기존 D: 입력은 읽기만 한다. `--out` 폴더가 이미 존재하고 내부 파일이 있으면 실행을 거부한다. C: 캐시가 쌓이지 않도록 작업 환경의 TEMP/TMP/PYTHONPYCACHEPREFIX도 D:로 설정한다.

## 분석 필독

1. `sensitivity_comparison.csv`의 `conditional_completed_return_pct_sum_NOT_ANNUAL`은 **서로 별개의 초기화된 구간**에서 얻은 완료 거래 수익률의 진단 합계이며 실제 한 계좌의 연간 수익률이 아니다.
2. `annual_prefix_last` 이후는 한 계좌의 잔여 경로 미검증이다. 연말 자산이나 승률을 만들어내지 않는다.
3. `gap_exposed=true` 청산은 결측 시간에 진입·익절·매매 가능성이 있었는지 모르는 것이므로 보수적 검증 표본과 분리한다. 미청산 평가손실을 별도 보고한다.
4. `strict`의 수가 과거 26/8/18과 맞지 않으면 코드·원장 대조 전까지 어떤 개선 성과도 발표하지 않는다.
5. 월물 변경 시점의 가격을 소급하거나 임의 롤오버하지 않는다.
6. 코덱스는 실수익 검증 결과와 CSV 원장, 해시를 **사용자의 GitHub 저장소** 새 연구 폴더에 커밋·푸시한다. 제3자 원문 데이터는 재배포 허용이 확인되지 않았으므로 업로드하지 않는다.
