# 최종 보관 묶음과 개발 원장 복원

이 폴더에는 최종 보고서, 448개 조합의 모든 기간별 결과, 전체 연구 코드·설정·출처,
감사 기록, 최종 평가 원장과 저장 모델이 있다. 루트 `results.csv`는
`results/all_development_results.csv`와 바이트가 같은 **1,344행** 파일이다.
448개 조합 각각의 2024·2025·합계 행을 포함한다.

G1~G4의 큰 개발 원장은 이미 원격 바이트 검증을 통과한 아래 배치에 모두 있다.
최종 묶음에서는 중복 저장하지 않았으며, 정확한 커밋과 파일별 해시를
`batch_archives.json` 및 `receipts/`에 포함했다.

| 그룹 | 정확한 커밋 | 완전한 개발 배치 | 복원할 결과 파일 수 |
|---|---|---|---|
| G1 | `4490fa6417a2afd101a747fbf51ace1697dcf78b` | [b01_G1_20261024T054335Z](https://github.com/jeh183000-art/-/tree/4490fa6417a2afd101a747fbf51ace1697dcf78b/research-reports/btc4h-nextcandle/20261024-v2-60pct/batches/b01_G1_20261024T054335Z) | 45 |
| G2 | `f77f1898fa9e5b7a902830aea5bab4fed52499e7` | [b02_G2_20261024T054456Z](https://github.com/jeh183000-art/-/tree/f77f1898fa9e5b7a902830aea5bab4fed52499e7/research-reports/btc4h-nextcandle/20261024-v2-60pct/batches/b02_G2_20261024T054456Z) | 45 |
| G3 | `9585003d5317fe5ae099afb25e32e1cb4baa8e0b` | [b03_G3_20261024T054629Z](https://github.com/jeh183000-art/-/tree/9585003d5317fe5ae099afb25e32e1cb4baa8e0b/research-reports/btc4h-nextcandle/20261024-v2-60pct/batches/b03_G3_20261024T054629Z) | 45 |
| G4 | `b331059b51b3035465c084a73fd8bf099648adbd` | [b04_G4_20261024T054756Z](https://github.com/jeh183000-art/-/tree/b331059b51b3035465c084a73fd8bf099648adbd/research-reports/btc4h-nextcandle/20261024-v2-60pct/batches/b04_G4_20261024T054756Z) | 45 |

개발 원장은 전체 gzip CSV와 월별 평문 예측 CSV, 분기별 평문 보정 CSV를 포함한다.
최종 평가의 같은 형태 원장과 모델은 이 폴더의 `results/evaluation/`에 전부 있다.
이 폴더에서 보고서의 증거 링크는 바로 열 수 있다. 개발 원장까지 다시 감사하려면
아래처럼 동일한 `results/G1`~`results/G4` 경로를 복원한다.

## 정확한 커밋에서 결과 폴더 복원

다음 Python 3 코드를 최종 묶음 폴더에서 실행한다. 공개 GitHub의 고정 커밋만 읽고,
각 파일의 크기와 SHA256이 맞는 경우에만 저장한다. 이미 있는 파일이 다른 내용이면
덮어쓰지 않고 중단한다. 시세 재수집이나 모델 재학습은 하지 않는다.

```python
import hashlib
import json
from pathlib import Path, PurePosixPath
from urllib.request import Request, urlopen

root = Path.cwd().resolve()
index = json.loads((root / "batch_archives.json").read_text())
for batch in index["batches"]:
    for item in batch["restoration_files"]:
        relative = PurePosixPath(item["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Unsafe result path")
        target = root / relative
        if not target.resolve().is_relative_to(root):
            raise ValueError("Result path escapes the destination")
        if target.exists():
            data = target.read_bytes()
        else:
            request = Request(batch["raw_url_base"] + "/" + item["path"],
                              headers={"User-Agent": "BTC4H-research-restoration"})
            with urlopen(request, timeout=30) as response:
                data = response.read()
        if len(data) != item["bytes"] or hashlib.sha256(data).hexdigest() != item["sha256"]:
            raise ValueError("Result bytes differ: " + item["path"])
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as stream:
                stream.write(data)
    print(batch["group"], "RESTORED_AND_HASH_VERIFIED")
```

공식 시세 입력은 보고서와 `README_KO.md`의 재현 명령으로 준비한다. 입력 해시가
맞고 개발 결과 폴더를 복원한 뒤 `python audit_v2.py --phase development`로
기존 개발 선택을 다시 점검할 수 있다. 이미 존재하는 평가 결과를 다시 학습하거나
선별 기준을 바꾸지 않는다.

## 묶음 자체의 무결성

`manifest.csv`는 자신을 제외한 모든 파일의 경로·역할·바이트 수·SHA256을 기록하며
LF 줄바꿈을 사용한다. 로컬 검사:

```bash
python verification/verify_archive_batch.py .
```

최종 묶음의 공개 커밋이 생성된 뒤에는 정확한 커밋을 지정해
`verification/verify_remote_publication.py`로 원격 파일을 다시 확인할 수 있다.
이 폴더 안의 G1~G4 영수증은 이미 검증된 이전 배치에 관한 것이다. 최종 묶음의
원격 검증 영수증은 자기 참조를 피하도록 묶음 밖에 별도로 기록한다.

최종 보관 경로: `research-reports/btc4h-nextcandle/20261024-v2-60pct/batches/b05_final_20261024T101300Z`.
