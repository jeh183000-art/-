# OpenClaw Gateway 근본 원인 추적 결과 — 2026-10-20

## 결론

복구되지 않았다. 핵심 문제는 두 층이다. (1) Gateway 서비스가 `systemd`에서 정상 종료 신호를 받은 뒤 WSL user manager가 사라져 Gateway가 반복적으로 끊겼다. (2) Companion 연결 화면에는 `Authentication failed`와 `Transport error`가 표시되어 Owner 인증과 세션 UI가 복구되지 않았다. 인증 재발급, 재페어링, 수동 Gateway 재시작은 하지 않았다.

## 프로세스 및 중단 원인

- 설정은 JSON으로 읽혔고, gateway 모드는 `local`, 포트는 `18789`, bind는 `loopback`이었다. systemd 실행 인수도 `gateway --port 18789`였다.
- 관측 시 systemd `MainPID`와 실제 Node Gateway PID가 일치했다. unit은 `Type=simple`, `Restart=always`, `RestartUSec=5s`, `NRestarts=0`, 종료 결과 `success`로 확인됐다. 포트 소유권 충돌은 없었다.
- 17:19:17에 시작한 프로세스는 설정 로딩, 인증 해석, broker 준비까지 진행했지만 17:19:56에 systemd가 서비스를 `Stopping` 상태로 전환했다. Node는 SIGTERM을 받고 정상 종료 절차를 시작했으며, systemd가 하위 broker 프로세스를 SIGKILL했다. 이는 Node의 자체 crash나 OOM 재시작이 아니었다.
- 같은 시점 직후 Gateway가 systemd stop timeout을 확인하려고 호출한 `systemctl show`에서 `Failed to get properties: Transport endpoint is not connected`가 발생했다. 이미 user systemd manager/DBus transport가 해체되는 중에 나온 결과이며 최초 원인은 아니다.
- Companion 연결 기록은 17:19:34에 `Error`, 17:20:41에 다시 `Error`를 남겼다. 그 사이 systemd manager ID가 바뀌고 WSL이 다시 시작되는 순서가 관측됐다. 이 시각 관계와 현재 설정의 자동 복구 활성 상태는 Companion의 managed-local auto-repair가 WSL을 재기동하는 동작과 강하게 부합한다. 다만 Companion 진단 로그에는 repair action ID나 실행 주체가 기록되지 않아, 실제 `wsl --terminate` 호출 주체까지는 직접 확정할 수 없다.
- 이후 17:23:48에는 Gateway가 실제로 127.0.0.1:18789에서 listen했고 HTTP 200도 한 차례 확인됐다. 약 1분 뒤 다시 Companion 오류가 반복됐으며, 17:26 검사에서는 포트가 연결 거부 상태였다. 마지막 `wsl --list --verbose`에서는 OpenClawGateway가 Stopped였다.
- Companion keepalive marker가 가리키는 `wsl.exe` PID 17328은 더 이상 실행 중이 아니었다. marker의 시작 시각은 05:27 EDT였고 재기동 뒤에도 갱신되지 않았다. Companion 설치 버전은 2026.9.8-1이며 자동 복구 설정은 켜져 있었다. 즉 keepalive 기능은 설치되어 있으나 현재 keepalive 프로세스는 살아 있지 않다.
- Gateway 메모리 peak는 관측 로그에서 약 2.0 GiB였고, 접근 가능한 로그에서 OOM 흔적은 확인되지 않았다. SQLite 손상은 발견되지 않았다. shutdown 중 SQLite coordinator lock wait 약 672 ms 경고는 있었지만 손상 원인은 아니다.

따라서 가장 가능성 높은 lifecycle 원인은 Companion의 managed-local 자동 복구/WSL 수명주기와 살아 있지 않은 keepalive가 맞물려 WSL을 반복 생성·종료시키는 것이다. 정확한 stop caller 기록은 없으므로 이 부분은 강한 정황 판단으로 남긴다. Gateway가 잠시 listen한 뒤에도 Companion은 인증 오류를 표시했으므로, WSL 수명주기 안정화만으로 Owner 오류가 해결된다고 볼 수 없다.

## 인증, 대화 및 예약 작업

Companion Settings에는 `Authentication failed`, `Transport error`가 표시됐고 저장 Gateway는 `paired via device token`으로 남아 있었다. Workspace에는 `Owner Error`, `No agents loaded`, `No conversations to show`, `Loading messages...`가 표시됐다. Chrome의 OpenClaw 탭 제목에도 연결 끊김이 나타났다.

