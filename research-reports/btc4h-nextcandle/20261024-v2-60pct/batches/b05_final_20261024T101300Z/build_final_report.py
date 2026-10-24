#!/usr/bin/env python3
"""Build the Korean report after the one frozen evaluation and its audit.

This script never fits an estimator, chooses a new policy, or changes an engine
artifact. The explicit --after-evaluation flag and completion/audit checks must
pass before any evaluation ledger is opened.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
LABELS = {
    'always_up': '항상 양봉',
    'always_down': '항상 음봉',
    'past_majority': '해당 분기 이전의 다수 방향',
    'same_currentcolor': '현재 봉과 같은 방향',
    'opposite_currentcolor': '현재 봉과 반대 방향',
}
GROUPS = {
    'G1': ('기존 4시간봉 특징', 38),
    'G2': ('4시간봉 모양·변동성·체결 흐름 확장', 77),
    'G3': ('G2 + 확정된 15분봉 16개의 내부 흐름', 104),
    'G4': ('G3 + 같은 시각의 ETH 상대 정보', 122),
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def read_csv(path):
    return pd.read_csv(path, float_precision='round_trip')


def pct(value, places=2):
    return '해당 없음' if value is None or pd.isna(value) else f'{value * 100:.{places}f}%'


def pp(value, places=2):
    return '해당 없음' if value is None or pd.isna(value) else f'{value * 100:+.{places}f}%p'


def integer(value):
    return '해당 없음' if value is None or pd.isna(value) else f'{int(value):,}'


def correct(row):
    return int(row['correct_up_count']) + int(row['correct_down_count'])


def table(headers, rows):
    return '\n'.join(['| ' + ' | '.join(headers) + ' |',
                      '| ' + ' | '.join('---' for _ in headers) + ' |'] +
                     ['| ' + ' | '.join(str(x) for x in row) + ' |' for row in rows])


def row_for(frame, predictor, policy, period='ALL'):
    rows = frame[(frame.predictor == predictor) & (frame.policy == policy) &
                 (frame.period.astype(str) == str(period))]
    if len(rows) != 1:
        raise ValueError(f'Expected exactly one metrics row: {predictor}/{policy}/{period}')
    return rows.iloc[0].to_dict()


def comparison_row(stage, period, subject, predictor, policy, scope, metrics, source):
    return {
        'stage': stage, 'period': period, 'subject': subject, 'predictor': predictor,
        'policy': policy, 'scope': scope,
        'selected_count': metrics.get('selected_count', metrics.get('scored_count')),
        'scored_count': metrics['scored_count'], 'correct_count': correct(metrics),
        'accuracy': metrics['accuracy'], 'coverage': metrics.get('coverage'),
        'predicted_up_count': metrics.get('predicted_up_count'),
        'predicted_down_count': metrics.get('predicted_down_count'),
        'active_months': metrics.get('active_months'),
        'max_month_share': metrics.get('max_month_share'), 'source': source,
    }


def build(root, after_evaluation):
    if not after_evaluation:
        raise SystemExit('Use --after-evaluation only after the one frozen evaluation completes')
    result = root / 'results'
    completion_path = result / 'evaluation' / 'completion.json'
    if not completion_path.is_file():
        raise SystemExit('Evaluation is not complete; no evaluation ledger was opened')
    completion = read_json(completion_path)
    if completion.get('status') != 'COMPLETE':
        raise SystemExit('Evaluation completion is required')
    audit_path = result / 'audit_evaluation.json'
    if not audit_path.is_file() or read_json(audit_path).get('status') != 'PASS':
        raise SystemExit('A passing independent evaluation audit is required before reporting')
    settings, freeze = read_json(root / 'settings.json'), read_json(root / 'engine_freeze.json')
    selection = read_json(result / 'selection.json')
    if completion['selection_sha256'] != sha(result / 'selection.json'):
        raise ValueError('Selection bytes differ from the completed frozen evaluation')
    for relative, expected in freeze['code_sha256'].items():
        if sha(root / relative) != expected:
            raise ValueError('Frozen source changed: ' + relative)
    ev = result / 'evaluation'
    # File content is first accessed after all guards above pass.
    summary = read_json(ev / 'evaluation_summary.json')
    if summary['selection_sha256'] != sha(result / 'selection.json'):
        raise ValueError('Evaluation summary is tied to another selection')
    required_payloads = ['evaluation_summary.json', 'predictions.csv.gz', 'results.csv',
                         'monthly.csv', 'quarterly.csv', 'sides.csv', 'uncertainty.json',
                         'matched_v1_control.csv', 'matched_v1_comparison.json',
                         'v1_control/results.csv']
    for relative in required_payloads:
        if sha(ev / relative) != completion['sha256'][relative]:
            raise ValueError('Completed evaluation output changed: ' + relative)
    predictor, policy = selection['predictor'], selection['policy']['id']
    chosen, full = summary['selected_metrics'], summary['full_coverage_metrics']
    rows = read_csv(ev / 'results.csv')
    monthly, quarterly = read_csv(ev / 'monthly.csv'), read_csv(ev / 'quarterly.csv')
    sides = read_csv(ev / 'sides.csv')
    ledger = read_csv(ev / 'predictions.csv.gz')
    p = ledger[predictor + '__p_up'].to_numpy(dtype=float)
    if selection['policy']['kind'] == 'absolute':
        threshold = float(selection['policy']['threshold'])
    else:
        threshold = ledger[predictor + '__' + policy].to_numpy(dtype=float)
    selected = np.isfinite(p) & (np.maximum(p, 1-p) >= threshold)
    scorable = selected & ledger.y.notna().to_numpy()
    if int(scorable.sum()) != chosen['scored_count']:
        raise ValueError('Report mask differs from frozen summary')
    if int((((p >= .5) == ledger.y.to_numpy()) & scorable).sum()) != correct(chosen):
        raise ValueError('Report correct count differs from frozen summary')
    if not np.array_equal(selected, ledger.selected_policy_signal.astype(bool).to_numpy()):
        raise ValueError('Stored signal differs from frozen policy')
    v1 = read_csv(ev / 'v1_control' / 'results.csv')
    v1_full = row_for(v1, 'V1_LOGISTIC38', 'A500')
    v1_55 = row_for(v1, 'V1_LOGISTIC38', 'A550')
    matched_v1 = summary['v1_comparison']
    uncertainty = read_json(ev / 'uncertainty.json')
    ranking = read_csv(result / 'selection_ranking.csv')
    all_dev = read_csv(result / 'all_development_results.csv')
    if len(ranking) != 448 or len(all_dev) != 1344:
        raise ValueError('The complete registered development search is required')
    eligible = ranking[ranking.eligible.astype(bool)]
    if not len(eligible) or eligible.iloc[0].predictor != predictor or eligible.iloc[0].policy != policy:
        raise ValueError('Report candidate differs from the frozen development winner')
    dev_rows, group_rows, comparison = [], [], []
    for group, (description, count) in GROUPS.items():
        rg = ranking[(ranking.group == group) & ranking.eligible.astype(bool)]
        if not len(rg):
            group_rows.append([group, count, '적격 후보 없음', '—', '—', '—', '0 / 112'])
            continue
        winner = rg.iloc[0]
        a = row_for(all_dev, winner.predictor, winner.policy, 2024)
        b = row_for(all_dev, winner.predictor, winner.policy, 2025)
        pooled = row_for(all_dev, winner.predictor, winner.policy)
        group_rows.append([group, count, winner.predictor + ' / ' + winner.policy,
                           pct(a['accuracy']) + ' (' + integer(a['scored_count']) + ')',
                           pct(b['accuracy']) + ' (' + integer(b['scored_count']) + ')',
                           pct(pooled['accuracy']), f'{len(rg)} / 112'])
        for period, row in [('2024', a), ('2025', b), ('ALL', pooled)]:
            comparison.append(comparison_row('development', period, group + ' gated leader',
                winner.predictor, winner.policy, 'group_leader_selected', row,
                f'results/{group}/results.csv'))
    for year in [2024, 2025, 'ALL']:
        row = row_for(all_dev, predictor, policy, year)
        dev_rows.append(['2024~2025 합계' if year == 'ALL' else year, f'{correct(row):,} / {int(row["scored_count"]):,}',
                         pct(row['accuracy']), pct(row['coverage']), integer(row['active_months']),
                         f'{int(row["predicted_up_count"]):,} / {int(row["predicted_down_count"]):,}'])
    comparison += [
        comparison_row('evaluation', '2026-01/2026-09', 'V2 full coverage', predictor, 'A500',
                       'full', full, 'results/evaluation/evaluation_summary.json'),
        comparison_row('evaluation', '2026-01/2026-09', 'V2 frozen policy', predictor, policy,
                       'frozen_policy', chosen, 'results/evaluation/evaluation_summary.json'),
        comparison_row('evaluation', '2026-01/2026-09', 'V1 full coverage', 'V1_LOGISTIC38', 'A500',
                       'full', v1_full, 'results/evaluation/v1_control/results.csv'),
        comparison_row('evaluation', '2026-01/2026-09', 'V1 default 55%', 'V1_LOGISTIC38', 'A550',
                       'v1_default_policy', v1_55, 'results/evaluation/v1_control/results.csv'),
    ]
    control_rows = []
    for name, label in LABELS.items():
        accuracy = chosen['matched_' + name + '_accuracy']
        n = int(chosen['scored_count'])
        truth = ledger.loc[scorable, 'y'].to_numpy(dtype=int)
        pred = ledger.loc[scorable, 'ctrl_' + name].to_numpy(dtype=int)
        wins = int((pred == truth).sum())
        if n and abs(wins/n - accuracy) > 1e-12:
            raise ValueError('Matched-control report count differs: ' + name)
        control_rows.append([label, f'{wins:,} / {n:,}', pct(accuracy), pp(chosen['accuracy'] - accuracy)])
        metrics = dict(chosen, accuracy=accuracy, correct_up_count=int(((pred == 1) & (truth == 1)).sum()),
                       correct_down_count=int(((pred == 0) & (truth == 0)).sum()),
                       predicted_up_count=int((pred == 1).sum()), predicted_down_count=int((pred == 0).sum()))
        comparison.append(comparison_row('evaluation', '2026-01/2026-09', label, name, policy,
                           'same_v2_selected_timestamps', metrics, 'results/evaluation/predictions.csv.gz'))
    n_v1 = int(matched_v1['matched_selected_non_doji_count'])
    a_v1 = matched_v1['v1_accuracy_on_v2_selected_timestamps']
    v2_matched_accuracy = matched_v1['v2_accuracy_on_same_timestamps']
    control_rows.append(['기존 V1의 방향 예측',
                         f'{round(a_v1*n_v1):,} / {n_v1:,}' if a_v1 is not None else '해당 없음',
                         pct(a_v1), pp(v2_matched_accuracy-a_v1) if a_v1 is not None else '해당 없음'])
    control_rows.append(['선택한 V2 모델', f'{correct(chosen):,} / {int(chosen["scored_count"]):,}',
                         pct(chosen['accuracy']), '기준'])
    matched = read_csv(ev / 'matched_v1_control.csv')
    mv_mask = matched.selected.astype(bool) & matched.y.notna() & matched['V1_LOGISTIC38__p_up'].notna()
    mv_pred = matched.loc[mv_mask, 'V1_LOGISTIC38__p_up'].to_numpy() >= .5
    mv_y = matched.loc[mv_mask, 'y'].to_numpy(dtype=int)
    v1_matched_metrics = dict(chosen, scored_count=n_v1, selected_count=n_v1, accuracy=a_v1,
        correct_up_count=int((mv_pred & (mv_y == 1)).sum()),
        correct_down_count=int((~mv_pred & (mv_y == 0)).sum()),
        predicted_up_count=int(mv_pred.sum()), predicted_down_count=int((~mv_pred).sum()))
    comparison.append(comparison_row('evaluation', '2026-01/2026-09', 'V1 on V2-selected timestamps',
        'V1_LOGISTIC38', policy, 'same_v2_selected_timestamps', v1_matched_metrics,
        'results/evaluation/matched_v1_control.csv'))
    month_rows = []
    for month in sorted(monthly.month.unique()):
        sf = monthly[(monthly.month == month) & (monthly.policy == policy)].iloc[0]
        ff = monthly[(monthly.month == month) & (monthly.policy == 'A500')].iloc[0]
        month_rows.append([month, integer(ff.scored_count), pct(ff.accuracy),
                           f'{correct(sf):,} / {int(sf.scored_count):,}', pct(sf.accuracy), pct(sf.coverage),
                           f'{int(sf.predicted_up_count):,} / {int(sf.predicted_down_count):,}'])
    quarter_rows = []
    for row in quarterly[quarterly.policy == policy].sort_values(['year', 'quarter']).to_dict('records'):
        quarter_rows.append([f'{row["year"]} Q{row["quarter"]}', f'{correct(row):,} / {int(row["scored_count"]):,}',
                             pct(row['accuracy']), pct(row['coverage']),
                             f'{int(row["predicted_up_count"]):,} / {int(row["predicted_down_count"]):,}'])
    side_rows = [[('양봉' if row['side'] == 'UP' else '음봉'),
                  f'{int(row["correct_count"]):,} / {int(row["scored_count"]):,}', pct(row['accuracy'])]
                 for row in sides[sides.policy == policy].to_dict('records')]
    threshold_rows = []
    for start, group in ledger.groupby('fold_start_utc', sort=True):
        t = (selection['policy']['threshold'] if selection['policy']['kind'] == 'absolute'
             else float(group[predictor + '__' + policy].iloc[0]))
        if selection['policy']['kind'] != 'absolute' and group[predictor + '__' + policy].nunique() != 1:
            raise ValueError('Policy threshold changed inside an evaluation quarter')
        threshold_rows.append([start[:10], pct(t, 4) if t <= 1 else '전부 관망',
                               integer(group.selected_policy_signal.astype(bool).sum()), integer(len(group))])
    uncertainty_rows = []
    for name, interval in uncertainty.get('paired_accuracy_differences', {}).items():
        uncertainty_rows.append([LABELS[name], pp(interval['point_difference']),
            pp(interval['percentile_95_low']) + ' ~ ' + pp(interval['percentile_95_high'])])
    audits = []
    for phase in ['G1', 'G2', 'G3', 'G4', 'development', 'evaluation']:
        a = read_json(result / f'audit_{phase}.json')
        if a['status'] != 'PASS':
            raise ValueError('A required research audit failed: ' + phase)
        audits.append([phase, integer(a['checks_total']), integer(a['checks_failed']), a['status']])
    data_audit = read_json(root / 'data' / 'development' / 'aggregation_comparison.json')
    feature_spec = read_json(root / 'feature_specification.json')
    model_path = ev / 'selected_historical_model.joblib'
    model_sha = sha(model_path) if model_path.is_file() else '모델 적합 실패로 생성되지 않음'
    if model_path.is_file() and model_sha != completion['sha256']['selected_historical_model.joblib']:
        raise ValueError('Saved selected model differs from the completed evaluation')
    goal = bool(summary['point_60_percent_goal_met'])
    verdict = '사전 지정한 선택적 예측의 60% 점추정 목표를 충족했다' if goal else '사전 지정한 60% 목표를 충족하지 못했다'
    full_goal = full['accuracy'] is not None and full['accuracy'] >= .6
    full_verdict = '전체 봉 예측에서도 이번 평가의 점추정 적중률이 60% 이상이다.' if full_goal else '전체 봉을 빠짐없이 예측하는 60% 모델은 확보하지 못했다.'
    gate_labels = {'all_three_folds_successful': '세 평가 분기 모두 적합 성공',
                   'accuracy_at_least_target': '선별 적중률 60% 이상',
                   'selected_non_doji_count': '선별 평가 200개 이상',
                   'active_months': '월 5회 이상 예측한 달 6개월 이상',
                   'month_concentration': '특정 한 달의 비중 25% 이하'}
    gate_rows = [[gate_labels[name], '충족' if ok else '미충족'] for name, ok in summary['goal_gate_checks'].items()]
    eval_days = 273
    if uncertainty.get('status') == 'OK':
        ci_text = pct(uncertainty['accuracy_percentile_95_low']) + ' ~ ' + pct(uncertainty['accuracy_percentile_95_high'])
    else:
        ci_text = '계산 불가: ' + uncertainty.get('reason', '평가 실패 또는 선택 표본 없음')
    same_time_conclusion = (
        f"같은 {n_v1:,}개 선별 시점에서 기존 V1의 적중률은 **{pct(a_v1)}**, "
        f"현재 봉의 반대 방향을 찍는 단순 기준은 **{pct(chosen['matched_opposite_currentcolor_accuracy'])}**였다. "
        "이번 변경으로 두 기준보다 적중률이 높아졌다고 판정할 수 없다."
        if a_v1 is not None and chosen['accuracy'] <= a_v1 and
        chosen['accuracy'] <= chosen['matched_opposite_currentcolor_accuracy'] else
        "같은 선별 시점의 기존 V1 및 단순 기준과의 비교와 그 차이의 불확실성을 아래에 함께 제시한다.")
    smoke_path = result / 'prediction_smoke.json'
    smoke_text = ''
    if smoke_path.is_file():
        smoke = read_json(smoke_path)
        if smoke.get('status') == 'PASS':
            smoke_text = (f"저장 모델의 역사적 추론 재현도 통과했다. {smoke['prediction_time_utc']}의 예측을 "
                          f"그 시점까지 닫힌 캔들만으로 다시 계산했으며, 원장 확률과의 절대 차이는 "
                          f"{smoke['absolute_probability_error']:.3g}이었다. "
                          "[추론 재현 기록](results/prediction_smoke.json)\n\n")
    recipe_rows = []
    for recipe in selection['member_recipes']:
        recipe_rows.append([recipe['id'], recipe['kind'], '확장 이력' if recipe['train_days'] is None else f'{recipe["train_days"]}일',
                            json.dumps(recipe['params'], ensure_ascii=False, sort_keys=True)])
    input_hash_rows = []
    for scope, mapping in [('개발', freeze['development_data_sha256']), ('평가', freeze['holdout_data_sha256'])]:
        for path, digest in mapping.items():
            input_hash_rows.append([scope, Path(path).name, '`' + digest + '`'])
    calibration = read_json(ev / 'calibration.json')
    fallback_count = sum(x.get('mode') == 'constant_fallback' for x in calibration)
    dev_fits = sum(len(read_csv(result / group / 'split_audit.csv')) for group in GROUPS)
    fit_failures = sum(len(read_json(result / group / 'failures.json')) for group in GROUPS)
    group_description, feature_count = GROUPS[selection['group']]
    policy_text = (f"과거 180일 확률 보정 구간의 확신도 {selection['policy']['quantile']*100:.0f}백분위수를 기준으로 선별한다. "
                   "Q85는 정확도 85%라는 뜻이 아니며, 새 분기에서 신호가 정확히 15% 발생한다는 보장도 없다."
                   if selection['policy']['kind'] == 'calibration_quantile' else
                   f"모델의 확신도가 {selection['policy']['threshold']*100:.1f}% 이상일 때 선별한다. 이 임계값과 실제 적중률은 서로 다른 수치다.")
    report = f'''# BTCUSDT 선물 4시간봉: 60% 목표 모델 검증 결과

## 결과와 판정

**2026년 1월 1일~9월 30일 UTC의 별도 평가에서, 고정한 `{predictor} / {policy}`는 {correct(chosen):,}/{int(chosen['scored_count']):,}개를 맞혀 적중률 {pct(chosen['accuracy'])}를 기록했다. {verdict}.**

전체 {int(full['forecast_count']):,}개 예측 기회 중 {int(chosen['selected_count']):,}개, **{pct(chosen['coverage'])}**를 선별했다. 같은 모델이 모든 봉에서 방향을 예측했을 때의 적중률은 **{pct(full['accuracy'])}**였다. {full_verdict}

{same_time_conclusion}

실제 다음 봉의 색상과 비교해 적중률을 계산했다. 후보와 선별 기준을 개발 기간에서 고정한 뒤 2026년 자료를 한 번 평가했다. 선택적 적중률을 전체 봉의 성능으로 확대 해석하지 않는다. [평가 요약](results/evaluation/evaluation_summary.json), [전체 예측 원장](results/evaluation/predictions.csv.gz)

| 예측 방식 | 적중 / 평가 표본 | 실제 적중률 | 전체 기회 중 신호 비율 |
|---|---|---|---|
| V2 전체 봉 | {correct(full):,} / {int(full['scored_count']):,} | {pct(full['accuracy'])} | {pct(full['coverage'])} |
| V2 고정 선별 기준 {policy} | {correct(chosen):,} / {int(chosen['scored_count']):,} | **{pct(chosen['accuracy'])}** | {pct(chosen['coverage'])} |
| 기존 V1 전체 봉 | {correct(v1_full):,} / {int(v1_full['scored_count']):,} | {pct(v1_full['accuracy'])} | {pct(v1_full['coverage'])} |
| 기존 V1 기본 확신도 55% 기준 | {correct(v1_55):,} / {int(v1_55['scored_count']):,} | {pct(v1_55['accuracy'])} | {pct(v1_55['coverage'])} |

위 네 행은 모두 같은 2026년 평가 기간이다. 다만 각 선별 기준이 고른 시점은 다를 수 있으므로, 모델 간 같은 시점의 방향 예측 비교를 뒤에서 따로 제시한다. [V1 대조군 결과](results/evaluation/v1_control/results.csv)

## 무엇을 예측했는가

현재 4시간봉이 확정되는 시점에 바로 다음 4시간봉을 예측한다. 다음 봉의 종가가 **그 다음 봉의 시가**보다 높으면 양봉, 낮으면 음봉이다. 현재 봉 종가와 미래 종가의 변화율로 정답을 바꾸지 않았다. 보합은 시간축에서 보존하고 이진 학습·채점에서만 제외했다.

현재 봉의 마감 이후 정보는 입력 특징에 들어가지 않는다. 확신도는 `max(양봉 확률, 음봉 확률)`이며, 양봉 확률이 0.5 이상이면 양봉으로 분류한다. 저장 확률은 다음 봉이 보합이 아니라는 조건의 이진 확률이다. 이 연구는 실제 주문이나 매매 수익률을 측정하지 않는다. [설정](settings.json), [특징 정의](feature_specification.json)

## 최종 선택 모델과 선별 방식

선택된 특징 그룹은 **{selection['group']} — {group_description} {feature_count}개**다. 선택된 예측기는 `{predictor}`, 선별 기준은 `{policy}`다.

{table(['구성원', '모델 종류', '기본 학습 이력', '고정 파라미터'], recipe_rows)}

{('선택된 앙상블은 구성원별로 과거 자료에서 보정한 확률을 동일 가중치로 평균한다.' if selection['ensemble'] else '사전에 정한 파라미터를 유지한 단일 모델이다.')}

{policy_text} 임계값은 분기 시작 전에 과거 자료로 정하고 그 분기 내내 유지했다. 평가 분기의 결과나 확신도 순위를 보고 신호 수를 조정하지 않았다.

{table(['평가 분기 시작 UTC', '실제 확신도 임계값', '신호 수', '예측 기회'], threshold_rows)}

선별 신호는 평가 기간 하루 평균 **{chosen['selected_count']/eval_days:.3f}개**였다. 고정된 임계값은 앞으로도 같은 빈도와 적중률을 보장하지 않는다. [선택 파일](results/selection.json), [확률 보정 기록](results/evaluation/calibration.json)

## 개발 과정: 448개 조합을 모두 기록

개발 입력은 2020~2025년이다. 이미 앞선 연구에서 결과를 본 2024~2025년을 이번에는 후보 선택용 개발 기간으로 명확히 사용했다. 2026년 1~9월 자료는 V2의 별도 평가용으로 분리했으며, 사용자의 모든 과거 연구를 통틀어 처음 보는 기간이라고 주장하지 않는다. 기존 보호 Final OOS 파일은 수정하지 않았다.

특징 그룹 4개 × 기본 모델 설정 10개 = **40개 모델 설정**, 고정 앙상블 4개 × 4개 그룹 = **16개 앙상블 설정**을 비교했다. 56개 예측기마다 8개 선별 기준을 적용했으므로 개발에서 비교한 조합은 **448개**다. 개발 분기별 기본 모델 적합은 실제 **{dev_fits}회**, 적합 실패 기록은 **{fit_failures}개**다. 앙상블은 기본 모델의 보정 확률을 평균하므로 추가 기본 모델 학습과 구분한다.

선별 기준은 확신도 50·52.5·55·57.5·60·62.5%와 과거 보정 구간의 확신도 70·85백분위수다. 전체 후보, 표본 부족·시기 집중·실패·신호 0개인 조합도 결과 CSV에 남겼다.

개발에서 적격 후보가 되려면 **2024년과 2025년 각각** 200개 이상을 평가하고, 월 5개 이상 예측한 달이 8개월 이상이어야 하며, 특정 한 달이 연간 신호의 25%를 넘지 않아야 한다. 이 조건은 사용자 요구를 대신 인용한 것이 아니라 연구자가 사전에 정한 최소 검증 기준이다. 적격 후보 중 두 해의 적중률 중 낮은 값을 우선하고, 결합 적중률·작은 연도 표본 수·전체 log loss·이름 순으로 동률을 처리했다.

{table(['그룹', '특징 수', '그룹 내 최고 적격 후보', '2024 적중률 (평가 수)', '2025 적중률 (평가 수)', '결합 적중률', '적격 / 전체'], group_rows)}

그룹마다 여러 조합을 살펴본 뒤 최고값을 뽑았으므로 이 표는 탐색 성적이다. 입력 특징을 더 추가한 것 자체가 실제 미래 성능 개선을 뜻하지는 않는다. [전체 448개 순위](results/selection_ranking.csv), [전체 1,344행 기간별 결과](results/all_development_results.csv)

최종 선택 후보의 개발 성적은 다음과 같다.

{table(['개발 기간', '적중 / 평가 표본', '적중률', '신호 비율', '활동 월 수', '양봉 / 음봉 예측'], dev_rows)}

코드는 {freeze['frozen_at_utc']}에 실제 V2 학습 전에 고정했다. 후보 하나와 정책을 {selection['frozen_at_utc']}에 고정한 후 2026년 평가를 시작했다. 개발 최고점이 60%에 못 미치더라도 적격 최고 후보 하나는 평가한다는 실행 규칙도 사전에 정했다. 최종 평가를 본 뒤 후보를 교체하거나 임계값을 추가로 고르지 않았다. [사전 등록](preregistration.json), [코드 동결](engine_freeze.json)

## 평가 방식과 정보 시점

2024~2025년 개발은 8개 분기, 2026년 평가는 3개 분기로 나눴다. 각 분기 시작 시점에 당시 알 수 있는 자료로만 기본 모델과 확률 보정을 다시 학습했다. 이전 평가 분기가 나중 분기의 과거 학습 자료가 될 수 있는 순차 평가다. 2026년 내내 2025년 말 모델을 그대로 유지한 실험과는 다르다.

기본 모델 학습과 분리된 **180일**을 확률 보정에 사용했다. 기본 학습의 정답 확정 시점은 보정 시작보다 엄격하게 앞서고, 보정 정답의 확정 시점은 평가 분기 시작보다 엄격하게 앞서도록 했다. 결측값 대체의 중앙값과 표준화 값은 기본 학습 구간에만 맞췄다. 부스팅의 무작위 조기 종료를 사용하지 않았다.

보정 기울기가 0 이하이면 신호 순서를 뒤집지 않고 과거 보정 구간의 평활 양봉 비율을 상수로 사용했다. 상수 확신도에서 백분위 선별 정책은 전부 관망한다. 선택된 구성원의 이번 평가에서 상수 대체 기록은 {fallback_count}개였다. 어느 평가 분기의 모델 적합이라도 실패하면 일부 분기의 성공만으로 전체 성공으로 표시하지 않는다. [분기 경계 기록](results/evaluation/split_audit.csv), [보정 원장](results/evaluation/calibration_predictions.csv.gz)

기존 V1 대조군은 2022년부터 데이터를 다시 잘라 최초 96봉 준비 구간을 보존했다. 기존 38개 특징, 로지스틱 C=0.1, 90일 보정, 기존 보정의 음수 기울기 허용 동작을 유지했다. V2를 유리하게 보이도록 대조군의 설정을 새로 고르지 않았다.

## 같은 선별 시점의 단순 기준과 V1 비교

다음 표는 **V2가 실제로 신호를 낸 바로 그 시점**에 각 대조군이 방향을 예측했을 때의 결과다. 추가 선별이나 후보 교체에 사용하지 않았다.

{table(['방향 예측 기준', '적중 / 평가 표본', '적중률', 'V2와의 적중률 차이'], control_rows)}

모델이 양봉으로 치우쳐 있을 때 항상 양봉 기준과의 비교가 특히 필요하다. 선별 시점 자체가 어느 방향에 유리했다면 높은 적중률의 일부는 시점 선택에서 나온다. 방향 분류와 시점 선택의 기여를 분리해서 보아야 한다. V1 비교 표본 수는 {n_v1:,}개다. [같은 시점 V1 대조 원장](results/evaluation/matched_v1_control.csv), [대조 요약](results/evaluation/matched_v1_comparison.json)

## 월별·분기별·방향별 평가

활동 월은 월 5개 이상 선별 평가한 달로 정의했다. 이번 평가는 활동 월 **{int(chosen['active_months'])}개월**, 한 달 최대 비중 **{pct(chosen['max_month_share'])}**였다. 보합과 표본 0개가 있으면 적중률을 임의로 0%로 채우지 않는다.

{table(['월 UTC', '전체 평가 수', '전체 적중률', '선별 적중 / 평가 수', '선별 적중률', '신호 비율', '양봉 / 음봉 예측'], month_rows)}

{table(['분기', '선별 적중 / 평가 수', '선별 적중률', '신호 비율', '양봉 / 음봉 예측'], quarter_rows)}

{table(['예측 방향', '적중 / 평가 수', '그 방향의 적중률'], side_rows)}

전체 기간 평균만으로 모든 달·방향에서 같은 성능이 났다고 해석하지 않는다. 방향별 표본 크기가 다르면 비슷한 적중률에도 불확실성이 다르다. [월별 결과](results/evaluation/monthly.csv), [분기별 결과](results/evaluation/quarterly.csv), [방향별 결과](results/evaluation/sides.csv)

## 60% 목표의 판정과 불확실성

{table(['사전 평가 조건', '판정'], gate_rows)}

목표 판정은 위 조건을 모두 충족하는 **점추정치** 기준이다. 선별 적중률의 UTC 7일 블록 부트스트랩 95% 백분위 구간은 **{ci_text}**였다. 2026년 1월 1일 UTC를 시작점으로 고정한 7일 구간 전체를 함께 재표집했고, 신호가 없는 구간도 포함해 사전에 정한 seed로 2,000회 반복했다.

같은 재표집에서 단순 기준과의 적중률 차이는 다음과 같다.

{table(['동일 시점의 대조군', 'V2 적중률 차이', '차이의 95% 블록 부트스트랩 구간'], uncertainty_rows)}

이 구간은 보조 진단이다. 시장 국면 변화, 블록을 넘는 의존성, 이전 연구를 포함한 모든 탐색 과정을 완전히 반영하지 않는다. 60% 점추정 목표를 넘더라도 앞으로의 실제 적중률 60%를 보장하지 않는다. 대조군 대비 차이의 구간이 0을 포함하면 해당 대조군에 대한 안정적인 우위가 입증됐다고 표현하지 않는다. V1에 대해서는 같은 시점의 점추정 비교를 제시했으며 위 단순 기준의 구간을 V1 구간으로 대신 사용하지 않았다. [불확실성 기록](results/evaluation/uncertainty.json)

## 자료 출처와 품질

Binance USD-M 무기한 선물의 공식 월별 공개 캔들을 사용했다. 개발 자료는 BTC 4시간봉·15분봉과 ETH 4시간봉의 2020~2025년, 별도 평가는 같은 세 입력의 2026년 1~9월이다. 추가 수집한 147개 월별 ZIP은 공식 체크섬을 확인했고, 앞선 연구에서 검증한 BTC 2022~2025년 원본을 재사용했다. [개발 출처](data/development/download_manifest.json), [평가 출처](data/holdout_2026/download_manifest.json), [공식 데이터 설명](https://github.com/binance/binance-public-data)

BTC 개발 4시간봉은 13,152개, 15분봉은 210,432개이며 ETH 개발 4시간봉은 13,152개다. 평가 구간은 각 4시간봉 1,638개, BTC 15분봉 26,208개다. 구조 검사에서 누락·중복·잘못된 OHLC를 사후 보간하거나 임의 삭제하지 않았다. 필요한 연속 과거 이력이 부족한 입력은 모델 대상에서 제외하도록 설계했다.

공식 4시간봉을 정답과 가격의 기준으로 삼았다. 개발 구간의 15분봉 16개 합산과 비교했을 때 **{data_audit['affected_window_count']}개 4시간 구간**의 일부 가격·거래량 필드가 달랐지만, 양봉·음봉 정답의 차이는 **{data_audit['target_color_mismatch_count']}개**였다. 불일치한 원본을 결과에 맞춰 교체하지 않았다. 이 진단은 개발 기간에 관한 것이며 평가 기간의 모든 필드가 일치한다고 주장하지 않는다. [구간 불일치](data/development/aggregation_discrepancies.csv), [비교 요약](data/development/aggregation_comparison.json)

## 검증과 재현

학습 전 의미 있는 합성 검사 **{freeze['tests_passed']}개**가 통과했다. 이후 별도 감사 코드가 엔진의 점수 함수를 가져다 쓰지 않고 정답 시점·마스크·지표·엄격한 분할·과거 보정 백분위수·448개 조합의 선택 순위를 재계산했다.

{table(['감사 범위', '검사 수', '실패 수', '상태'], audits)}

개별 배치 감사와 전체 개발 감사에는 중복 확인이 포함된다. 위 검사 수를 서로 다른 시장 실험의 수로 합산하지 않는다. 감사 통과는 기록된 원장과 코드·규칙의 일치를 확인하는 것이며 미래 성능의 증명이 아니다. [개발 감사](results/audit_development.md), [평가 감사](results/audit_evaluation.md)

핵심 파일의 SHA256:

- 엔진: `{sha(root / 'engine_v2.py')}`
- 특징 코드: `{sha(root / 'features_v2.py')}`
- 설정: `{sha(root / 'settings.json')}`
- 선택 파일: `{sha(result / 'selection.json')}`
- 동결 기록: `{sha(root / 'engine_freeze.json')}`
- 저장 모델: `{model_sha}`

{table(['구분', '정규화 입력 파일', 'SHA256'], input_hash_rows)}

재현은 별도의 깨끗한 복사본에서 다음 순서로 수행한다. 이미 완료한 결과·선택·평가 시작 기록을 덮어쓰지 않는다.

```bash
pip install -r requirements.txt
python reproduce_inputs.py --scope development
python -m unittest -v test_features_v2.py test_engine_v2.py
python engine_v2.py --phase development --group G1
python audit_v2.py --phase development --group G1
python engine_v2.py --phase development --group G2
python audit_v2.py --phase development --group G2
python engine_v2.py --phase development --group G3
python audit_v2.py --phase development --group G3
python engine_v2.py --phase development --group G4
python audit_v2.py --phase development --group G4
python engine_v2.py --phase select
python audit_v2.py --phase development
python reproduce_inputs.py --scope holdout
python engine_v2.py --phase evaluation
python audit_v2.py --phase evaluation --allow-holdout
python build_final_report.py --after-evaluation
```

동결된 입력 파일과 코드의 해시가 맞아야 실행되며, 각 배치의 단독 감사는 `python audit_v2.py --phase development --group G1`처럼 실행할 수 있다. 데이터 수집은 공개 원본에만 접근한다. 저장 모델은 역사적 2026년 3분기 평가 모델이며 현재 시세에 연결된 서비스가 아니다. 원장과 같은 시점의 추론 예제는 `predict_example.py`로 검증한다. [재현 설명](README_KO.md), [비교 수치 CSV](results/final_comparison.csv)

{smoke_text}## 사용 범위

모든 결과는 다음 캔들 색상의 분류 성능이다. 실제 주문·차입·거래소 계정 변경·매매 백테스트는 하지 않았고 수익률·PF·MDD를 계산하지 않았다. 앞으로 매매 전략을 검증한다면 기존 왕복 수수료 0.12% 가정, 실제 펀딩, 체결 지연과 슬리피지가 별도로 필요하다. 적중률이 높아도 틀린 거래의 손실 크기와 비용 때문에 수익성이 달라질 수 있다.

선택된 규칙을 평가 결과에 맞춰 다시 바꾸지 않았다. 추가 개선에서는 이번 2026년 결과를 이미 본 개발 정보로 취급하고 이후의 새 평가 자료에서 검증해야 한다.
'''
    pd.DataFrame(comparison).to_csv(result / 'final_comparison.csv', index=False,
                                   float_format='%.17g', lineterminator='\n')
    (root / 'REPORT_KO.md').write_text(report, encoding='utf-8')
    receipt = {'status': 'REPORT_BUILT_FROM_COMPLETED_AUDITED_EVALUATION',
               'generator_sha256': sha(Path(__file__)), 'report_sha256': sha(root / 'REPORT_KO.md'),
               'comparison_sha256': sha(result / 'final_comparison.csv'),
               'selection_sha256': sha(result / 'selection.json'),
               'evaluation_completion_sha256': sha(completion_path),
               'predictor': predictor, 'policy': policy, 'point_goal_met': goal,
               'comparison_rows': len(comparison), 'no_model_fitted': True,
               'no_policy_changed': True}
    (result / 'report_generation.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(receipt, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--after-evaluation', action='store_true')
    args = parser.parse_args()
    build(args.root.resolve(), args.after_evaluation)


if __name__ == '__main__':
    main()
