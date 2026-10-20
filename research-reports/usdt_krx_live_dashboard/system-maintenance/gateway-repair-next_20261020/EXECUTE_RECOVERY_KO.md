# OpenClaw Gateway 비파괴 복구 실행 절차

작성일: 2026-10-20
상태: PREPARED_NOT_EXECUTED — 이 파일을 GitHub에 저장한 것은 사용자 PC에서 복구를 실행한 것이 아니다.
대상: 기존 Windows Companion과 OpenClawGateway WSL의 기존 Gateway. 신규 설치/신규 프로필 생성 작업이 아니다.

## 목표와 근거

기존 진단만 반복하지 말고, 아래 제한 내에서 실제 복구를 수행하고 각 단계의 결과를 확인한다. 근거 보고서는 커밋 `4aac974c60ce994dc2758df62ab85bed15816ce8`의 `research-reports/usdt_krx_live_dashboard/system-maintenance/gateway-root-cause_20261020_1736/REPORT_KO.md` 및 `STATUS_FOLLOWUP_KO.md`다. 이 보고서는 과거 관측이며 현재 상태를 대신하지 않는다.

보고된 유력 원인은 자동 복구와 WSL keepalive 수명주기의 충돌이다. SIGTERM 발신 주체는 확정되지 않았다. `Transport endpoint is not connected`를 최초 원인으로 단정하거나 DBus 재설치를 하지 않는다. 포트/프로세스 안정화와 인증 복구를 별도 검증한다.

새로 확인한 실행 경로: 설치 버전 v2026.9.8-1의 공식 문서에 따르면 Companion은 Gateway 없이도 동작 가능한 로컬 MCP와 `winnode` CLI를 제공한다. 로컬 MCP의 기본 주소는 `http://127.0.0.1:8765/`이며 Gateway의 18789 포트와 다르다. 따라서 좌표 입력 실패만으로 설정 변경을 포기하지 말고, 실제 설치된 로컬 MCP 명령을 우선 사용한다. MCP가 활성화되어 있거나 명령이 존재한다고 미리 가정하지 않는다.

## 보존 조건

