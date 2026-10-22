# 재현 순서

원문626개와 정규화 입력은 기존 D: 감사 폴더를 읽기 전용으로 사용한다. 새로 다운로드하지 않는다. common.py의SOURCE와OLD는 실제 로컬 보관 경로이며, OLD/validation2.py는 strategy_code_ref.json의 고정 원격 SHA와 같아야 한다. 원본 가격 및 전체 정규화 자료는 재배포 허가 미확인으로 이 GitHub 패키지에 포함하지 않는다.

1. 별도의 새 D: 연구 디렉터리에서 code/bootstrap.py prepare_quotes.py로 원본·정규화·감사 파일의 무결성과 관측 구간을 확인한다.
2. settings.json과 실행 코드 해시·segments 입력 해시를 execution_hashes.json 형식으로 고정하고 test_regressions.py를 실행한다.
3. run_quarter.py 1,2,3,4를 순서대로 한 번씩 실행한다. 각 분기는 이전 checkpoint를 이어받으며 기존 완료 분기는 재실행을 거절한다.
4. finalize_results.py → post_checks.py → enrich_marks.py 순서로 보고용 원장을 검산한다. enrich_marks는 체결을 다시 계산하지 않고 기존 원장에 최고자산·현재낙폭·누적MDD 열을 추가한다.
5. manifest 파일별 바이트·SHA-256과 원격 blob를 확인한다. 압축 평가 원장은 archive_verification.json의 압축 및 비압축 해시로 검증할 수 있다.

주 검증·대조군 둘뿐이며 임계값 최적화는 없다. scope=ANNUAL_CHAIN_PREFIX는 한 계좌의 검증 가능한 앞부분, INDEPENDENT_EPISODE는 서로 다른 관측 구간의 별도 실험이다. 같은 계좌로 합산하거나 미청산 손실을 지운 연간 수익률로 쓰지 않는다.
