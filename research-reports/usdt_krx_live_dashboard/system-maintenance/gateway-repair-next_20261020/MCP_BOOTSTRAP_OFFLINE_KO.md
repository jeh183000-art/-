# MCP 비활성 상태의 Companion 설정 부트스트랩

상태: PREPARED_NOT_EXECUTED. 이 문서 게시 및 소스 검토는 사용자 PC에서 설정을 변경하거나 Gateway를 복구한 증거가 아니다.

## 이 문서가 바꾸는 부분

기존 EXECUTE_RECOVERY_KO.md 2절의 MCP/화면 제어 불가 분기만 보완한다. 기존 데이터·인증정보·연구·Final OOS 보존 조건은 유지한다. 실행 중인 앱의 설정을 덮어쓰지 않는 원칙은 유지하지만, 확인된 Companion 인스턴스를 완전히 종료한 다음 검증된 기존 설정 파일의 두 Boolean 값만 오프라인 변경하는 대안을 사용한다. 이를 공식 복구 버튼이나 이미 성공한 복구로 표현하지 않는다.

## 확인한 근거

- 사용자 저장소 커밋 6d8a6fee184e2e94f30ce6726354b50130f6b2f4의 gateway-execute-blocked_20261020_2218/REPORT_KO.md 및 verification.json: EnableMcpServer=false, 자동 복구 true 유지, MCP/Gateway 연결 거부, 조사한 경로에서 winnode 미발견, 설정 변경 없음. 이 관측은 과거 기록이며 실행 직전 상태는 별도 확인한다.
- openclaw/openclaw-windows-node, ref v2026.9.8-1, src/OpenClaw.Tray.WinUI/Services/SettingsManager.cs: SettingsPath는 프로필 데이터 디렉터리의 settings.json이며, 생성자에서 Load()로 기존 JSON을 읽는다. EnableMcpServer와 EnableManagedLocalGatewayAutoRepair가 실제 설정 속성으로 존재한다. OPENCLAW_TRAY_DATA_DIR 및 프로필별 경로를 고려해야 하며 기본 경로를 무조건 덮어쓰면 안 된다.
- 같은 ref의 docs/MCP_MODE.md: MCP는 Gateway 없이 동작 가능하며 루프백 127.0.0.1:8765에 바인딩한다. winnode가 없어도 HTTP JSON-RPC를 사용할 수 있다. MCP 최초 시작으로 로컬 MCP bearer 파일이 새로 생성될 수 있다. 이는 기존 Gateway 토큰이나 device identity를 교체하는 것과 다르다.
- 공식 원문: https://github.com/openclaw/openclaw-windows-node/blob/v2026.9.8-1/src/OpenClaw.Tray.WinUI/Services/SettingsManager.cs
- 공식 원문: https://github.com/openclaw/openclaw-windows-node/blob/v2026.9.8-1/docs/MCP_MODE.md

## 실행 절차

### 1. 실제 대상과 재실행 방법 확정

로컬 Windows 실행 권한으로 현재 Companion의 실행파일 전체 경로, 버전, 사용자/SID, 세션, PID, 시작시각, 선택된 프로필 및 실제 settings.json을 식별한다. 과거 PID를 재사용하지 않는다. 설치 버전이 v2026.9.8-1과 다르면 그 버전의 설정 모델과 시작 동작을 먼저 확인한다.

기존 설치의 재실행 방법을 종료 전에 확보한다. 패키지형 앱이면 원래 앱 등록/바로가기 경로를 사용하고, 임의의 EXE나 다른 프로필을 실행하지 않는다. 같은 프로필을 공유하는 다른 Companion 인스턴스와 자동 실행 주체가 있는지도 확인한다. 전체 명령행/설정/환경변수에 비밀값이 있을 수 있으므로 콘솔과 보고서에는 필요한 비민감 메타데이터만 남긴다.

