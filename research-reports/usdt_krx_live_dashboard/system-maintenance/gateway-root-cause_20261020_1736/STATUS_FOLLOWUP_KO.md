# Gateway 상태 보충 — 2026-10-20 17:41 EDT

이 보충 기록은 같은 날 앞서 저장한 근본 원인 보고서의 후속 읽기 전용 확인이다.

- `wsl --list --verbose`에서는 OpenClawGateway가 `Running`이었다.
- Companion 진단의 최근 상태는 17:41:06에 `Error`로 바뀐 뒤 `Connecting`이었다.
- Windows의 `http://127.0.0.1:18789/` 요청은 연결 거부를 반환했고 TCP 리스너도 보이지 않았다.
- 이 상태 변화 뒤 systemd를 다시 조회하지 않았다. 추가 WSL 명령으로 lifecycle cycle을 자극하지 않기 위해서다.
- 수동 start/restart, 재페어링, 인증정보 변경, 연구 실행은 하지 않았다.

결과: WSL VM이 실행 중이라고 해서 Gateway 서비스가 HTTP listener를 제공하거나 Companion 인증이 성공한 것은 아니다. 복구는 여전히 미완료다. Owner/대화 UI와 예약 작업의 live Gateway 접근도 검증할 수 없다. D: 연구 배치 상태는 별도 원인 보고서에 기록했으며 이 보충 점검에서 변경하지 않았다.
