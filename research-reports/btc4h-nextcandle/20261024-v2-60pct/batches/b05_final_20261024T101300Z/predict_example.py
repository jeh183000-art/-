#!/usr/bin/env python3
"""Reproduce a saved historical forecast from candles closed at a stated time.

This is a research example, not an order interface or a live-data service.
It requires the once-only evaluation to have completed before opening 2026 data.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import pandas as pd
from threadpoolctl import threadpool_limits

import engine_v2 as engine
import features_v2

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--asof', default='2026-07-01T00:00:00Z')
    parser.add_argument('--out', type=Path, default=ROOT / 'results' / 'prediction_smoke.json')
    args = parser.parse_args()
    completion = ROOT / 'results' / 'evaluation' / 'completion.json'
    if not completion.exists() or json.loads(completion.read_text()).get('model_status') != 'OK':
        raise SystemExit('A completed frozen evaluation is required before reading 2026 input data')
    artifact_path = completion.parent / 'selected_historical_model.joblib'
    expected = json.loads(completion.read_text())['sha256']['selected_historical_model.joblib']
    if engine.digest(artifact_path) != expected:
        raise SystemExit('Saved model bytes differ from the completed evaluation')
    artifact = joblib.load(artifact_path)  # Only this study\'s checked local artifact.
    asof_ms = engine.ms(args.asof)
    inputs = {}
    for name, history_path in engine.dataset_paths(ROOT / 'data' / 'development').items():
        future_path = engine.dataset_paths(ROOT / 'data' / 'holdout_2026', True)[name]
        bars = pd.concat([engine.read_csv(history_path), engine.read_csv(future_path)], ignore_index=True)
        inputs[name] = bars.loc[bars.close_time < asof_ms].reset_index(drop=True)
    groups, meta = features_v2.build_features(inputs['btc4h'], inputs['btc15m'], inputs['eth4h'])
    with threadpool_limits(limits=2):
        result = engine.predict_with_artifact(artifact, groups, meta, args.asof)
    ledger = engine.read_csv(completion.parent / 'predictions.csv.gz')
    same = ledger[ledger.prediction_time == engine.ms(result['prediction_time_utc'])]
    if len(same) != 1:
        raise SystemExit('The example must correspond to one archived historical prediction')
    probability = float(same.iloc[0][artifact['predictor'] + '__p_up'])
    error = abs(probability - result['p_up_conditional_non_doji'])
    if error > 1e-10:
        raise SystemExit(f'Historical inference differs from archived forecast: {error}')
    result.update({'status': 'PASS', 'source_rows_are_closed_at_asof': True,
                   'archived_p_up': probability, 'absolute_probability_error': error,
                   'model_sha256': engine.digest(artifact_path)})
    engine.write_json(args.out, result)
    print(json.dumps(engine.native(result), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