기본 경로 후보는 %APPDATA%\OpenClawTray\settings.json이지만 이것만으로 수정 대상을 확정하지 않는다. 기존 조사에서 읽었던 실제 파일과 프로필 소유권이 맞아야 한다. 경로가 불명확하면 후보 파일들을 일괄 수정하지 않는다.

### 2. 해당 Companion을 완전히 종료

진행 중인 명령, 설정 저장, 설치/업데이트, 연구 실행이 없는지 확인하고 Companion의 정상 Exit를 우선한다. 창이 사라졌다는 것만으로 종료로 판단하지 말고 해당 프로세스가 종료됐는지 확인한다.

정상 종료가 응답하지 않을 때 강제 종료가 꼭 필요하면, 종료 직전 다시 확인한 사용자·실행파일 전체 경로·PID·시작시각이 모두 일치하는 해당 Companion 인스턴스만 대상으로 한다. 실행 중 쓰기/작업이 있거나 귀속을 확정할 수 없으면 강제 종료하지 않는다. 프로세스 이름 와일드카드나 전체 프로세스 트리 일괄 종료를 사용하지 않는다. 다른 앱, Codex, WSL, Gateway/Node 프로세스는 종료 대상이 아니다.

동일 설정을 쓰는 프로세스가 남아 있거나 자동 재실행되어 경쟁 상태가 생기면 파일 변경을 하지 않는다. wsl --shutdown, --unregister, 배포판 재설치, DBus 런타임 삭제는 금지한다.

### 3. 종료 상태에서 소규모 백업과 두 값 변경

기존 D:\Codex_Research\_system\openclaw_recovery_20261020\ 아래의 새 작업 폴더를 사용한다. 비밀값이 포함될 수 있는 설정 백업은 동일 사용자와 필요한 시스템 관리자 외에 읽히지 않도록 ACL을 제한한다. 백업 바이트/해시와 원본 일치를 확인한다. 전체 DB/51GB TAR 재복사는 이번 단계의 전제가 아니다. 백업 및 원본 설정은 공개 GitHub에 올리지 않는다.

변경 대상은 기존 settings.json의 다음 두 최상위 Boolean 값뿐이다.

```json
{
  "EnableMcpServer": true,
  "EnableManagedLocalGatewayAutoRepair": false
}
```

위 JSON은 전체 설정 파일의 대체 내용이 아니다. 이 두 줄만 담긴 파일로 기존 설정을 덮어쓰지 않는다.

- JSON 구문과 실제 속성 타입을 먼저 검사한다. 이름/스키마가 다르면 추측하여 추가하지 않는다.
- 기존 Gateway URL/ID, PreferredGatewayId, EnableNodeMode, 공유 토큰, device token, identity/keypair, 암호화 문자열, 권한/샌드박스 및 나머지 설정은 그대로 유지한다.
- 원본 파일 전체를 기본값 모델로 재생성하지 않는다. 나머지 필드와 암호화 문자열을 보존하는 최소 수정과 JSON 구조 비교를 사용한다.
- 수정 직전 파일 해시가 백업 시점과 같은지 확인하여 경쟁 변경을 탐지한다. 변경이 있으면 덮어쓰지 않는다.
- 완성한 임시 JSON을 검증하고 기존 접근권한을 유지하면서 같은 볼륨에서 안전하게 교체한다. 비밀값 포함 임시파일을 넓은 ACL의 폴더에 남기지 않는다.
- 재조회 시 위 두 값이 목표값이고 나머지 데이터가 동등한지 확인한다. 값/토큰 자체는 출력하지 않고 일치 여부만 기록한다.

설정 변경은 롤백 가능해야 한다. 롤백 시에도 앱 종료를 확인하고, 실행 후 생긴 다른 정상 변경을 무조건 옛 전체 파일로 덮어쓰지 않는다. 전체 백업 복원과 두 값만 원복 중 안전한 방법을 선택하고 결과를 기록한다.

### 4. 기존 인스턴스 재실행과 MCP 검증

