# OpenClaw Gateway 연결 복구 진단 — 2026-10-20

## 결과

Gateway 연결은 복구되지 않았다. Windows Companion은 실행 중이지만 연결 진단은 `Connecting → Error → Connecting`을 반복한다. Windows에서 TCP 18789 리스너가 없고 `http://127.0.0.1:18789/` 요청은 연결 거부를 반환했다. WSL 내부에서도 포트 리스너가 확인되지 않았다.

## 읽기 전용 점검 결과

- 첫 `wsl --list --verbose` 결과에서 Ubuntu와 OpenClawGateway 모두 Stopped였다. 지정된 openclaw 사용자 계정으로 서비스 상태를 확인하자 WSL 배포판이 기동되었고, `openclaw-gateway.service`는 `active (running)` 및 `Result=success`로 표시됐다.
- 서비스 프로세스는 있었으나 TCP 18789를 열지 않았다. systemd는 응답했고, 현재 확인 시점의 서비스 상태는 running이었다. 따라서 서비스가 단순히 중지되어 생긴 문제로 볼 수 없었다.
- 최근 journal에는 서비스의 반복적인 시작·중지와 중지 과정의 SIGKILL 기록이 있다. `NRestarts=0`으로 systemd 자체 재시작 횟수는 0이었다. 반복 중지를 시작한 주체는 현재 로그만으로 확정할 수 없다.
- Gateway 로그의 구체적인 systemd 오류는 `systemctl show exited 1: Failed to get properties: Transport endpoint is not connected`다. 이는 Gateway가 사용자 systemd 관리자에 속성 조회를 요청할 때 IPC transport가 끊겼다는 직접 증거다. 근본 원인까지는 확인되지 않았다.
- 현재 확인에서는 포트 충돌, 새 EIO 또는 SQLite 손상 오류가 관찰되지 않았다. 다만 Gateway가 listen하지 않아 health/RPC를 성공적으로 검증할 수 없었다.
- 예약 작업은 이전 백업 전 확인에서 3개 활성, 실행 중 0개였다. 이번 연결 실패 상태에서는 현재 실행 상태를 신뢰성 있게 조회할 수 없어 재확인하지 못했다.
- Chrome Owner 권한, Owner Error 표시, main 에이전트 및 대화 10개의 UI 접근은 Gateway 연결이 실패해 검증되지 않았다. 기존 인증이나 세션을 변경하지 않았다.

## 수행한 조치와 한계

요청한 `systemctl --user status` 및 `journalctl --user-unit` 진단만 수행했다. WSL CLI 진단이 Stopped 배포판을 기동했고 활성화된 사용자 서비스가 자동 시작됐지만, 별도 수동 start/restart는 실행하지 않았다. 포트 충돌은 발견하지 않았으나, systemd transport 오류가 확인되고 프로세스 상태와 실제 포트가 불일치해 추가 복구 조치를 중단했다. Companion 복구 버튼, 강제 종료, 재설치, 버전 변경, pairing 변경은 수행하지 않았다.

## 연구 상태

Gateway가 정상 복구되지 않아 사용자 지시대로 `D:\Codex_Research\usdt_krx_live_dashboard`를 열람하지 않았다. 마지막 완료 50조건 배치, 체크포인트, GitHub 업로드 누락 및 다음 배치 번호는 미확인이다. 백테스트와 수집기를 실행하지 않았다.

## 후속 진단에 필요한 근거

Companion 로그에는 연결 오류 이벤트의 시각과 상태만 기록됐고, 원인을 특정할 세부 오류는 해당 이벤트에서 제공되지 않았다. 근본 원인을 확정하려면 Companion의 지원되는 Gateway 복구/재연결 진단 로그에서 systemd 사용자 관리자 transport가 끊기는 순간의 오류를 확인해야 한다. 그 전에는 기존 서비스를 반복 시작하거나 강제 종료하지 않는 것이 현재 보존 조건에 맞다.
