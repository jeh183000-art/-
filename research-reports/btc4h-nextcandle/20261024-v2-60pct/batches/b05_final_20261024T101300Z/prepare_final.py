#!/usr/bin/env python3
"""Prepare the immutable final V2 publication after four verified batch uploads.

No upload, model fit, parameter change or raw candle access occurs here. The
large G1--G4 result folders stay in their exact-commit batch publications.
Their receipts and hash-checked restoration index accompany the final report.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import re
import shutil
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent
REPOSITORY = 'jeh183000-art/-'
ARCHIVE_ROOT = 'research-reports/btc4h-nextcandle/20261024-v2-60pct/batches'
GROUPS = ('G1', 'G2', 'G3', 'G4')
SOURCE_FILES = (
    'engine_v2.py', 'features_v2.py', 'data_loader_v2.py', 'reproduce_inputs.py',
    'audit_v2.py', 'test_engine_v2.py', 'test_features_v2.py',
    'predict_example.py', 'build_final_report.py', 'prepare_batch.py', 'prepare_final.py',
)
ROOT_EVIDENCE = (
    'settings.json', 'preregistration.json', 'engine_freeze.json',
    'feature_specification.json', 'independent_engine_review.json',
    'README_KO.md', 'REPORT_KO.md', 'requirements.txt',
)
REQUIRED_ROLES = {'strategy_code', 'settings', 'results_csv', 'fills', 'costs',
                  'statistics_report', 'environment'}
SECRET = re.compile(
    rb"(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|"
    rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|"
    rb"(?i:app[_-]?(?:key|secret)|api[_-]?key|access[_-]?token)\s*[:=]\s*"
    rb"[\"'][A-Za-z0-9+/=_-]{16,}[\"'])")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')


def safe_relative(name):
    path = PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts or '\\' in name or ':' in name:
        raise ValueError('Unsafe archive path: ' + name)
    if any(part.startswith('.') or part in ('__pycache__', 'raw') for part in path.parts):
        raise ValueError('Excluded archive path: ' + name)
    return path


def verified_batches(root):
    batches = []
    for index, group in enumerate(GROUPS, 1):
        receipt_path = root / 'receipts' / f'{group}.json'
        if not receipt_path.is_file():
            raise FileNotFoundError(f'{group} remote verification receipt is not ready')
        receipt = read_json(receipt_path)
        files = receipt.get('files', [])
        if (receipt.get('status') != 'PUBLISHED_VERIFIED' or receipt.get('repository') != REPOSITORY or
                receipt.get('failures') or not files or
                receipt.get('verified_count') != receipt.get('expected_count') or
                len(files) != receipt.get('verified_count')):
            raise ValueError('Incomplete remote verification: ' + group)
        commit, prefix = receipt['commit'], receipt['prefix']
        if not re.fullmatch(r'[a-f0-9]{40}', commit):
            raise ValueError('An exact full Git commit is required: ' + group)
        if not prefix.startswith(f'{ARCHIVE_ROOT}/b{index:02d}_{group}_'):
            raise ValueError('Receipt points outside the expected group archive: ' + group)
        names = [item['path'] for item in files]
        if len(set(names)) != len(names):
            raise ValueError('Duplicate paths in remote verification receipt: ' + group)
        for item in files:
            safe_relative(item['path'])
            if item.get('status') != 'MATCH' or not re.fullmatch(r'[a-f0-9]{64}', item['sha256']):
                raise ValueError('Unverified remote file: ' + group + '/' + item['path'])
        entries = {item['path']: item for item in files}
        completion_name = f'results/{group}/completion.json'
        completion = root / completion_name
        if completion_name not in entries or sha(completion) != entries[completion_name]['sha256']:
            raise ValueError('Local group completion differs from its verified publication: ' + group)
        local_batch = root / 'publications' / PurePosixPath(prefix).name
        if not (local_batch / 'manifest.csv').is_file():
            raise FileNotFoundError('The verified local immutable batch is missing: ' + group)
        if 'manifest.csv' not in entries or sha(local_batch / 'manifest.csv') != entries['manifest.csv']['sha256']:
            raise ValueError('Local batch manifest differs from the verified remote manifest: ' + group)
        restored_files = []
        for item in files:
            if item['path'].startswith(f'results/{group}/'):
                source = local_batch / item['path']
                if not source.is_file() or source.stat().st_size != item['bytes'] or sha(source) != item['sha256']:
                    raise ValueError('Immutable local batch bytes changed: ' + group + '/' + item['path'])
                restored_files.append({key: item[key] for key in ('path', 'bytes', 'sha256')})
        if not restored_files:
            raise ValueError('The complete development result folder is absent: ' + group)
        batches.append({
            'group': group, 'status': 'PUBLISHED_VERIFIED', 'repository': REPOSITORY,
            'commit': commit, 'prefix': prefix,
            'url': f'https://github.com/{REPOSITORY}/tree/{commit}/{prefix}',
            'raw_url_base': f'https://raw.githubusercontent.com/{REPOSITORY}/{commit}/{prefix}',
            'manifest_sha256': entries['manifest.csv']['sha256'],
            'receipt_file': f'receipts/{group}.json', 'receipt_sha256': sha(receipt_path),
            'remote_verified_files': receipt['verified_count'],
            'remote_verified_bytes': sum(item['bytes'] for item in files),
            'restore_destination': f'results/{group}',
            'restoration_file_count': len(restored_files),
            'restoration_files': sorted(restored_files, key=lambda item: item['path']),
        })
    return batches


def validate_results(root):
    results = root / 'results'
    freeze = read_json(root / 'engine_freeze.json')
    for name, expected in freeze['code_sha256'].items():
        if sha(root / name) != expected:
            raise ValueError('Frozen source changed: ' + name)
    selection = read_json(results / 'selection.json')
    evaluation = results / 'evaluation'
    completion = read_json(evaluation / 'completion.json')
    if completion.get('status') != 'COMPLETE' or completion.get('model_status') != 'OK':
        raise ValueError('A complete successful frozen evaluation is required')
    if completion['selection_sha256'] != sha(results / 'selection.json'):
        raise ValueError('Evaluation is tied to a different selection')
    actual = {p.relative_to(evaluation).as_posix() for p in evaluation.rglob('*') if p.is_file()}
    if actual != set(completion['sha256']) | {'completion.json'}:
        raise ValueError('Unexpected or missing evaluation files')
    for name, expected in completion['sha256'].items():
        if sha(evaluation / name) != expected:
            raise ValueError('Completed evaluation output changed: ' + name)
    summary = read_json(evaluation / 'evaluation_summary.json')
    if summary['point_60_percent_goal_met'] is not False:
        raise ValueError('This final publication records the observed V2 target miss')
    for phase in (*GROUPS, 'development', 'evaluation'):
        audit = read_json(results / f'audit_{phase}.json')
        if audit.get('status') != 'PASS' or audit.get('checks_failed') != 0:
            raise ValueError('A required independent audit did not pass: ' + phase)
    smoke = read_json(results / 'prediction_smoke.json')
    if smoke.get('status') != 'PASS' or smoke['absolute_probability_error'] > 1e-10:
        raise ValueError('Historical model inference did not reproduce its ledger')
    generation = read_json(results / 'report_generation.json')
    for name, key in [('REPORT_KO.md', 'report_sha256'),
                      ('build_final_report.py', 'generator_sha256'),
                      ('results/final_comparison.csv', 'comparison_sha256'),
                      ('results/selection.json', 'selection_sha256'),
                      ('results/evaluation/completion.json', 'evaluation_completion_sha256')]:
        if sha(root / name) != generation[key]:
            raise ValueError('Final report is stale relative to its source: ' + name)
    with (results / 'all_development_results.csv').open(newline='', encoding='utf-8') as stream:
        rows = list(csv.DictReader(stream))
    keys = {(row['predictor'], row['policy']) for row in rows}
    if len(rows) != 1344 or len(keys) != 448:
        raise ValueError('All 448 combinations and all three scoring periods are required')
    for predictor, policy in keys:
        periods = [row['period'] for row in rows if row['predictor'] == predictor and row['policy'] == policy]
        if sorted(periods) != ['2024', '2025', 'ALL']:
            raise ValueError('A registered candidate lacks its complete scoring history')
    return selection, summary, freeze


def build(root, out, prefix):
    out = out.resolve()
    if out.exists():
        raise FileExistsError('Prepared or published folders are immutable; choose a new folder')
    if out.parent != (root / 'publications').resolve() or not re.fullmatch(r'b05_final_20261024T\d{6}Z', out.name):
        raise ValueError('Use publications/b05_final_20261024THHMMSSZ for this final batch')
    if prefix != ARCHIVE_ROOT + '/' + out.name:
        raise ValueError('The final repository prefix must match its immutable local folder')
    batches = verified_batches(root)
    selection, summary, freeze = validate_results(root)
    sources = {}

    def plan(source, name=None, role='evidence'):
        source = Path(source)
        name = name or source.relative_to(root).as_posix()
        safe_relative(name)
        if not source.is_file() or source.is_symlink():
            raise ValueError('Missing or unsafe source file: ' + str(source))
        if name in sources:
            raise ValueError('Duplicate planned archive path: ' + name)
        data = source.read_bytes()
        if SECRET.search(data):
            raise ValueError('Possible credential literal; source withheld: ' + name)
        if len(data) > 45 * 1024 * 1024:
            raise ValueError('Large source requires lossless archive or LFS: ' + name)
        sources[name] = {'path': source, 'role': role, 'bytes': len(data),
                         'sha256': hashlib.sha256(data).hexdigest()}

    for name in SOURCE_FILES:
        plan(root / name, role='strategy_code' if name == 'engine_v2.py' else 'verification_code')
    for name in ROOT_EVIDENCE:
        role = ('settings' if name == 'settings.json' else
                'statistics_report' if name == 'REPORT_KO.md' else 'evidence')
        plan(root / name, role=role)
    for path in sorted((root / 'reference').rglob('*')):
        if path.is_file() and path.suffix in ('.py', '.json', '.md') and '__pycache__' not in path.parts:
            plan(path, role='reference_code')
    for path in sorted((root / 'data').rglob('*')):
        if path.is_file() and path.suffix in ('.json', '.csv') and 'raw' not in path.relative_to(root).parts:
            plan(path, role='input_provenance')
    for path in sorted((root / 'results').iterdir()):
        if not path.is_file() or path.name.startswith('.'):
            continue
        if path.name.lower().startswith(('upload_', 'publication_', 'transfer_', 'stage_')):
            continue
        if path.suffix not in ('.json', '.csv', '.md', '.log', '.txt'):
            raise ValueError('Unexpected top-level result file; review before publishing: ' + path.name)
        role = ('execution_log' if path.suffix == '.log' else
                'audit' if path.name.startswith('audit_') else 'results_evidence')
        plan(path, role=role)
    for path in sorted((root / 'results' / 'evaluation').rglob('*')):
        if not path.is_file():
            continue
        role = ('model_artifact' if path.suffix == '.joblib' else
                'prediction_ledger' if 'predictions' in path.name else 'evaluation_evidence')
        plan(path, role=role)
    for group in GROUPS:
        plan(root / 'receipts' / f'{group}.json', role='remote_verification_receipt')
    plan(root / 'results' / 'G1' / 'environment.json', 'environment.json', 'environment')
    plan(root / 'results' / 'all_development_results.csv', 'results.csv', 'results_csv')
    for name in ('verify_archive_batch.py', 'verify_remote_publication.py'):
        plan(root.parent / name, 'verification/' + name, 'verification_code')
    # All gates and content checks pass before a new publication is created.
    out.mkdir(parents=True)
    roles = {}
    for name, item in sorted(sources.items()):
        target = out / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item['path'], target)
        if target.stat().st_size != item['bytes'] or sha(target) != item['sha256']:
            raise ValueError('Source changed while preparing publication: ' + name)
        roles[name] = item['role']

    def put(name, value, role):
        write_json(out / name, value)
        roles[name] = role

    def put_csv(name, columns, rows, role):
        with (out / name).open('w', newline='', encoding='utf-8') as stream:
            writer = csv.DictWriter(stream, fieldnames=columns, lineterminator='\n')
            writer.writeheader()
            writer.writerows(rows)
        roles[name] = role

    put_csv('trades.csv', ['trade_id', 'entry_time', 'exit_time', 'side', 'quantity', 'pnl'], [], 'fills')
    put_csv('cycles.csv', ['cycle_id', 'entry_time', 'exit_time', 'net_return'], [], 'cycles')
    costs = {'status': 'NOT_APPLICABLE_CLASSIFICATION_ONLY', 'actual_orders': 0,
             'trading_backtests': 0, 'future_roundtrip_fee_assumption': .0012,
             'funding_evaluated': False, 'slippage_evaluated': False}
    put_csv('costs.csv', list(costs), [costs], 'costs')
    put('batch_archives.json', {
        'study': 'BTC4H_NEXTCANDLE_V2_60PCT_20261024', 'repository': REPOSITORY,
        'all_four_batches_remote_verified': True,
        'development_result_folders_duplicated_in_final': False,
        'restoration': 'Read ARCHIVE_KO.md; fetch exact-commit bytes and verify size/SHA256 before saving.',
        'batches': batches,
    }, 'provenance')
    put('checkpoint.json', {
        'study': 'BTC4H_NEXTCANDLE_V2_60PCT_20261024', 'phase': 'FINAL', 'status': 'COMPLETE',
        'development_predictor_policy_combinations': 448, 'development_base_model_fold_fits': 320,
        'selected_predictor': selection['predictor'], 'selected_policy': selection['policy'],
        'point_60_percent_goal_met': False,
        'selected_accuracy': summary['selected_metrics']['accuracy'],
        'selected_non_doji_count': summary['selected_metrics']['scored_count'],
        'full_accuracy': summary['full_coverage_metrics']['accuracy'],
        'no_model_or_policy_switch_after_evaluation': True, 'independent_audits': 'PASS',
        'historical_model_inference': 'PASS', 'actual_orders': 0, 'trading_backtests': 0,
        'development_archives': 'FOUR_BATCHES_PUBLISHED_VERIFIED',
        'final_publication': 'REMOTE_VERIFICATION_REQUIRED',
    }, 'checkpoint')
    put('provenance.json', {
        'prepared_at_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
        'repository': REPOSITORY, 'archive_prefix': prefix,
        'source': 'https://github.com/binance/binance-public-data',
        'official_monthly_archive_root': 'https://data.binance.vision/data/futures/um/monthly/klines/',
        'raw_inputs_uploaded': False,
        'input_reproduction': 'Public official monthly archive URLs, official checksums and frozen normalized SHA256',
        'canonical_prices_and_target': 'Official BTCUSDT four-hour trade-price candles',
        'development_data_sha256': freeze['development_data_sha256'],
        'evaluation_data_sha256': freeze['holdout_data_sha256'],
        'code_sha256': freeze['code_sha256'],
        'selection_sha256': sha(root / 'results' / 'selection.json'),
        'final_report_sha256': sha(root / 'REPORT_KO.md'),
        'parent_v1_commit': read_json(root / 'settings.json')['parent_commit'],
        'development_ledger_location': 'Exact commits and restoration inventory in batch_archives.json',
        'evaluation_ledgers': 'Complete gzip and plaintext monthly/quarterly shards in results/evaluation/',
        'input_preparation_status_files': 'Historical collection-stage metadata; final evaluation status is in checkpoint.json and results/evaluation/completion.json',
        'trading_profitability': 'NOT_EVALUATED',
        'protected_prior_research_modified': False,
        'environment_scope': 'Isolated cloud Linux workspace; no user Windows C:/D: or WSL access',
    }, 'provenance')
    batch_rows = '\n'.join(
        f"| {b['group']} | `{b['commit']}` | [{PurePosixPath(b['prefix']).name}]({b['url']}) | {b['restoration_file_count']} |"
        for b in batches)
    archive_text = f'''# 최종 보관 묶음과 개발 원장 복원

이 폴더에는 최종 보고서, 448개 조합의 모든 기간별 결과, 전체 연구 코드·설정·출처,
감사 기록, 최종 평가 원장과 저장 모델이 있다. 루트 `results.csv`는
`results/all_development_results.csv`와 바이트가 같은 **1,344행** 파일이다.
448개 조합 각각의 2024·2025·합계 행을 포함한다.

G1~G4의 큰 개발 원장은 이미 원격 바이트 검증을 통과한 아래 배치에 모두 있다.
최종 묶음에서는 중복 저장하지 않았으며, 정확한 커밋과 파일별 해시를
`batch_archives.json` 및 `receipts/`에 포함했다.

| 그룹 | 정확한 커밋 | 완전한 개발 배치 | 복원할 결과 파일 수 |
|---|---|---|---|
{batch_rows}

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
                              headers={{"User-Agent": "BTC4H-research-restoration"}})
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

최종 보관 경로: `{prefix}`.
'''
    (out / 'ARCHIVE_KO.md').write_text(archive_text, encoding='utf-8')
    roles['ARCHIVE_KO.md'] = 'restoration_instructions'
    # All report-relative evidence must be available in this final package.
    links = re.findall(r'\]\(([^)]+)\)', (out / 'REPORT_KO.md').read_text(encoding='utf-8'))
    for link in links:
        if link.startswith(('https://', 'http://', '#')):
            continue
        safe_relative(link)
        if not (out / link).is_file():
            raise ValueError('Final report evidence link is missing: ' + link)
    if REQUIRED_ROLES - set(roles.values()):
        raise ValueError('Missing required publication role')
    with (out / 'manifest.csv').open('w', newline='', encoding='utf-8') as stream:
        writer = csv.writer(stream, lineterminator='\n')
        writer.writerow(['path', 'role', 'bytes', 'sha256'])
        for name, role in sorted(roles.items()):
            path = out / name
            writer.writerow([name, role, path.stat().st_size, sha(path)])
    actual = {p.relative_to(out).as_posix() for p in out.rglob('*') if p.is_file()}
    if actual != set(roles) | {'manifest.csv'}:
        raise ValueError('Unmanifested final publication file')
    print(json.dumps({'prepared': str(out), 'prefix': prefix, 'files': len(roles) + 1,
                      'bytes': sum((out / name).stat().st_size for name in actual),
                      'verified_development_batches': len(batches),
                      'report_relative_links_resolved': len(links),
                      'development_directories_duplicated': False,
                      'point_60_percent_goal_met': False}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--prefix', required=True)
    args = parser.parse_args()
    build(args.root.resolve(), args.out, args.prefix)


if __name__ == '__main__':
    main()