재실행은 동일 Windows 사용자·동일 기존 프로필로 한 번만 한다. MCP 활성화 자체는 Gateway 복구가 아니며, Companion 시작 과정의 기존 자동 연결이 Gateway를 기동할 가능성도 따로 고려한다.

기동 전에 기존 절차의 예약 작업/연구 실행 차단 조건을 적용한다. 설치 버전이 지원하는 전역 스케줄러 일시정지 방법을 확인하고 필요 시 사용하되, 작업 3개의 개별 정의/enabled/실행 이력이나 DB를 직접 편집하지 않는다. 해당 안전 조건이 충족되지 않으면 미확인 상태로 무작정 Gateway를 기동하지 말고 정확한 남은 조건을 기록한다.

확인 항목:

1. 같은 프로필의 Companion이 정상 실행되며 두 설정이 유지되는가.
2. 127.0.0.1:8765 리스너가 해당 Companion 소유로 열리는가.
3. 기존 프로필의 mcp-token.txt가 생성/사용되는가. 파일 내용을 채팅, 보고서, 명령행 인수 또는 GitHub에 노출하지 않는다.
4. 로컬 스크립트에서 토큰을 메모리로 읽고 Authorization 헤더로 인증한 JSON-RPC initialize/tools/list가 성공하는가. 토큰을 셸 명령 문자열에 삽입하지 않는다.
5. 실제 tools/list에 app.settings.get과 app.connection.status가 있는지 확인하고, 자동 복구 false와 MCP 활성 상태를 재조회한다.

winnode가 없다는 이유로 멈추거나 새 버전 winnode/Companion을 설치하지 않는다. 지원되는 직접 HTTP JSON-RPC를 사용한다. 실패 시 TCP 거부, 401 인증 실패, JSON-RPC/tool 오류를 구분하며 포트 개방을 기능 성공으로 보고하지 않는다. MCP 또는 Gateway를 0.0.0.0에 바인딩하거나 방화벽/인증을 해제하지 않는다.

### 5. 기존 Gateway 복구 절차로 계속

MCP 확인 뒤 기존 EXECUTE_RECOVERY_KO.md 3~6절의 범위에서 계속한다. 자동 복구 false를 유지한 채 기존 WSL/Gateway의 단일 기동과 지속성을 검증하고, 기존 자격으로 한 번 연결한다. 이미 동작 중이면 추가 Node/Gateway를 띄우지 않는다. 실제 인증 오류 코드 확인 없이 토큰 삭제/재발급/재페어링을 하지 않는다.

임시 WSL 유지 셸을 닫은 뒤에도 18789와 인증된 연결이 유지되는지, Owner/main/기존 일반 대화 10개의 실제 접근이 되는지 확인한다. 단순 HTTP 200, MCP tools/list 성공 또는 설정 변경 성공을 Gateway 복구 완료로 바꾸어 표현하지 않는다.

## 결과 보고

최소한 다음을 실제 관측으로 구분해 보고한다.

- Companion 종료/재실행 여부 및 동일 프로필 여부
- EnableMcpServer 전후 값 / EnableManagedLocalGatewayAutoRepair 전후 값
- 나머지 설정 보존 검사와 로컬 백업 검증 여부
- MCP 포트와 인증된 tools/list PASS/FAIL
- Gateway 18789 지속성 / 인증된 연결 / Owner / main / 기존 대화 접근 각각 PASS/FAIL/UNVERIFIED
- 데이터·인증 변경 여부, 예상하지 않은 연구/예약 작업 실행 여부
- 실패하면 마지막으로 실제 실행한 단계와 구체적 오류 종류

민감정보를 제외한 증거만 GitHub에 게시하고 원격 내용을 확인한다. 기존 백업 해시를 새로운 재해시처럼 보고하지 않는다. 이 지시문 게시 커밋과 실제 복구 실행 증거 커밋은 구분한다.
