#!/usr/bin/env python3
"""Prepare an immutable, whitelisted development-batch publication; no upload.

The complete prediction/calibration ledgers, failures and all policies are kept.
Raw exchange archives are reproducible from public URLs and checked hashes.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import shutil
from pathlib import Path

import pandas as pd

import engine_v2

ROOT = Path(__file__).resolve().parent


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(engine_v2.native(value), indent=2, ensure_ascii=False,
                               allow_nan=False) + '\n', encoding='utf-8')


def pct(value):
    return '해당 없음' if pd.isna(value) else f'{value * 100:.2f}%'


def build(group, out, prefix, audit_path):
    out = Path(out).resolve()
    if out.exists():
        raise FileExistsError('Published/prepared batches are immutable; choose a new folder')
    folder = ROOT / 'results' / group
    completion = json.loads((folder / 'completion.json').read_text())
    settings = json.loads((ROOT / 'settings.json').read_text())
    freeze = json.loads((ROOT / 'engine_freeze.json').read_text())
    audit = json.loads(Path(audit_path).read_text())
    if completion['status'] != 'COMPLETE' or audit.get('status') != 'PASS':
        raise ValueError('Complete results and a passing independent audit are required')
    if digest(ROOT / 'settings.json') != freeze['settings_sha256']:
        raise ValueError('Frozen settings changed')
    if completion['config']['engine_sha256'] != digest(ROOT / 'engine_v2.py'):
        raise ValueError('Development code changed')
    table = engine_v2.read_csv(folder / 'results.csv')
    ranking = engine_v2.rank_candidates(table, settings)
    if len(ranking) != 112 or len(table) != 336:
        raise ValueError('The complete 14 predictors x 8 policies x 3 periods are required')
    out.mkdir(parents=True)
    roles = {}

    def copy(source, destination=None, role='evidence'):
        source = Path(source)
        target_name = destination or source.relative_to(ROOT).as_posix()
        target = out / target_name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        roles[target_name] = role

    def put(name, obj, role):
        write_json(out / name, obj)
        roles[name] = role

    for name in ['engine_v2.py', 'features_v2.py', 'data_loader_v2.py', 'reproduce_inputs.py',
                 'audit_v2.py', 'test_features_v2.py', 'test_engine_v2.py', 'prepare_batch.py']:
        copy(ROOT / name, role='strategy_code' if name == 'engine_v2.py' else 'verification_code')
    for name in ['README_KO.md', 'requirements.txt', 'preregistration.json', 'engine_freeze.json',
                 'feature_specification.json', 'independent_engine_review.json']:
        if (ROOT / name).exists():
            copy(ROOT / name)
    copy(ROOT / 'settings.json', role='settings')
    for source in sorted((ROOT / 'reference').iterdir()):
        if source.is_file() and source.suffix in ('.py', '.json'):
            copy(source, role='reference_code')
    for scope in ('development', 'holdout_2026'):
        for source in sorted((ROOT / 'data' / scope).iterdir()):
            if source.is_file() and source.suffix in ('.json', '.csv'):
                copy(source, role='input_provenance')
    # Explicit result-folder scope. No hidden files, caches, data or secrets.
    for source in sorted(folder.rglob('*')):
        if not source.is_file() or source.name.startswith('.') or '__pycache__' in source.parts:
            continue
        role = 'prediction_ledger' if 'predictions' in source.name else 'results_evidence'
        if source.name == 'environment.json':
            role = 'environment'
        copy(source, role=role)
    copy(folder / 'results.csv', 'results.csv', 'results_csv')
    copy(Path(audit_path), 'independent_audit.json', 'audit')
    for source in sorted((ROOT / 'results').glob(f'audit_{group}*')):
        if source.is_file() and source.resolve() != Path(audit_path).resolve():
            copy(source, role='audit')
    recomputed = ROOT / 'results' / f'audit_recomputed_{group}_results.csv'
    if recomputed.exists():
        copy(recomputed, role='audit')
    interpretation = ROOT / 'results' / f'{group}_interpretation.json'
    if interpretation.exists():
        copy(interpretation, role='independent_interpretation')
    log = ROOT / 'results' / f'{group}_run.log'
    if log.exists():
        copy(log, 'run.log', 'execution_log')
    engine_v2.save_csv(ranking, out / 'batch_ranking.csv')
    roles['batch_ranking.csv'] = 'ranking'
    for name, columns in [('trades.csv', ['trade_id', 'entry_time', 'exit_time', 'side', 'quantity', 'pnl']),
                          ('cycles.csv', ['cycle_id', 'entry_time', 'exit_time', 'net_return'])]:
        pd.DataFrame(columns=columns).to_csv(out / name, index=False, lineterminator='\n')
        roles[name] = 'fills' if name == 'trades.csv' else 'cycles'
    pd.DataFrame([{'status': 'NOT_APPLICABLE_CLASSIFICATION_ONLY', 'actual_orders': 0,
                   'trading_backtests': 0, 'future_roundtrip_fee_assumption': .0012,
                   'funding_evaluated': False, 'slippage_evaluated': False}]).to_csv(
        out / 'costs.csv', index=False, lineterminator='\n')
    roles['costs.csv'] = 'costs'
    eligible = ranking[ranking.eligible]
    top = eligible.head(5)
    leaderboard = []
    for row in top.itertuples():
        f = table[(table.predictor == row.predictor) & (table.policy == row.policy)].set_index('period')
        a, b = f.loc['2024'], f.loc['2025']
        leaderboard.append(f'| {row.predictor} | {row.policy} | {pct(a.accuracy)} ({int(a.scored_count):,}) | '
                           f'{pct(b.accuracy)} ({int(b.scored_count):,}) | {pct(row.combined_accuracy)} |')
    lines = '\n'.join(leaderboard) or '| 없음 | — | — | — | — |'
    group_text = {'G1': '기존 38개 특징', 'G2': '확장한 77개 4시간봉 특징',
                  'G3': '15분봉 내부 흐름을 포함한 104개 특징',
                  'G4': 'ETH 상대 정보를 포함한 122개 특징'}[group]
    failed = sum(v != 'OK' for v in completion['predictor_status'].values())
    report = f'''# BTC 4시간봉 60% 목표 연구: {group} 개발 배치

이 배치는 **{group_text}**으로 10개 모델 설정과 4개 고정 앙상블을 비교했다.
각각 8개 예측 선별 기준을 적용해 **112개 조합**을 기록했다. 전체 계획은
4개 배치, 모델 설정 40개 + 앙상블 16개, 선별 기준까지 포함해 **448개 조합**이다.
이번 결과는 후보 선택용 **2024~2025년 개발 성적**이다. 2026년 최종 평가 결과가 아니다.

## 사전 기준을 통과한 배치 내 상위 후보

두 해 각각 200개 이상, 한 달에 5개 이상 예측한 달이 8개월 이상,
특정 한 달의 비중 25% 이하를 요구했다. 이는 연구자가 정한 검증 기준이다.
두 해 중 낮은 적중률을 우선하고, 결합 적중률·표본 수·전체 log loss로 동률을 처리했다.

| 후보 | 선별 기준 | 2024 적중률 (평가 수) | 2025 적중률 (평가 수) | 결합 적중률 |
|---|---|---:|---:|---:|
{lines}

적격 조합 **{len(eligible)} / 112개**, 실패 또는 실패 모델을 포함한 후보 **{failed} / 14개**.
표의 상위 5개뿐 아니라 탈락·실패·신호 0개를 포함한 전체 결과가 `results.csv`에 있다.
정확한 실패 원인은 배치의 `failures.json`, 탈락 사유는 `batch_ranking.csv`에 있다.

## 기준 해석과 검증

`A500`은 전체 예측, `A525`~`A625`는 모델 확신도 52.5%~62.5% 이상인 예측이다.
`Q70`과 `Q85`는 해당 분기 이전의 확률 보정 자료에서 확신도 70·85분위수를 정한다.
평가 분기의 확신도 순위를 보고 선별하지 않는다. 모델 확신도와 실제 적중률은 다른 수치다.

모델은 각 분기 이전 자료로만 학습하며, 180일의 별도 확률 보정 구간을 둔다.
학습 정답은 보정 시작 전에, 보정 정답은 평가 분기 전에 확정되어야 한다.
표준화·결측 대체는 기본 학습 자료에만 맞춘다. 어느 한 분기라도 실패한 모델과
그 모델을 포함하는 앙상블은 최종 후보에서 제외한다.

예측 원장·보정 원장·분기 경계·모든 월별 성적·동일 선별 시점의 단순 기준 성적을 보존했다.
독립 재계산 감사 상태는 **{audit['status']}**이며 상세 검사는 `independent_audit.json`에 있다.
전체 계획의 최종 후보 선택은 4개 배치가 모두 끝난 뒤 한 번만 수행한다.
2026년 평가에서 후보를 바꾸거나 결과를 보고 새 임계값을 고르지 않는다.

## 재현과 범위

`pip install -r requirements.txt` 후 공식 원본은 `python reproduce_inputs.py --scope development`로 재현한다.
원본 월별 ZIP의 공식 체크섬과 정규화 파일 해시는 `data/`의 출처 기록에 있다.
학습 실행은 `python engine_v2.py --phase development --group {group}`이다.
기존 결과 폴더를 덮어쓰지 않도록 깨끗한 재현 복사본에서 실행한다.

현재 4시간봉이 닫힌 뒤 다음 봉의 종가와 그 봉의 시가를 비교하는 연구다.
보합을 시간축에서 삭제하지 않고 이진 채점에서만 제외한다.
공식 4시간봉과 15분봉 합산의 알려진 4개 필드 불일치 구간은 수정하지 않았다.
주문·매매 백테스트는 0건이며, 수익률·PF·MDD를 산출하지 않았다.

공개 보관 경로: `{prefix}`. 실제 게시 커밋과 원격 바이트 검증 결과는 별도 게시 영수증에 기록한다.
'''
    (out / 'report.md').write_text(report, encoding='utf-8')
    roles['report.md'] = 'statistics_report'
    put('checkpoint.json', {'study': settings['study_id'], 'group': group, 'phase': 'DEVELOPMENT',
        'status': 'COMPLETE', 'eligible_combinations': len(eligible), 'registered_combinations': 112,
        'holdout_performance_inspected_during_development_run': False,
        'publication_prepared_after_evaluation': (ROOT / 'results/evaluation/completion.json').exists(),
        'independent_audit': audit['status'],
        'actual_orders': 0, 'trading_backtests': 0, 'publication': 'REMOTE_VERIFICATION_REQUIRED'}, 'checkpoint')
    put('provenance.json', {'prepared_at_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
        'prefix': prefix, 'source': 'https://github.com/binance/binance-public-data',
        'raw_inputs_uploaded': False, 'input_reproduction': 'Public official archive URLs and SHA256',
        'all_registered_results_included': True, 'prior_protected_research_modified': False,
        'parent_v1_commit': settings['parent_commit'], 'config': completion['config'],
        'canonical_prices': 'Official 4h', 'trading_profitability': 'NOT_EVALUATED'}, 'provenance')
    with (out / 'manifest.csv').open('w', newline='', encoding='utf-8') as stream:
        writer = csv.writer(stream, lineterminator='\n')
        writer.writerow(['path', 'role', 'bytes', 'sha256'])
        for name, role in sorted(roles.items()):
            path = out / name
            writer.writerow([name, role, path.stat().st_size, digest(path)])
    print(json.dumps({'prepared': str(out), 'files': len(roles)+1,
                      'bytes': sum(f.stat().st_size for f in out.rglob('*') if f.is_file()),
                      'prefix': prefix, 'eligible': len(eligible)}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--group', required=True, choices=['G1', 'G2', 'G3', 'G4'])
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--prefix', required=True)
    parser.add_argument('--audit', type=Path, required=True)
    args = parser.parse_args()
    build(args.group, args.out, args.prefix, args.audit)
