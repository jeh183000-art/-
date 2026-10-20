# OpenClaw 기존 환경 복구 실행 결과

결과: **Gateway 연결 복구 및 5분 이상 지속성 검증 통과**. 연구와 수집기는 재개하지 않았다.

## 핵심 결과

| 항목 | 결과 |
|---|---|
| Companion | 2026.9.8-1, 기존 release 프로필로 재실행 |
| EnableMcpServer | false → true |
| EnableManagedLocalGatewayAutoRepair | true → false, 최종 파일 재조회 확인 |
| 나머지 설정 | 모든 필드 동등, 암호화 문자열 보존 |
| MCP 인증 | initialize/tools/list HTTP 200, 명령 59개 |
| Gateway | 기존 2026.9.6, PID 300, 기존 사용자 서비스 |
| 기존 자격 연결 | operator 및 node Connected, node Paired |
| 공식 health RPC | ok=true, main 확인, durationMs=5 |
| 임시 WSL 셸 없는 지속성 | 314.567초 관찰 통과 |
| Chrome Owner | 기존 Owner 메뉴 및 연결 정상, Owner Error 없음 |
| 일반 대화 | 활성 3개 실제 메시지 접근, 과거 압축 보관본 7개 읽기 검증 |
| 세션 키 | 이전 검증 백업 16개와 현재 16개 전부 일치, 누락 0 |
| 예약 작업 | 저장 4개 중 개별 활성 3개 보존, 전역 유지보수로 실행 차단 |
| 실행 이력 | 작업 실행 기록 107건 → 107건, 새 예약 실행 없음 |
| 오류 | 관찰 구간 EIO·SQLite 손상·서비스 종료 신호 0 |

## 실제 수행한 변경

지정 커밋 5231d9a645d719c6838bc2e9f2512e39312956d4의 MCP_BOOTSTRAP_OFFLINE_KO.md 전체를 읽었다. 실행파일 경로, 버전, 사용자·세션·PID·시작시각, 기존 바로가기와 단일 release 프로필을 확인했다. 정상 창 닫기를 먼저 시도했으나 프로세스가 남아 있어 대상을 다시 확인한 뒤 기존 Companion PID 15788 하나만 종료했다. WSL 전체 종료나 프로세스 트리 종료는 하지 않았다.

앱 프로세스 0개 상태에서 2,035바이트 설정과 기존 인증 파일 2개를 D:의 제한된 private 폴더에 백업하고 해시를 대조했다. 기존 JSON 텍스트의 두 Boolean만 최소 치환했다. 동일 볼륨 임시파일에 기존 ACL을 적용한 뒤 교체했다. 첫 File.Replace 호출은 빈 백업 경로 처리 오류로 원본을 변경하지 못했으며, 명시적 백업 경로를 사용한 재시도가 성공했다. 성공 여부는 재조회와 전체 JSON 구조 비교로 판정했다.

설정 백업 SHA-256: 289069a1081a520ab0d3af4538b80c664a488ae390b9f59cbf7d8c8b653a36ad

설정 변경 후 SHA-256: 35f523d18bdbf4d8b45bd7cada601a374d7877eddd65a3a2898c6afaf5e57dca

실제 설치 코드 server-cron-Dd6AX5Mc.mjs에서 OPENCLAW_SKIP_CRON=1이 cronEnabled를 false로 만드는 것을 확인했다. 기존 Gateway 서비스를 초기화 전에 중지하고, 기존 사용자 서비스에 유지보수용 90-codex-maintenance.conf를 추가했다. 개별 작업 정의/enabled/DB는 편집하지 않았다. 최종 PID의 실제 환경에도 차단값이 있음을 확인했다. WSL 기동 시 enabled 서비스가 자동 활성화되는 과정은 있었으며, 수동 start 명령은 한 번만 실행했다. 별도 Gateway 프로세스를 띄우지 않았다.

같은 Companion 실행파일과 프로필로 PID 24244를 한 번 실행했다. 버전 변경 방지를 위해 해당 실행 프로세스에만 OPENCLAW_SKIP_UPDATE_CHECK=1을 사용했고 Windows 전역 환경변수는 변경하지 않았다. Companion이 생성한 keepalive PID 23016과 WSL 자식 PID 26164의 부모·경로·배포판·시작시각을 확인했다. 두 PID는 같은 관리형 keepalive의 Windows 실행기와 자식이며 별도 진단 셸이 아니다.

## MCP와 기존 인증

