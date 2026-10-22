# 재현·검증 안내

작업 상태는 STOPPED_RULE_DEDUP_AUDIT_FAILURE입니다. 500회 실행/499고유규칙이며 금융검증PASS·중복검증FAIL을 구분합니다. 기존원장재계산없이읽기전용진단을마쳤습니다. 코드/조건은바뀌지않았습니다.

원전략 및 금융검산 코드: strategy_code_ref.json의 cfe7b2f7245e626b7707391e03e1e6372d950f63, shared/code_v1/code/. 외부의 공통금융검산기·입력로더는 external_dependencies.json의 버전/해시 참조입니다. 패키지변경없음: Python3.12.0, NumPy2.2.6, Numba0.61.2, llvmlite0.44, pandas3.0.1(기존로더만). 연구프로세스는 -X utf8 -u -B code/bootstrap.py 로 실행했습니다. 모든 TEMP/TMP/TMPDIR/캐시/로그는 D: 프로세스경로입니다. Windows전역설정변경없음.

원시는 D:/Codex_Research/usdt_krx_live_dashboard/shared/approved_20261016_01/ 의 matched_simulation_bars.csv 및 margin_schedule.csv이며 해시는 provenance.json입니다. 전체입력이원격에없어원시가격부터완전히독립재실행했다는주장은하지않습니다. 보호OOS를열지않습니다.

배치별모든체결/사이클/현금/증거금NPZ와감사자료는batch_publication_index.csv의불변commit/path에있습니다. 각배치 full_ledgers.tar.partNNN을이름순바이너리연결하고archive_parts.json의전체SHA256/크기검사후TAR를열어archive_inventory.csv의모든멤버SHA256과NPZ ZIP CRC를확인합니다. 후보별full_account_ledger.npz는[입력행,OPEN/CLOSE/SETTLEMENT,11필드]이며스키마는각배치ledger_schema.json. 원본CSV를배치별로중복저장하지않았습니다.

상위후보 작은비압축 *_cycles.csv/*_fills.csv/*_orders.csv와 *_cash_margin_snapshot.csv를바로읽을수있습니다. 스냅샷은모든현금변화와선택한위험극값이며전체369010평가시점계좌원장을대체하지않습니다. 비용스냅샷에는기지급비용과완료사이클비용이별도입니다. cost_stress/의4bp결과는주순위와분리합니다.

검산코드는operations/all_rules_prefix.py, audit_final_metrics.py(중복발견시실패한원본), audit_final_metrics_v2.py(실패를보존하며금융영향만진단), forensic_saved_ledgers.py입니다. 기존출력을덮어쓰지않는exclusive정책이므로재검토시새D:검증출력폴더를사용하고기존거래시뮬레이션은재시작하지않습니다. 불변전략코드의 runner.py와build_structural.py는완료배치를다시실행하기위한명령이아닙니다. 후속신규연구전에는균형필터도메인/비활성파라미터정규화오류를수정·별도등록해야하며이번작업에서원본생성기를변경하거나재개하지않았습니다.

청산이벤트 bit1은기존 gap_recovery 열별칭으로남아있지만 구조별관측상태청산(이동중심복귀·추세전환포함)입니다. bit4 순손익익절/손절, bit8 시간, bit16 정체, bit32 순이익추적. 엄격한 단독·동시횟수는각배치 strict_exit_trigger_ledger.csv입니다.

인접조건은같은구조의설정변화일뿐독립검증이아닙니다. 평균현물노출은매칭관측CLOSE평가의평균이며관측되지않은공백가격을채워달력평균으로만들지않았습니다. 월/분기는청산거래일기여이며0거래월의0은집계값입니다.

주순위 ranking_completed_unique.csv는455개완료규칙만점수순정렬했고0완료44개를제외합니다. all_unique_rules_499.csv는중복제외499개전체목록이며순위파일과구분합니다.
