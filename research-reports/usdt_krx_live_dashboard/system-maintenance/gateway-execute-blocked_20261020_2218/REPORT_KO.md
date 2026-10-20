# OpenClaw 복구 실행 결과

상태: BLOCKED_LOCAL_CONTROL — Gateway 복구 미완료.

지정된 커밋 05c8b366b970992cc97971c3abb8faefbc77de88의 EXECUTE_RECOVERY_KO.md 전체를 읽고 실행 경로를 확인했다.

## 실제 확인 결과

| 항목 | 결과 |
|---|---|
| 자동 복구 설정 | 변경 전 true / 변경 후 true, 변경하지 못함 |
| 로컬 MCP | EnableMcpServer=false, 127.0.0.1:8765 ECONNREFUSED |
| MCP 토큰 파일 | 없음, 생성·삭제하지 않음 |
| winnode | PATH 및 설치 폴더, 사용자 Local/.local/npm, Program Files, D:/OpenClaw 검색에서 실행 파일 미발견 |
| Gateway | 127.0.0.1:18789 ECONNREFUSED |
| WSL | 조회 시 Ubuntu와 OpenClawGateway 모두 Stopped |
| 설정 UI | 접근성 트리는 읽힘; Ctrl+E 및 Tab 입력 후 포커스는 Transport error에 그대로 남음 |
| 단일 Gateway 기동 | 미실행: 자동 복구 중지 전제 불충족 |
| 기존 인증 재연결 | 미실행: MCP 사용 불가 |
| 임시 WSL 종료 후 5분 지속성 | UNVERIFIED; 임시 WSL 자체를 시작하지 않음 |
| Owner/main/기존 대화 접근 | UNVERIFIED, 화면은 Authentication failed / Transport error |

좌표 클릭은 재시도하지 않았다. 설치 버전의 공식 winnode 스킬과 MCP_MODE 문서에서 실제 호출 형식과 MCP 활성화 조건을 확인했다. 원격 문서의 기능 목록을 로컬에서 활성화된 기능으로 간주하지 않았다.

## 변경과 보존

설정 파일을 읽기 전후 비교한 결과 동일했다. 자동 복구 설정을 false로 바꿨다고 주장할 수 없다. 인증정보, 배포판, 가상디스크, 대화, 예약 작업, 연구 자료를 수정하지 않았다. 새 Gateway, WebSocket, 수집기, 백테스트를 실행하지 않았다. Final OOS에는 접근하지 않았다. 대화 및 예약 작업의 이번 실시간 무결성 검사는 수행하지 못했으며 과거 검증으로 대체하지 않는다. 51GB TAR의 과거 해시를 이번 재검증 결과로 표시하지 않는다.

## 다음 최소 조치

사용자가 기존 Companion의 Settings에서 Developer Mode/Advanced의 Local MCP Server를 켜고 저장해야 한다. 토큰은 채팅에 보내지 않는다. 이는 공식 루프백 MCP 접근 경로를 활성화하는 조치다. 활성화 후 기존 로컬 토큰 파일을 메모리에서만 읽어 tools/list를 확인하고 app.settings.get/set/get으로 EnableManagedLocalGatewayAutoRepair=false를 검증할 수 있다. 이후 예약 작업 상태를 확인하고 기존 Gateway 단일 기동, 기존 인증 reconnect, 임시 유지 세션 종료 후 최소 5분 지속성, Owner/main/기존 대화 접근 순서로 계속한다. winnode가 없어도 공식 JSON-RPC MCP를 사용할 수 있다.

지정 절차 2절은 MCP와 요소 기반 조작이 모두 불가능하면 실행 중 앱의 설정을 직접 덮어쓰지 말고 구체적인 접근 장애를 보고하도록 명시한다. 이 조건 때문에 복구 완료로 보고하지 않는다.