winnode를 설치하지 않고 공식 HTTP JSON-RPC를 사용했다. 이 버전의 기존 Node 모드는 Gateway 연결 후 AttachClient에서 MCP를 시작했다. 초기 브라우저형 fetch 요청은 HTTP 403 browser context not allowed였으므로, 인증을 끄지 않고 브라우저 문맥 헤더가 없는 native HTTP 요청으로 전환해 정상 인증했다. MCP bearer는 로컬 파일에서 메모리로만 읽었고 출력·명령행·공개 파일에 넣지 않았다.

app.settings.get(EnableMcpServer)는 true를 반환했다. EnableManagedLocalGatewayAutoRepair는 이 버전의 MCP 접근 목록에서 허용되지 않아 해당 호출은 오류를 반환했다. 이를 성공으로 간주하지 않고 실제 설정 파일을 재조회해 false를 검증했다.

app.connection.reconnect를 기존 자격으로 한 번 호출했고 재연결 후 operator/node와 MCP가 모두 정상화됐다. device identity 파일은 바이트 단위 동일하다. gateways.json은 lastConnected만 바뀌었으며 인증 필드는 그대로다. 재페어링·토큰 삭제·초기화·권한 우회는 하지 않았다.

## 지속성·대화·데이터 검증

진단 명령용 WSL 프로세스는 각 호출 후 종료됐다. 대화형 유지 셸을 생성하지 않았으며, Companion 관리 keepalive만 남은 상태에서 314.567초 동안 표본 확인했다. 모든 표본에서 operator/node/MCP 연결 및 Windows HTTP 200이 유지됐다. PID 300은 동일했고 관찰 구간에 새로운 SIGTERM/SIGKILL·EIO·SQLite 손상 로그가 없었다. 공식 gateway call health --json도 기존 자격으로 성공했다.

Chrome의 기존 인증 탭에서 Owner 메뉴, 연결됨, main과 mailbox 대화 2개의 기존 메시지를 확인했다. 메시지를 보내거나 새 대화를 만들지 않았다. 일반 대화 10개를 모두 활성 목록으로 복원했다는 뜻은 아니다. 활성 3개는 실제 UI 접근을 확인했고, 과거 7개는 기존 zstd 압축 보관본의 해시·압축 해제·JSONL 파싱을 읽기 전용으로 검증했다. 각 보관본 행 수는 247, 131, 245, 79, 237, 81, 89다.

이전 D: SQLite 추출 백업과 현재의 두 DB를 비교한 세션 키 합집합은 양쪽 모두 16개로 누락이 없었다. 과거 보고의 단일 숫자를 재사용하지 않고 현재 범위를 재확인했다. SQLite quick_check는 ok다. 예약 작업 정의 SHA-256은 전후 70a1869feae24cb4a215544237aa93e99c062908aa48ab75b103addc494d454c로 동일하며 실행 기록도 107건 그대로다.

## 최종 유지 상태와 롤백

자동 복구 false와 MCP true를 유지한다. 전역 예약 실행은 유지보수 차단 상태로 남긴다. 연구 또는 예약 작업의 재개 승인이 있을 때만 서비스의 90-codex-maintenance.conf를 제거하고 daemon-reload 및 필요한 통제 재기동을 검토한다. 개별 작업 3개를 비활성으로 바꾼 것은 아니다.

Companion 설정을 원복할 경우 앱을 완전히 종료하고 최신 설정의 두 값만 기존 값으로 되돌린다. 재연결 후 생긴 정상적인 lastConnected를 포함한 전체 설정을 옛 백업으로 덮어쓰지 않는다. private 백업과 인증 자료는 GitHub에 올리지 않는다.

이전 SIGTERM 발신 주체를 이번 결과만으로 확정할 수는 없다. 자동 복구 차단과 정상 keepalive 재생성 후 연결이 안정화된 것은 확인했다. 기존 약 51GB TAR을 이번에 다시 해시한 것으로 주장하지 않는다. 기존 연구·Final OOS·VHDX·다른 배포판은 변경하지 않았으며 백테스트와 수집기를 시작하지 않았다.

로컬 기록: D:/Codex_Research/_system/openclaw_recovery_20261020/mcp_bootstrap_2026-10-20T22-26-04-450Z/

최종 공간 확인: C: 약 42.97 GiB, D: 약 763.83 GiB 여유. 공개 결과는 이 보고서와 비밀정보를 제외한 verification.json만이다.

