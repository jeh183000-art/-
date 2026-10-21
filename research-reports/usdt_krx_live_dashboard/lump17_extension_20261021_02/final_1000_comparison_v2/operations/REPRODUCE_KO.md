# 재현·검증 안내

이 연구는 실제 주문 없는 PAPER 탐색입니다. 기존500조건은 재계산하지 않았으며 새50조건씩 최대500개만 실행했습니다.

## 원본과 실행 코드

- 승인 입력: D:/Codex_Research/usdt_krx_live_dashboard/shared/approved_20261016_01/
- matched_simulation_bars.csv SHA-256: 62becd7d50e05bdcf47010cdcdfdd8178bbe2ef1d8099a84ab18fae8fea19fbd
- margin_schedule.csv SHA-256: 910816bc61c9d9b7361bec370e225bfeae9cde0f11b889265cb4409ecb9344b8
- 원시 시세는 공개 패킷에 중복 업로드하지 않았습니다. INPUT_NOT_REMOTELY_REPRODUCIBLE이며, 공개 결과만으로 원시 시세까지 포함한 재실행을 보장하지 않습니다.
- 최초17계약·170,000 USDT의 매매 실행기는 7198d4f47ea458580fb522f3b9ebf37e10ea178c 커밋의 lump17_sweep_20261021_01/shared/repair_v2/code/engine.py입니다. 추가진입은 없습니다.
- input_loader_frozen.py는 당시 입력 로더 참조본입니다. runner.py는 이 모듈의 load_arrays()만 사용하며, 모듈 안의 과거 연구용 실행 함수를 사용하지 않습니다. 재현 시 원래 shared/approved_20261016_01/ 배치를 유지해야 합니다.
- 신호·독립 검산기·bootstrap은 strategy_code_ref.json, 각 사전등록 settings.json의 code_sha256 및 feature_source_reference.json을 확인합니다.
- 실행 환경은 dependency_versions.json과 environment.json에 기록합니다. 이 작업에서 패키지를 설치하거나 환경을 갱신하지 않았습니다.

## 게시 파일 검증

각 배치 manifest.csv의 path/bytes/sha256을 모두 대조합니다. archive_parts.json에 기록된 full_ledgers.tar.partNNN을 번호 순서대로 바이너리 연결하면 원래 TAR가 됩니다. 연결 후 archive_bytes/archive_sha256을 확인하고 archive_inventory.csv의 각 member 크기·SHA를 대조합니다. 50조건별 계좌·결과 NPZ100개의 ZIP CRC도 검사했습니다. 검증 코드는 각 배치 verify_archive.py에 있습니다.

각 후보 numeric_result.npz는 trades/events/residual/risk/equity/extremes/orders 배열을 보존합니다. full_account_ledger.npz는 ledger[input_row, phase, field]이며 실제 없는 SETTLEMENT 평가는 NaN입니다. 각 배치 ledger_schema.json에 열·이벤트·phase 정의가 있습니다. 전체 cycles.csv.gz/fills.csv.gz/orders.csv.gz와 후보별 CSV는 같은 원장으로 대조됩니다. 입력 행 시각은 승인 원시 시세와 연결해야 합니다.

## MDD 검증

현재 낙폭은 누적 최고 평가자산에서 현재 평가자산을 뺀 값입니다. MDD는 현재 낙폭의 누적 최댓값입니다. 시작 평가자산3,000만원을 누적 최고값의 바닥으로 유지합니다. synthetic drawdown_tests_v2.json은 신규 최고점·손실 확대·회복·초기 손실을 수동 예상값과 대조했습니다. 현금 변조·MDD 초기화·정산 누락·롤오버 한쪽 누락도 검출했습니다.

validation_all_new_500.csv는 체결·현금 변화로 재구축한 독립 원장과 기존 Numba 검산 결과입니다. actual_mdd_audit/는 저장된 실제 MDD 열 자체가 감소하지 않는지 전체 평가시점에서 다시 검사한 결과입니다. anchor_audit/의 NPZ는 기존 두 후보의 평가행/phase별 최고 평가자산·현재 낙폭·누적 MDD를 별도로 보존합니다.

## 재실행 보호

기존 폴더에서 스크립트를 다시 실행해 원본을 덮어쓰지 마세요. 재계산이 별도로 승인되면 D:의 새 연구 폴더에 해당 버전 코드·사전등록·검증 영수증을 복사하고 원본 입력은 해시로 참조합니다. 먼저 C:와D:각10GiB 이상을 점검하고 bootstrap.py로 프로세스 TEMP/TMP/cache를D:로 지정합니다. 기존 worker.lock 및 동일 워커를 확인한 후에만 신규 연구를 실행합니다. 이 작업 종료 뒤에는 백테스트·수집기·Gateway·예약 작업을 추가 실행하지 않습니다.

주 순위는 완료 사이클별 비용 차감 순손익/현물 최초 진입 명목 절대값×100의 반올림 전 단순 합계입니다. 미청산 손익을 더하지 않으며, 마지막 관측 종가 가정청산은 실제 체결 검증이 아닌 보조 지표입니다. 역배 차입·차입비, 과거 호가·체결 잔량, 분중 손실은 미검증이며7월6일~8월2일 증거금 일정에는 인접 공식 일정 추론이 포함됩니다.
