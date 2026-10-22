# 저장 자료 검증 방법

1. strategy_code_ref.json의 고정 커밋에서 신규 연구 코드13개와 기존 공통 엔진·검산기·입력 로더를 받습니다. 설정과 비용은 변경하지 않습니다.
2. batch_publication_index.csv의 각 불변 커밋에서 manifest와 archive_inventory, ledger.part*.bin 및 직접CSV를 받습니다. 배치 폴더의 verify_archive.py로 연결 TAR의 모든 멤버 SHA와 NPZ CRC를 검사합니다. 분할 파일 이름과 정확한 연결 순서는 각 배치의 archive 관련 JSON/CSV를 따릅니다.
3. 원장은 batch_0001..0010/candidates/<ID>/에 복원할 수 있습니다. 각 후보의 cycles·fills·orders와 full_account_ledger, numeric_result, audit, residual, period_contribution, result를 보존합니다.
4. 새 D: 검증 복사본에서 code/bootstrap.py를 통해 operations/verify_actual_mdd.py, verify_registrations.py, verify_all_metrics.py를 실행합니다. 이미 있는 감사 폴더는 덮어쓰지 않도록 새 작업 사본을 사용합니다. 전략 runner를 재실행할 필요가 없습니다.
5. operations/resume_finalize_evidence.mjs는 기존400조건의 게시 인벤토리와 파일보존을 대조하고 저장된500조건을 점수순으로 정렬한 이번 후처리 코드입니다. 이미 생성된 산출물은 덮어쓰지 않습니다.
6. 원시 가격자료는 D: 공통 경로의 승인 탐색 사본에만 있습니다. provenance.json의 SHA로 식별하며 INPUT_NOT_REMOTELY_REPRODUCIBLE입니다. 원시 가격부터 완전 재현하려면 해당D: 입력이 필요합니다. 보호 Final OOS나 인증정보를 게시하지 않았습니다.
7. 순위는 완료사이클별 비용차감 순손익 / 최초 현물진입 명목금액 절대값 *100의 반올림 전 단순합입니다. 미청산은 별도이며 강제종료 가정 점수도 결과CSV에서 확인할 수 있습니다.
