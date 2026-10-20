# OpenClaw D: 이전 사전 점검 결과 — 2026-10-20

## 결론

OpenClawGateway 배포판의 D: 이전은 실행하지 않았다. Windows OpenClaw Companion이 요구하는 관리 경로는 `%LOCALAPPDATA%\OpenClawTray\wsl` 하위이며, `D:\OpenClaw\WSL\OpenClawGateway`를 Companion이 자동 시작·업데이트·복구까지 지원한다는 근거를 확인하지 못했다. 사용자가 지정한 호환성 기준에 따라 안전성을 입증하지 못한 상태로 이전을 강행하지 않았다. `wsl --manage ... --move` 명령도 실행하지 않았다.

## 설치 및 저장 상태

- WSL 버전: 3.0.3.0; 커널 6.18.5.4.
- OpenClaw Companion: 2026.9.4. OpenClawGateway는 WSL 2 배포판이며 등록 경로는 `%LOCALAPPDATA%\OpenClawTray\wsl\OpenClawGateway`다. Ubuntu 배포판은 변경하지 않았다.
- Companion 설정에서 자동 시작 및 관리형 Gateway 자동 복구가 켜져 있었다. 설정은 수정하지 않았다.
- 작업 후 여유 공간: C: 43.74 GiB, D: 763.83 GiB.

## 백업 및 무결성

기존 TAR 백업 `D:\Codex_Research\_system\openclaw_recovery_20261020\wsl-backups\OpenClawGateway_postreboot_20261020.tar`는 56,082,257,920 바이트이며 SHA-256은 `BC0E7F510595961AD43CE29DEB14690FDAC898ADCCEFDA1BA9D95DC84764B6C2`다. TAR 목록 210,784개 항목을 읽었다.

Owner pairing 이후 새로 만든 `D:\Codex_Research\_system\openclaw_recovery_20261020\wsl-backups\OpenClawGateway_post_pairing_20261020.tar`는 51,143,352,320 바이트이며 SHA-256은 `BBF289F9DA62474E4DD347DDA53E5C4910CACE48AE0850292200E78A7DAFF43A`다. TAR 목록 200,278개 항목을 읽었다. 내보내기 중 임시 Unix 소켓 하나는 아카이브할 수 없다는 경고가 있었다. 추출 검사용으로 확인한 두 SQLite 데이터베이스는 `PRAGMA integrity_check`에서 `ok`를 반환했다.

백업 간 세션 키 비교에서는 이전 백업의 13개 키가 모두 새 백업의 활성 세션 또는 보관된 트랜스크립트에 존재했다. 새 백업에는 활성 세션 노드 7개와 보관된 트랜스크립트 7개가 확인됐다. 이는 세션 보관 형태가 바뀐 상태이며 키 누락은 발견되지 않았다. 대화 본문은 읽거나 보고서에 복사하지 않았다.

## Gateway 및 예약 작업

백업 전 Gateway는 2026.9.6으로 실행 중이었고 health/RPC 확인이 통과했다. 예약 작업은 3개 활성화, 실행 중 0개였으며, 최근 상태는 성공 2개와 실패 1개였다. 작업 프롬프트나 인증정보는 이 보고서에 포함하지 않았다.

백업을 위한 정상 종료 후 Companion/WSL이 재기동을 시도했으나, 마지막 확인 시점에는 `127.0.0.1:18789` 응답이 없고 Gateway RPC/health가 실패했다. 현재 Gateway 정상 상태, Chrome Owner 접근 및 10개 일반 대화의 UI 접근은 재검증되지 않았다. 자동 재시작을 반복하거나 새 pairing을 승인하지 않았다. 로그에서 새 EIO 또는 SQLite 손상/IOERR는 확인되지 않았으나, 느린 SQLite 잠금 경고와 WSL systemd transport 오류는 남아 있다.

## 연구 자료 점검

D: 이전이 호환성 기준을 통과하지 못했으므로, 지시된 조건에 따라 `D:\Codex_Research\usdt_krx_live_dashboard` 연구 자료는 열람하지 않았다. 마지막 완료 배치, 다음 배치, 원격 해시 상태는 미확인이다. 백테스트는 시작하지 않았다.

## 다음 조치

Companion이 공식 지원하는 Gateway Setup/복구 흐름으로 WSL 관리 상태를 정상화하고, Tray 연결·Owner 권한·대화·예약 작업을 다시 확인해야 한다. D: 이전을 재검토하려면 Companion 공급자가 해당 경로를 지원한다는 명시적 호환성 근거가 먼저 필요하다.

## 근거 문서

- [OpenClaw Windows documentation](https://github.com/openclaw/openclaw/blob/main/docs/platforms/windows.md)
- [OpenClaw WSL Gateway admin guide](https://github.com/openclaw/openclaw-windows-node/blob/main/docs/WSL_GATEWAY_ADMIN.md)
- [OpenClaw Windows-node architecture](https://github.com/openclaw/openclaw-windows-node/blob/main/docs/ARCHITECTURE.md)
- [Microsoft WSL CLI source](https://github.com/microsoft/WSL/blob/master/src/windows/inc/wsl.h#L546-L552)
- [Microsoft WSL disk-space documentation](https://github.com/MicrosoftDocs/wsl/blob/main/WSL/disk-space.md)