이전 백업 대조에서는 기존 세션 키 13개가 새 백업의 활성 세션 또는 아카이브에 모두 존재했다. 데이터가 백업에서 누락된 것은 아니지만, 현재 Companion 화면에서는 인증 실패 때문에 10개 일반 대화를 확인할 수 없다. main 에이전트 표시도 현재 실패 상태다.

현재 Gateway SQLite의 읽기 전용 조회 결과 예약 작업 4개 레코드 중 3개가 enabled였다. 활성 작업의 최근 상태는 성공 2개, 오류 1개였고 실행 중 상태/receipt는 발견되지 않았다. 예약 작업은 수정하지 않았다.

## 백업 및 연구 상태

최신 D: TAR는 `D:\Codex_Research\_system\openclaw_recovery_20261020\wsl-backups\OpenClawGateway_post_pairing_20261020.tar`, 51,143,352,320바이트다. 직전 검증 보고서/manifest에 기록된 SHA-256은 `BBF289F9DA62474E4DD347DDA53E5C4910CACE48AE0850292200E78A7DAFF43A`이며 이전에 TAR listing 및 SQLite 무결성 검사를 통과했다. 이번에는 파일 크기와 최종 수정시각(08:32 EDT)을 확인했다. 51 GB 전체를 다시 읽는 새 해시 계산은 제한된 작업 시간 안에 완료되지 않아, 이번 결과에서는 이전에 검증된 해시를 재사용하고 새 재해시를 완료했다고 주장하지 않는다.

D: 연구 자료는 읽기 전용으로 확인했다. 2025/2026 정규장·야간장 데이터 폴더와 승인된 연구 산출물이 존재한다. `unlimited_revalidation_20261017_01`의 마지막 계산 완료 배치는 `batch_0141`이며 76,608개 중 7,050개 조건까지 기록됐다. D:의 `batch_0141/publish` manifest 22개 payload 모두 파일 크기와 SHA-256이 일치했다. `READY.json`은 `READY_FOR_PUBLICATION`이지만 publication receipt가 없고, 동일한 batch_0141 보고서는 GitHub에서 찾을 수 없었다. 마지막 원격 게시 배치는 `batch_0140`, 커밋 `750f31d78f663c028d36646c086757066c9fc2ed`다.

batch_0141의 `READY.json` payload pointer는 이전 C: 경로를 가리키고 그 위치에는 파일이 없다. D: publish 폴더 자체는 검증됐으므로, 이어서 작업할 때는 D: payload를 기준으로 batch_0141을 먼저 게시·검증하고 그 다음 계산 batch_0142를 시작해야 한다. worker lock의 PID는 실행 중이지 않았고 현재 sweep 프로세스도 확인되지 않았다. 백테스트나 수집기를 실행하지 않았으며 Final OOS 자료는 열거나 분석하지 않았다.

## 조치 및 남은 제한

Companion 연결 진단은 이미 반복 복구 시도를 하고 있어 수동 재시작을 추가하지 않았다. Companion UI 버튼 입력은 현재 Windows 자동화에서 `coordinate input geometry is unavailable`로 실패해 UI를 통한 단일 수동 복구를 실행하지 못했다. `Re-pair this gateway`는 새 setup code 또는 직접 token을 요구하며 기존 saved device credential을 바꿀 수 있어 실행하지 않았다.

Owner와 대화 UI를 복구하려면 Gateway lifecycle 안정화와 함께 Companion의 공식 재페어 절차가 필요할 수 있다. 이는 저장된 인증정보 변경이므로 기존 보존 조건에서는 진행하지 않았다. 다음 실행 전 사용자는 인증 재페어 허용 여부를 결정해야 한다. Companion 자동 복구 반복도 계속되고 있는지 확인이 필요하다.

## 공식 동작 문서

- [Windows Companion connection architecture](https://github.com/openclaw/openclaw-windows-node/blob/main/docs/CONNECTION_ARCHITECTURE.md)
- [OpenClaw Windows Hub v2026.9.8-1 release](https://github.com/openclaw/openclaw-windows-node/releases/tag/v2026.9.8-1)
- [Managed WSL Gateway administration](https://github.com/openclaw/openclaw-windows-node/blob/main/docs/WSL_GATEWAY_ADMIN.md)
