# C 연구 자료 D 이전 및 OpenClaw 복구 점검

작업일: 2026-10-20

## 결과

- C의 Codex 작업 영역은 31,274개 파일, 6,194,658,207바이트로 조사됐다. 여기에 Downloads의 연구 산출물, 구형 연구 폴더와 Codex 연구 첨부파일을 별도로 확인했다.
- D 신규 이전분은 14,373개 파일 기록, 5,586,161,608바이트다. 복사 직후 SHA-256을 대조했고, 전체 재검증은 일반 파일 14,371개 일치, 의도적으로 변경한 런처 2개, 기타 오류 0개였다.
- 기존 D의 무제한 스윕 자료 6,739개, 474,038,527바이트는 C 원본과 파일별 해시가 전부 일치해 재복사 없이 사용했다.
- C에서는 검증된 중복 파일 21,080개, 6,059,884,508바이트를 제거했다. C 여유 공간은 정리 직전 3.11GiB에서 8.79GiB로 늘었다. 3개의 작은 Downloads 보고서(각 600바이트)는 삭제 시점 전에 이미 없어졌고, D 사본은 검증돼 있다.
- 10GiB 목표에는 도달하지 못했다. 남은 주요 연구 관련 항목은 두 Python 가상환경 약 249.5MB와 대시보드 `.env`다. 가상환경은 현재 실행 구성에 필요해 보존했고, `.env` 및 기타 비밀·OpenClaw 원본도 추가 안전을 위해 C에 남겼다. Codex 활성 `AGENTS.md`, 첨부 참조파일, OpenClaw 작업 폴더도 보존했다.
- C 여유 공간은 작업 시작 관측치 약 5.28GiB에서 복사 도중 약 3.11GiB로 일시 감소했다가, 중복 정리 후 8.79GiB가 됐다. 전송 목적지는 D였으며 C 감소 원인은 확인하지 못했다.
- 현재 D 여유 공간은 891.00GiB다.

## D 저장 경로와 실행 상태

- 대시보드 경로: `D:\Codex_Research\usdt_krx_live_dashboard\app` (D 아카이브 사본을 가리키는 junction)
- 마이그레이션 아카이브: `D:\Codex_Research\archive\c_drive_migration_20261020`
- 전체 파일 이전 manifest: `D:\Codex_Research\_system\migration_20261020\migration_manifest_full_20261020.csv`
- 전체 사후 SHA 검증: `D:\Codex_Research\_system\migration_20261020\migration_validation_full_20261020.csv`
- C 중복 제거 원장: `D:\Codex_Research\_system\migration_20261020\c_duplicate_removal_log.csv`, `unlimited_duplicate_removal_log.csv`
- OpenClaw Windows 설정의 개인 백업은 `D:\Codex_Research\_system\openclaw_recovery_20261020\windows-config-backup`에 있으며 해시 검증을 통과했다. 이 폴더는 민감정보를 포함하므로 GitHub에 올리지 않았다.
- D 런처는 D의 작업 폴더·데이터·로그·임시 및 캐시 경로를 사용하도록 설정했고 기존 C Python 가상환경을 참조한다. PowerShell 구문 검사는 통과했다. 이번에는 런처, 수집기, 대시보드 또는 백테스트를 실행하지 않았다.
- D SQLite 사본과 `stop.request`, `maintenance_pause.json`이 존재한다. 8501, 8502, 8765 포트에는 리스너가 없었다. 체크포인트와 기존 백테스트 산출물은 보존했으며 재실행은 하지 않았다.

## WSL 및 OpenClaw 미해결 사항

- 읽기 전용 상태 확인에서 Ubuntu는 중지 상태, `OpenClawGateway` 배포판은 실행 중이었다.
- 두 배포판 모두 Microsoft 공식 `wsl --export --vhd`로 D 백업을 시도했지만 `Wsl/Service/ERROR_SHARING_VIOLATION`이 반환됐다. VHDX 파일은 만들지 못했다.
- VHDX 직접 복사, 배포판 종료·초기화·unregister·이전은 하지 않았다. 이전에 보고된 EIO 원인은 이번 작업에서 재현하거나 해결하지 못했다.
- `http://127.0.0.1:8765/REPORT.ko.html`은 응답하지 않았으며 OpenClaw Gateway 복구와 대시보드 연결은 미확인이다.
- 다음 안전 단계는 실행 중인 `OpenClawGateway` 배포판을 한 번 종료해 파일 잠금을 해제한 뒤 공식 export를 다시 시도하는 것이다. 이 단계는 실행 중 Gateway를 중단하므로 추가 승인이 필요하다.

## 보존 및 공개 저장소

기존 시장 원본, 보호된 OOS, 전략 설정·원장·체크포인트, D 백업, WSL 가상디스크 및 OpenClaw 설정은 유지했다. GitHub에는 이 요약 보고서만 공개하고, 개인 경로, 파일별 해시, 원본 데이터, `.env`, 토큰 및 OpenClaw 비밀정보는 포함하지 않았다.

GitHub 사전검증 보고서는 커밋 `d7d54483321e8cf7d1928f97c109bd5831436b25`에서 새로 조회해 로컬 내용과 일치함을 확인했다. C 정리 완료 보고는 별도 `MIGRATION_FINAL_KO.md`로 게시·검증했다.