- 기존 WSL, VHD, Gateway ID, agent/workspace, 세션·대화, 예약 작업 정의, D: 연구 자료와 백업을 삭제·초기화·이전하지 않는다.
- 기존 인증정보를 우선 보존한다. Gateway 공유 토큰, device identity/keypair, 저장된 장치 토큰을 일괄 삭제하거나 교체하지 않는다. 인증 해제, TLS 검증 해제, 외부 주소 바인딩으로 우회하지 않는다.
- `wsl --shutdown`, `wsl --unregister`, 무차별 `taskkill`, PID 숫자만 보고 종료, 패키지 재설치/자동 업그레이드, systemd/DBus 런타임 파일 삭제 금지.
- 백테스트·수집기·연구 worker를 시작하지 않는다. Final OOS를 열지 않는다. batch_0141 게시와 batch_0142 계산은 이번 Gateway 복구 범위에서 제외한다.
- 모든 추가 로컬 보고서·백업·임시 파일은 `D:\Codex_Research\_system\openclaw_recovery_20261020\` 아래 별도 작업 폴더에 둔다. 기존 파일을 덮어쓰지 않는다.
- 이 저장소는 공개다. MCP token, Gateway token, setup code, identity private key, 전체 설정/DB, 대화 본문은 올리지 않는다. 비밀값을 명령행 인수나 콘솔에 출력하지 않는다.

## 1. 변경 전 확인과 소규모 백업

Windows에서 현재 Companion 실행 경로/버전, 해당 프로필, WSL 이름, 현재 포트 및 프로세스 상태를 다시 확인한다. 과거 keepalive PID를 현재 프로세스로 간주하지 않는다. 실행 파일 경로·명령행·시작 시각·배포판 귀속까지 맞춰야 한다.

실제로 변경할 Companion 설정과 관련 registry/identity 상태를 로컬의 접근 제한된 폴더에 백업한다. DB 복사가 필요하면 일관된 SQLite backup 수단을 사용한다. 실행 중인 DB 파일만 임의 복사해 무결성 백업이라고 주장하지 않는다. 기존 51GB TAR의 이전 SHA를 새 검증 결과로 보고하지 않는다.

Gateway 기동으로 활성 예약 작업이 자동 실행될 가능성을 먼저 확인한다. 연구 재개를 막기 위한 전역 스케줄러 일시정지가 필요하면 설치 버전이 지원하는 공식 유지보수 설정을 확인하고 사용한다. 개별 작업의 내용·enabled 값·실행 이력을 편집하거나 DB를 직접 수정하지 않는다. 임시 전역 설정의 원래 값과 복원 조건을 기록한다.

## 2. 좌표 입력 대신 로컬 MCP로 자동 복구 중지

먼저 설치된 `winnode.exe`를 찾고 실제 도움말과 명령 목록을 확인한다. PATH에 없으면 확인된 설치 경로를 사용하며, 다른 버전의 실행 파일을 새로 설치하지 않는다.

```text
winnode --list-tools
winnode --command app.connection.status
winnode --command app.connection.gateways
```

호출 전에 실제 반환 스키마와 로컬 MCP의 정상 여부를 확인한다. MCP bearer는 CLI의 기존 로컬 파일 자동 로딩을 사용한다. `--mcp-token <비밀값>` 같은 인수, 채팅으로 토큰 전달, 포트 8765 외부 공개를 하지 않는다.

`app.settings.get`과 `app.settings.set`이 실제로 존재하고 설정 이름을 지원하는지 확인한다. 아래 두 JSON을 각각 로컬 임시 파일로 저장한 뒤 `--params @<파일경로>`로 전달하면 PowerShell/CMD JSON 따옴표 문제를 피할 수 있다.

읽기용:
```json
{"name":"EnableManagedLocalGatewayAutoRepair"}
```

변경용:
```json
{"name":"EnableManagedLocalGatewayAutoRepair","value":"false"}
```

```text
winnode --command app.settings.get --params @<읽기용_JSON_경로>
winnode --command app.settings.set --params @<변경용_JSON_경로>
winnode --command app.settings.get --params @<읽기용_JSON_경로>
```

성공 응답과 실제 재조회 값이 false인 것을 확인한다. 원래 값을 기록한다. Gateway 인증과 무관한 이 한 설정만 바꾼다. 오류 뒤 같은 쓰기 명령을 무한 반복하지 않는다.

MCP가 꺼져 있으면 이미 허용된 Windows UI Automation의 요소 기반 조작/키보드 접근으로 공식 Connection의 Disconnect 또는 Stop을 사용할 수 있는지 확인한다. 좌표를 추측해 클릭하지 않는다. MCP와 요소 기반 조작이 모두 불가능하면 실행 중 앱 설정을 추측한 경로에서 덮어쓰지 말고, 구체적인 로컬 접근 장애를 보고한다. 복구와 무관한 전체 권한 확대를 요구하지 않는다.

## 3. 자동 복구 개입을 차단한 상태에서 단일 기동

Gateway 사용자와 서비스 이름은 실제 설치 상태로 재확인한다. 공식 관리형 WSL 기준은 `openclaw` 사용자와 `openclaw-gateway.service`다. `systemctl --user`를 root로 실행하지 않는다.

Windows에서 유지되는 WSL 세션 하나를 열어 관찰 중 WSL이 닫히는 요인을 분리한다. 이는 임시 진단용이며 영구 keepalive 복구를 대체하지 않는다.

```powershell
wsl.exe -d OpenClawGateway --user openclaw -- bash
```

그 세션에서 다음 읽기 전용 확인을 수행한다.

```bash
whoami
systemctl --user show openclaw-gateway.service -p ActiveState -p SubState -p MainPID -p NRestarts -p Result
journalctl --user-unit openclaw-gateway.service --no-pager -n 100
ss -ltnp 'sport = :18789'
```

- 사용자 manager와 IPC가 정상이며 서비스가 비활성이면 `systemctl --user start openclaw-gateway.service`를 한 번만 실행한다.
- 이미 실행 중이면 중복 Node 프로세스를 띄우지 않는다. 초기화 로그가 진행 중이면 상태를 관찰한다. 멎은 서비스임이 확인되고 진행 작업이 없을 때에만 해당 서비스의 단일 통제 재시작을 검토한다. 같은 근거로 반복 재시작하지 않는다.
- IPC가 여전히 끊겨 있으면 서비스 시작부터 반복하지 말고 사용자 manager/배포판 상태와 종료 이벤트를 확인한다. 다른 WSL 배포판을 종료하거나 DBus를 재설치하지 않는다.
- 기동 전후 boot ID, MainPID, 프로세스 시작 시각, 포트 소유자, SIGTERM/서비스 stop 이벤트를 기록한다. PID/포트만으로 원인 주체를 확정하지 않는다.

WSL 내부와 Windows의 18789 연결을 각각 확인한다. WSL에서만 정상이고 Windows에서 실패하면 인증 문제가 아니라 전달/네트워크 경로를 별도 조사한다. HTTP 200만으로 인증된 Gateway 연결 성공이라고 판단하지 않는다.

최소 5분간 불필요한 재시작 없이 Gateway와 포트가 유지되는지 관찰한다. 이 시간은 검증 조건이지 사용자에게 작업 완료를 약속하는 시간이 아니다.

## 4. 기존 인증으로 연결하고 상세 오류 분리

실제 명령 목록에 있는 `app.connection.status`로 operator/node 상태, 선택된 Gateway, URL, credential source/status와 최근 오류를 확인한다. 민감값 없는 상태 정보만 저장한다. 대상이 기존 관리형 Gateway임을 확인한 후 기존 자격으로 `app.connection.reconnect`를 한 번 실행하고 결과를 재조회한다.

`Authentication failed`라는 화면 문구만으로 모든 자격을 바꾸지 않는다. 실제 `connect` 실패의 상세 코드와 대상 역할을 기록한다.

- `AUTH_TOKEN_MISSING` / `AUTH_TOKEN_MISMATCH`: 올바른 Gateway/prof​ile/endpoint와 기존 저장 자격 선택을 점검한다. 새 전역 토큰부터 만들지 않는다.
- `AUTH_DEVICE_TOKEN_MISMATCH`: 해당 장치·역할의 저장 토큰 거부인지 확인한다. 공식 장치별 복구 절차를 검토하되, 기존 인증 보존 범위를 넘는 rotate/remove/re-pair는 자동 실행하지 않는다. 어느 장치의 어떤 자격만 바꿔야 하는지 특정하여 보고한다.
- `AUTH_SCOPE_MISMATCH` / `PAIRING_REQUIRED`: 역할·scope·pending request를 확인한다. 관련 없는 장치를 승인하거나 Owner/admin 권한을 임의 확대하지 않는다. 새 승인이나 재페어링이 필요하면 정확한 대상과 요구 권한을 제시한다.
- `Transport error`: 이 시점에도 실제 리스너/전달 경로가 살아 있는지부터 확인한다. 인증 변경으로 연결 거부를 해결하려 하지 않는다.

새 인증 변경 승인이 필요하지 않은 단계는 사용자에게 다시 승인 질문을 반복하며 멈추지 말고 수행한다. 다만 이 문서를 인증정보 변경에 대한 포괄적 승인으로 해석하지 않는다.

## 5. 임시 유지 세션 없이 지속되는지 검증

설치 버전의 공식 Companion Start/Connect/Repair 흐름으로 관리형 keepalive의 정상 소유권을 복구한다. 지원 여부가 확인되지 않은 MCP 명령명은 만들지 않는다. stale marker 숫자만 지우거나 가짜 PID를 써넣지 않는다.

정상 keepalive 프로세스와 배포판 귀속을 확인한 다음 임시 WSL 유지 세션을 종료하고 다시 최소 5분간 관찰한다. 임시 셸을 열어 둔 동안만 작동하면 영구 복구 완료가 아니다. 자동 복구 false를 진단 중에 임의로 true로 되돌리지 않는다. 최종 값과 향후 원상복구 조건을 명시한다.

## 6. 완료 판정과 결과 게시

다음 항목을 각각 PASS/FAIL/UNVERIFIED로 구분한다.

1. 기존 Gateway의 프로세스·18789 리스너가 임시 유지 세션 없이 유지되는가.
2. Windows에서 같은 Gateway에 인증된 operator 연결이 성공하는가. HTTP 200과 구분한다.
3. 필요한 node 연결, Owner 상태, main 에이전트가 정상인가.
4. 기존 일반 대화 10개의 목록과 실제 메시지 접근이 가능한가. 새 대화를 만들거나 시험 메시지를 보내지 않는다.
5. 기존 세션 키 13개 보존, 예약 작업 정의/활성 상태 보존이 확인되는가. 의도하지 않은 연구 실행이 없었는가.
6. 변경한 항목, 원래 값, 최종 값, 롤백 방법과 남은 장애가 기록되었는가.

작업 후 민감정보를 제거한 실행 보고서와 검증 자료를 새 디렉터리에 커밋·푸시한다. 원격 커밋의 파일을 다시 읽어 검증하고 commit SHA와 파일 경로를 보고한다. GitHub 파일 저장, 서비스 active, 단일 HTTP 200을 Gateway 전체 복구 성공으로 표현하지 않는다. 인증 변경이 최종 차단점이면 정확한 오류와 최소 변경 대상을 보고한다. 이 작업 중 batch_0142, 백테스트, 수집기를 재개하지 않는다.

## 공식 참조

실제 설치 버전의 CLI 도움말과 live tools/list가 우선이다. 아래 문서는 지원 기능을 확인하기 위한 자료이며 원격 실행이 이미 연결되었다는 뜻이 아니다.

- https://github.com/openclaw/openclaw-windows-node/blob/v2026.9.8-1/docs/MCP_MODE.md
- https://github.com/openclaw/openclaw-windows-node/blob/v2026.9.8-1/.agents/skills/winnode/SKILL.md
- https://github.com/openclaw/openclaw-windows-node/blob/v2026.9.8-1/docs/WSL_GATEWAY_ADMIN.md
- https://github.com/openclaw/openclaw-windows-node/blob/main/docs/CONNECTION_ARCHITECTURE.md
- https://docs.openclaw.ai/gateway/troubleshooting/agent-replies-and-control-ui
- https://docs.openclaw.ai/cli/devices
