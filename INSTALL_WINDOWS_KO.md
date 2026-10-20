# Codex 영구 저장 규칙 설치 안내 (Windows, 1회 적용)

## 목적

**로컬 대용량 연구 산출물은 D:\Codex_Research에 저장하고, ChatGPT가 직접 검증할 결과는 GitHub `jeh183000-art/-`에 올린다.** C: 저장공간 고갈 재발 방지가 목적이다. 연구 조건 변경, 기존 파일 삭제, 과거 OOS 변경, WSL EIO 복구는 이 설치 작업의 범위가 아니다.

이 문서는 이미 GitHub에 저장된 다음 파일을 **실제 Windows Codex에 동기화**하는 절차다. GitHub에 등록한 것만으로 별도 Windows Codex 프로필에 자동 적용되지는 않는다.

### 원격 기준 파일

- `.agents/skills/github-backtest-report/SKILL.md`
- `.agents/skills/github-backtest-report/scripts/preflight_storage.py`
- `.agents/skills/github-backtest-report/scripts/verify_batch.py`
- 저장소 루트 `AGENTS.md`

### Codex가 한 번 실행할 설치 작업

1. 현재 Codex 설치의 홈 디렉터리(`$env:USERPROFILE\.codex` 또는 실제 `CODEX_HOME`)와 프로젝트 작업 루트를 **읽기 전용**으로 확인한다.
2. 기존 `github-backtest-report` 스킬과 사용자 전역·프로젝트 `AGENTS.md`를 D:\Codex_Backups 하위에 버전명으로 백업하고 해시를 기록한다. 별도 C 복사본을 만들지 않는다.
3. 위 GitHub 스킬의 `SKILL.md`, `scripts\preflight_storage.py`, `scripts\verify_batch.py`를 기존 로컬 `github-backtest-report`에 **동기화**한다. 해당 스킬의 기존 다른 지원 파일(`references`, 사용자 설정 등)은 보존한다.
4. 로컬 사용자 전역 `AGENTS.md` 및 현재 테더 롱 + 달러선물 숏 프로젝트의 `AGENTS.md`에 저장 규칙을 지정된 관리 구간으로 *추가하거나 업데이트*한다. 다른 지침은 그대로 보존한다. 중복 블록을 생성하지 않는 방식으로 적용한다.
5. 미래 백테스트를 실행하기 전에 작업 출력 경로·TMP/TEMP·캐시·로그·체크포인트가 `D:\Codex_Research`에 설정되는지 코드에서 확인한다. 스크립트 옆으로 출력을 만드는 기존 C 기반 코드에는 출력 루트 설정을 추가한다. 원본 전략 조건과 기존 상태는 유지한다.
6. `D:\Codex_Research`에 **아주 작은 텍스트 테스트 파일만** 생성하고 읽기·SHA-256을 확인한다. 다른 드라이브에는 테스트 데이터를 쓰지 않는다.
7. 공개 GitHub 저장소에 민감정보 없는 소형 테스트 보고서를 새 테스트 폴더에 업로드하고, 원격 저장소에서 다시 파일을 가져와 내용 및 SHA-256을 대조한다.
8. 설치 전후 D: 경로, C:/D: 여유 공간, 스킬 파일 해시, 글로벌/프로젝트 AGENTS 적용 여부, GitHub 테스트 커밋 SHA와 업로드 상태를 보고한다. GitHub 업로드가 실패하면 설치 완료로 보고하지 않는다.
9. 실제 연구 배치는 **C: 여유공간이 10GiB 이상, D: 여유공간이 10GiB 이상이며 예상 데이터량을 충분히 감당할 때만** 재개한다. C: 부족 또는 WSL EIO 지속 시 설치 검증까지만 진행하고 대용량 연구/수집기 재시작은 하지 않는다.

### 의무적인 결과 보고 포맷

- `LOCAL_SKILL_SYNCED` 또는 실패 사유
- `GLOBAL_AND_PROJECT_AGENTS_UPDATED` 여부
- `D_STORAGE_TEST_OK` 여부
- `GITHUB_TEST_PUBLISHED_VERIFIED` + 커밋 SHA
- `C_FREE_GIB`, `D_FREE_GIB`
- `LONG_RESEARCH_BLOCKED` 여부 및 이유
- 최종 배치 경로와 이후 기본 D: 출력 경로

**주의:** 기록용 GitHub 스킬이 설치되어도 기존 OpenClaw의 WSL EIO 오류가 해결되는 것은 아니다. 실험용 파일 외에는 삭제·이동·재실행하지 않는다.

## Codex에 전달할 한 번의 명령 (복사)

> GitHub 저장소 `jeh183000-art/-`의 `INSTALL_WINDOWS_KO.md`를 열고 `.agents/skills/github-backtest-report/SKILL.md`를 로컬 기존 스킬에 동기화하라. 사용자 전역과 현재 USDT/KRW–KRX 프로젝트 AGENTS.md에도 D: 작업저장/GitHub 검증업로드 규칙을 영구 적용하라. 기존 지침과 자료는 보존하고 설치만 확인하라. C: 용량과 WSL EIO 때문에 연구·수집은 재시작하지 마라. 모든 적용 결과와 GitHub 테스트 커밋 SHA를 보고하라.
