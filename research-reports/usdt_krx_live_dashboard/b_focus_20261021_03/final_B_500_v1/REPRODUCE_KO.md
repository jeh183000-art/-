# 결과 검증·재현 방법

이 연구는 기존 B의 사본에서 50조건씩 10배치, 신규500조건만 실행했습니다. 기존1,000조건과 A/C/D는 재실행하지 않았습니다. 실제 주문은 없습니다.

1. strategy_code_ref.json에서 공통코드 커밋/경로와 등록기 수정 오버레이를 확인합니다. shared/B_baseline_and_code_v1/code의 build_B.py는 등록기 수정 전 보존본이므로 registration_inventory_revision이 가리키는 검증된 build_B.py를 적용해야 합니다. 매매 엔진과 독립 검산기는 common_engine의 기존 불변 버전입니다.
2. batch_publication_index.csv의10개 결과 커밋/폴더와 registration_audit/all_500_registration_checks.csv의 실행 전 등록 커밋을 사용합니다. 각 결과 폴더 manifest.csv로 모든 파일의 바이트와SHA-256을 비교합니다. 조건표는 각 사전등록 settings.json 및 이번 settings_new_500.json에 있습니다.
3. 전체 현금·증거금·체결 원장은 배치별 archive_parts.json에 나열된 full_ledgers.tar.partNNN의 바이트를 이름 순서대로 이어붙여 복원합니다. 합친 TAR의SHA 및 archive_inventory.csv의 모든 구성파일SHA를 검증합니다. operations/verify_archive.py는 원장TAR의 모든 멤버와 NPZ의CRC를 검사하는 코드입니다. 원본 대신 D:의 새 검증 폴더에서 사용하십시오.
4. full_account_ledger.npz에는 모든 OPEN/CLOSE/정산 평가시점의 계좌 상태가, numeric_result.npz에는 수치 원장과 미청산 상태가 있습니다. ledger_schema.json이 열 정의입니다. CSV 체결·사이클·주문 원장은 압축을 풀면 직접 확인할 수 있습니다. 최고 후보의 CSV는 이번 폴더에 별도로 제공합니다.
5. Python3.12.0, numpy2.2.6, numba0.61.2, llvmlite0.44.0, pandas3.0.1을 유지합니다. 기존 D:연구의 code/bootstrap.py는 프로세스 TEMP/TMP/TMPDIR와 캐시를 D:로 지정합니다. 원장 재검산은 code/validation2.py와 기존 공통 audit.py가 수행합니다. MDD 독립 검사 및 사전등록 대조 코드는 operations/에 있습니다. 이미 존재하는 불변 결과를 덮어쓰지 않도록 재검산 결과는 새 연구 사본/검증 출력 폴더에 저장해야 합니다.
6. 승인된 시장 원시 입력은 D:공통 영역에 한 번 보존하며 공개GitHub에 반복 업로드하지 않았습니다. provenance.json의 source_sha256와 margin_sha256을 검증해야 실제 시세 재실행이 가능합니다. 입력을 내려받을 수 없는 공개 환경에서는 INPUT_NOT_REMOTELY_REPRODUCIBLE입니다. 공개 원장·검증코드·해시를 확인할 수 있지만 공개파일만으로 원시시세를 포함한 완전한 시뮬레이션 재현이 가능하다고 주장하지 않습니다.
7. 원본, 완료500조건, 기존B, 보호Final OOS를 수정하지 않습니다. 실행한 조건만500개이며 더 진행하려면 새로운 사전등록이 필요합니다. Gateway, 예약작업, 수집기는 연구 실행 대상이 아닙니다.

점수 = 각 완료 사이클의 (두 포지션 비용 차감 순손익 / 최초 현물 진입명목 절대값 ×100)을 반올림 전에 단순합산합니다. 잔여평가손익은 주점수에서 제외하고 강제청산 가정 보조점수로 별도 기록했습니다. 역배는 차입 미검증 이론값이며, 분봉 시가 대용체결과 증거금 일정 추론 등 제한사항은 REPORT_KO.md 및 provenance.json을 확인하십시오.
