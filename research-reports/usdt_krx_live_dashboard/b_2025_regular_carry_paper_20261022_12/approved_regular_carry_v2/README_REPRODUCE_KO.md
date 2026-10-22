# 재현

기존 D: 원본과 정규화 자료를 다시 다운로드하지 않는다. common.py의PRIOR는 기존4d9b7d60… 연구 폴더이고 BOUNDARY는 e8078bd7… 사전 감사 폴더다. 원본 시세는 재배포 허가가 없어 GitHub에 넣지 않았다.

1. shared_quote_account_module_refs.json과 strategy_code_ref.json의 고정 원격 모듈을 해시로 대조한다. bootstrap은 새 코드와 기존 불변 코드만 사용하며 일시파일·캐시는 D:로 둔다.
2. prepare_carry.py로 입력 무결성과 후보 경계를 재검사한다. settings.json의 승인 가정을 보존한다.
3. test_carry.py로 주말 이월·익일 재평가·1분 뒤 체결·분기 재개를 검증하고 코드/입력 해시를 execution_hashes.json 형식으로 고정한다.
4. run_carry_quarter.py 1 →2 →3 →4로 순차 실행한다. 각 분기는 기존 분기 폴더가 있으면 재실행을 거절하고 전 분기 상태를 이어받는다.
5. finalize_carry.py 및 post_carry.py는 저장 원장만 집계·대조한다. 완료 조건을 재계산하거나 바꾸지 않는다.
6. manifest와 전체 평가 gzip의 압축/비압축 SHA-256을 대조한다. CONDITIONAL_CHAIN의 별도 계좌들을 ANNUAL_PREFIX 하나의 연간 수익으로 합치지 않는다.

기존 원본·결과·설정·보호된Final OOS는 수정하지 않는다. 원본 데이터가 D:에만 있어 공개 패키지 단독의 완전한 원문 재현을 주장하지 않는다.
