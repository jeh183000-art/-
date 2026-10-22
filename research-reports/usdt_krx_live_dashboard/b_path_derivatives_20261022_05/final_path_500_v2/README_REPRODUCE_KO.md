# 재현·원격 검증 자료 안내

- 모든 전략 코드는 strategy_code_ref.json의 고정 커밋 f7f6e40b21dd30231f426a735687a7904f72cce1에 있습니다. 공통 검산기·통계·입력 로더의 정확한8a33… 경로와SHA는 external_dependencies.json에 있습니다.
- all_500_preregistration.json에 전체순서·조건·코드 해시가 있습니다. 22개 전략/검산/기준 코드에 변경이 없는지 registration_audit에서 확인했습니다. 원본 B의0.7%는 그대로입니다.
- Python3.12.0 / NumPy2.2.6 / Numba0.61.2 / pandas3.0.1을 보존했습니다. 전략·감사 Python 파일은 no-excuse 검사도 통과했습니다. 기존 실행환경에 패키지를 새로 설치하지 않았습니다.
- 데이터 원본은 D: 승인 탐색 사본에만 있습니다. source/margin SHA는 provenance.json에 있으며 INPUT_NOT_REMOTELY_REPRODUCIBLE입니다. 원시가격부터 재생하려면 같은 D: 입력이 필요합니다. 보호 Final OOS는 읽거나 게시하지 않았습니다.
- batch_publication_index.csv의10개 불변 커밋에서 manifest.csv, archive_parts.json, archive_inventory.csv와 full_ledgers.tar.partNNN을 받습니다. 순서대로 연결한 TAR의 SHA를 검사하고 각멤버SHA 및NPZ CRC를 확인합니다. 후보당10파일의 전체원장을 보존했습니다.
- 원장원본은 NPZ(전체 OPEN/CLOSE/SETTLEMENT 현금·증거금·평가)와 CSV.gz(체결·사이클·주문), exit_attribution.csv입니다. ledger_schema.json의 행/열 정의를 따릅니다. 최고후보의 비압축 CSV와211행 현금변동/위험극값 스냅샷은 이 폴더에 별도로 제공합니다. 스냅샷은 전체 분별원장을 대체하지 않습니다.
- operations/verify_actual_mdd.py, verify_registry_final.py, verify_all_metrics.py, study_diagnostics.py는 저장된 원장 대조만 합니다. code/bootstrap.py를 통해 새D: 검증 사본에서 실행하며 이미생성된 감사폴더를 덮어쓰지 않습니다. 연구 runner를 다시 실행할 필요가 없습니다.
- operations/codex_orchestration_v2.json은 Codex 도구 환경에서 단일워커·중복방지·게시/재조회 검증 순서를 복구하는 참조입니다. 일시적 GitHub 통신 오류만 같은 게시물로최대3회재시도하고 금융/해시 불일치는즉시중단합니다. Gateway나 수집기를 시작하지 않습니다.
- batch 내부 checkpoint는 게시 전 동결시점 상태이며 실제게시검증은 batch_publication_index.csv와 로컬 publication/*_verified.json으로 확인합니다. CONTROL1회는신규500개에포함하지않았습니다. 합성테스트도 실제시장거래로집계하지않았습니다.

- 월/분기 라벨은 YYYYMMDD와 ISO를 모두 인식하는 수정본입니다. REPORTING_DATE_CORRECTION.json과 diagnostics/period_totals_independent_validation.json을 확인합니다. 원래 배치의 보조 기간 라벨은 수정하지 않았고 이 최종본의 수정집계가 권위자료입니다. 재현 후 operations/verify_corrected_periods.py로 별도 파서 검산을 실행합니다. 금융모형 재실행은 필요 없습니다.
