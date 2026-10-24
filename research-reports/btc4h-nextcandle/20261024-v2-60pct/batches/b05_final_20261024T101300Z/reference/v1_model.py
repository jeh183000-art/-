#!/usr/bin/env python3
"""BTCUSDT next-4-hour candle-colour research; no orders or PnL simulation.

Experiment:
  python model.py --data data/BTCUSDT_4h_2022-01_2025-12.csv.gz --out outputs
Prediction from a saved historical research model:
  python model.py --predict-model outputs/evaluation/research_model.joblib \
      --data latest_closed_bars.csv --asof 2026-10-24T00:00:00Z --out prediction

The target is next CLOSE > next OPEN, conditional on a non-doji target. All
timestamps are UTC. An idealized bar-boundary prediction timestamp is used;
this does not assert that a live order can obtain that boundary's open price.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (accuracy_score, balanced_accuracy_score,
                             brier_score_loss, log_loss, roc_auc_score)
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

SEED = 20261024
BAR_MS = 14_400_000
WARMUP = 96
THRESHOLDS = (0.50, 0.55, 0.60)
MODELS = ("logistic", "hist_gradient_boosting")
BASELINES = ("historical_bullish_rate", "coinflip_0.5", "same_color_as_current",
             "opposite_color_to_current")
REQUIRED = ("open_time", "open", "high", "low", "close", "volume",
            "close_time", "quote_volume", "trades", "taker_buy_volume")


def json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        return float(value) if np.isfinite(value) else None
    if isinstance(value, np.bool_):
        return bool(value)
    return value


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(json_safe(value), ensure_ascii=False,
                               indent=2, allow_nan=False) + "\n")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def milliseconds(value: str | pd.Timestamp) -> int:
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    else:
        ts = ts.tz_convert("UTC")
    return int(ts.value // 1_000_000)


def iso(value: float | int) -> str | None:
    if pd.isna(value):
        return None
    return pd.Timestamp(int(value), unit="ms", tz="UTC").isoformat()


def validate_bars(frame: pd.DataFrame) -> pd.DataFrame:
    """Validate the original time axis; retain gaps and doji candles."""
    missing = set(REQUIRED) - set(frame.columns)
    if missing:
        raise ValueError(f"Missing required kline columns: {sorted(missing)}")
    bars = frame.copy().reset_index(drop=True)
    for column in REQUIRED:
        bars[column] = pd.to_numeric(bars[column], errors="raise")
    if bars.empty or not np.isfinite(bars[list(REQUIRED)].to_numpy()).all():
        raise ValueError("Empty input or non-finite kline value")
    for column in ("open_time", "close_time"):
        if not np.equal(bars[column], np.floor(bars[column])).all():
            raise ValueError("Timestamps must be integer milliseconds")
        bars[column] = bars[column].astype("int64")
    if not bars.open_time.is_monotonic_increasing or bars.open_time.duplicated().any():
        raise ValueError("Klines must be in strict ascending time order with no duplicates")
    if (bars.open_time % BAR_MS != 0).any():
        raise ValueError("Kline opens must align to UTC 4-hour boundaries")
    if (bars.close_time != bars.open_time + BAR_MS - 1).any():
        raise ValueError("Unexpected 4-hour close timestamp")
    if (bars[["open", "high", "low", "close"]] <= 0).any().any():
        raise ValueError("OHLC prices must be positive")
    if ((bars.high < bars[["open", "close", "low"]].max(axis=1)) |
            (bars.low > bars[["open", "close", "high"]].min(axis=1))).any():
        raise ValueError("Invalid OHLC bounds")
    if (bars[["volume", "quote_volume", "trades", "taker_buy_volume"]] < 0).any().any():
        raise ValueError("Volumes and trade counts cannot be negative")
    if (bars.taker_buy_volume > bars.volume + 1e-7).any():
        raise ValueError("Taker buy volume exceeds total volume")
    return bars


def read_bars(path: str | Path) -> pd.DataFrame:
    return validate_bars(pd.read_csv(path))


def build_features(bars: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    """38 fixed bar-count features; 96-bar lookback spans 16 days at 4h.

    Eligible rows need current plus 96 previous candles: 97 contiguous bars.
    """
    close, opening, high, low = (bars[c] for c in ("close", "open", "high", "low"))
    ret = close.pct_change(fill_method=None)
    body = (close - opening) / opening
    span = high - low
    features: dict[str, pd.Series | np.ndarray] = {}
    for lookback in (1, 2, 3, 4, 8, 16, 32, 96):
        features[f"return_{lookback}"] = close.pct_change(lookback, fill_method=None)
    features.update({
        "signed_body_pct": body,
        "range_pct": span / opening,
        "upper_wick_pct": (high - pd.concat([opening, close], axis=1).max(axis=1)) / opening,
        "lower_wick_pct": (pd.concat([opening, close], axis=1).min(axis=1) - low) / opening,
        "close_location": ((close - low) / span.replace(0, np.nan)).fillna(0.5),
    })
    for lag in (1, 2, 3, 4):
        features[f"body_lag_{lag}"] = body.shift(lag)
    for window in (4, 16, 96):
        features[f"return_std_{window}"] = ret.rolling(window).std(ddof=0)
    for window in (4, 16, 48, 96):
        features[f"close_to_sma_{window}"] = close / close.rolling(window).mean() - 1
    for window in (4, 16):
        features[f"up_fraction_{window}"] = (close > opening).astype(float).rolling(window).mean()
    for window in (4, 16, 96):
        features[f"volume_ratio_{window}"] = bars.volume / bars.volume.rolling(window).mean()
    for column in ("quote_volume", "trades"):
        features[f"{column}_ratio_16"] = bars[column] / bars[column].rolling(16).mean()
    for window in (1, 4, 16):
        features[f"taker_buy_fraction_{window}"] = (
            bars.taker_buy_volume.rolling(window).sum() / bars.volume.rolling(window).sum()
        )
    prediction_datetime = pd.to_datetime(bars.close_time + 1, unit="ms", utc=True)
    hour = prediction_datetime.dt.hour + prediction_datetime.dt.minute / 60
    weekday = prediction_datetime.dt.dayofweek
    features["utc_hour_sin"] = np.sin(2 * np.pi * hour / 24)
    features["utc_hour_cos"] = np.cos(2 * np.pi * hour / 24)
    features["utc_weekday_sin"] = np.sin(2 * np.pi * weekday / 7)
    features["utc_weekday_cos"] = np.cos(2 * np.pi * weekday / 7)
    X = pd.DataFrame(features, index=bars.index).replace([np.inf, -np.inf], np.nan)
    assert X.shape[1] == 38
    segments = bars.open_time.diff().ne(BAR_MS).cumsum()
    within_segment = bars.groupby(segments, sort=False).cumcount()
    eligible = (within_segment >= WARMUP) & X.notna().all(axis=1)
    return X, eligible


def build_dataset(bars: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    X, eligible = build_features(bars)
    next_open = bars.open.shift(-1)
    next_close = bars.close.shift(-1)
    next_open_time = bars.open_time.shift(-1)
    contiguous = next_open_time.eq(bars.open_time + BAR_MS)
    target_color = np.sign(next_close - next_open).where(contiguous)
    y = ((target_color + 1) / 2).where(target_color.ne(0))
    meta = pd.DataFrame({
        "current_open_time": bars.open_time,
        "prediction_time": bars.close_time + 1,
        "target_open_time": bars.open_time + BAR_MS,
        "target_close_time": bars.open_time + 2 * BAR_MS - 1,
        "label_end_time": bars.open_time + 2 * BAR_MS,
        "current_color": np.sign(bars.close - bars.open),
        "target_color": target_color,
        "target_available": contiguous,
        "y": y,
        "feature_eligible": eligible,
        "target_open": next_open.where(contiguous),
        "target_close": next_close.where(contiguous),
    })
    return X, meta


def split_masks(meta: pd.DataFrame, test_start: int, test_end: int):
    calibration_start = test_start - 90 * 24 * 60 * 60 * 1000
    labeled = meta.feature_eligible & meta.target_available & meta.y.notna()
    fit = labeled & (meta.label_end_time < calibration_start)
    calibration = labeled & (meta.prediction_time >= calibration_start) & (meta.label_end_time < test_start)
    test = (meta.feature_eligible & (meta.prediction_time >= test_start) &
            (meta.prediction_time < test_end) & meta.target_available)
    prior = labeled & (meta.label_end_time < test_start)
    return fit, calibration, test, prior, calibration_start


def create_model(name: str):
    if name == "logistic":
        return make_pipeline(StandardScaler(), LogisticRegression(
            C=0.1, max_iter=500, random_state=SEED))
    if name == "hist_gradient_boosting":
        return HistGradientBoostingClassifier(
            max_iter=100, max_leaf_nodes=7, learning_rate=0.05,
            l2_regularization=10, min_samples_leaf=100,
            early_stopping=False, random_state=SEED)
    raise ValueError(f"Unknown preregistered model: {name}")


def raw_logit(model, X: pd.DataFrame) -> np.ndarray:
    # Both registered models expose decision_function as raw binary log-odds.
    return np.asarray(model.decision_function(X), dtype=float).reshape(-1, 1)


def fit_fold(X, meta, name: str, start: int, end: int) -> tuple[dict, pd.DataFrame, dict]:
    fit, calibration, test, prior, calibration_start = split_masks(meta, start, end)
    if fit.sum() < 2000 or calibration.sum() < 500 or test.sum() == 0:
        raise ValueError("Insufficient chronological fit/calibration/test samples")
    assert meta.loc[fit, "label_end_time"].max() < calibration_start
    assert meta.loc[calibration, "label_end_time"].max() < start
    assert not (fit & calibration).any()
    model = create_model(name)
    model.fit(X.loc[fit], meta.loc[fit, "y"].astype(int))
    # A fixed weakly regularized sigmoid mapping, trained on disjoint later data.
    calibrator = LogisticRegression(C=1_000_000.0, max_iter=500, random_state=SEED)
    calibrator.fit(raw_logit(model, X.loc[calibration]), meta.loc[calibration, "y"].astype(int))
    test_meta = meta.loc[test].copy()
    test_meta["p_up"] = calibrator.predict_proba(raw_logit(model, X.loc[test]))[:, 1]
    test_meta["raw_p_up"] = model.predict_proba(X.loc[test])[:, 1]
    test_meta["model"] = name
    test_meta["fold_start_utc"] = iso(start)
    test_meta["fold_end_utc"] = iso(end)
    bullish_rate = float(meta.loc[prior, "y"].mean())
    test_meta["historical_bullish_rate"] = bullish_rate
    artifact = {
        "model": model, "calibrator": calibrator, "feature_columns": list(X.columns),
        "model_name": name, "study_type": "historical_classification_research",
        "fit_label_cutoff_exclusive_utc": iso(calibration_start),
        "calibration_label_cutoff_exclusive_utc": iso(start),
        "probability_definition": "P(next close > next open | next candle is not doji)",
        "historical_bullish_rate": bullish_rate, "bar_ms": BAR_MS,
    }
    audit = {
        "model": name, "test_start_utc": iso(start), "test_end_utc": iso(end),
        "calibration_start_utc": iso(calibration_start),
        "fit_samples": int(fit.sum()), "calibration_samples": int(calibration.sum()),
        "test_forecasts": int(test.sum()), "test_doji": int(test_meta.target_color.eq(0).sum()),
        "fit_first_prediction_utc": iso(meta.loc[fit, "prediction_time"].min()),
        "fit_last_label_end_utc": iso(meta.loc[fit, "label_end_time"].max()),
        "calibration_first_prediction_utc": iso(meta.loc[calibration, "prediction_time"].min()),
        "calibration_last_label_end_utc": iso(meta.loc[calibration, "label_end_time"].max()),
        "test_first_prediction_utc": iso(test_meta.prediction_time.min()),
        "fit_calibration_disjoint": True, "strict_label_cutoffs_passed": True,
        "prior_bullish_rate": bullish_rate,
        "calibration_slope": float(calibrator.coef_[0, 0]),
        "calibration_intercept": float(calibrator.intercept_[0]),
    }
    return artifact, test_meta, audit


def baseline_predictions(template: pd.DataFrame) -> list[pd.DataFrame]:
    records = []
    prior = template.historical_bullish_rate.to_numpy()
    same = np.where(template.current_color == 0, prior >= 0.5, template.current_color > 0).astype(float)
    opposite = np.where(template.current_color == 0, prior >= 0.5, template.current_color < 0).astype(float)
    for name, probability in zip(BASELINES, (prior, np.full(len(template), 0.5), same, opposite)):
        frame = template.copy()
        frame["model"] = name
        frame["p_up"] = probability
        frame["raw_p_up"] = probability
        records.append(frame)
    return records


def score(frame: pd.DataFrame, threshold: float = 0.5) -> dict:
    confidence = np.maximum(frame.p_up.to_numpy(), 1 - frame.p_up.to_numpy())
    selected = confidence >= threshold
    scorable = selected & frame.y.notna().to_numpy()
    truth = frame.loc[scorable, "y"].to_numpy(dtype=int)
    probabilities = frame.loc[scorable, "p_up"].to_numpy(dtype=float)
    predicted = probabilities >= 0.5
    result = {
        "threshold": threshold, "forecast_count": int(len(frame)),
        "non_doji_count": int(frame.y.notna().sum()),
        "doji_count": int(frame.target_color.eq(0).sum()),
        "selected_count": int(selected.sum()), "scored_count": int(scorable.sum()),
        "coverage": float(selected.mean()) if len(frame) else np.nan,
        "scored_coverage": float(scorable.sum() / frame.y.notna().sum()) if frame.y.notna().any() else np.nan,
        "predicted_up_count": int(predicted.sum()),
        "predicted_down_count": int((~predicted).sum()),
    }
    if not len(truth):
        return dict(result, accuracy=np.nan, balanced_accuracy=np.nan, bullish_precision=np.nan,
                    bearish_precision=np.nan, log_loss=np.nan, brier=np.nan, roc_auc=np.nan)
    clipped = np.clip(probabilities, 1e-6, 1 - 1e-6)
    result.update({
        "accuracy": accuracy_score(truth, predicted),
        "balanced_accuracy": balanced_accuracy_score(truth, predicted) if len(np.unique(truth)) == 2 else np.nan,
        "bullish_precision": float(truth[predicted].mean()) if predicted.any() else np.nan,
        "bearish_precision": float((1 - truth[~predicted]).mean()) if (~predicted).any() else np.nan,
        "log_loss": log_loss(truth, clipped, labels=[0, 1]),
        "brier": brier_score_loss(truth, probabilities),
        "roc_auc": roc_auc_score(truth, probabilities) if len(np.unique(truth)) == 2 else np.nan,
    })
    return result


def report_tables(predictions: pd.DataFrame, out: Path) -> pd.DataFrame:
    summaries, thresholds, monthly, bins = [], [], [], []
    for name, frame in predictions.groupby("model", sort=False):
        summaries.append({"model": name, **score(frame)})
        for threshold in THRESHOLDS:
            thresholds.append({"model": name, **score(frame, threshold)})
        month_labels = pd.to_datetime(frame.prediction_time, unit="ms", utc=True).dt.strftime("%Y-%m")
        for month, subset in frame.groupby(month_labels, sort=True):
            monthly.append({"model": name, "month": month, **score(subset)})
        valid = frame[frame.y.notna()].copy()
        valid["probability_bin"] = pd.cut(valid.p_up, np.linspace(0, 1, 11), include_lowest=True)
        for bucket, subset in valid.groupby("probability_bin", observed=False):
            bins.append({"model": name, "bin": str(bucket), "count": len(subset),
                         "mean_p_up": subset.p_up.mean(), "actual_up_fraction": subset.y.mean()})
    summaries_df = pd.DataFrame(summaries)
    summaries_df.to_csv(out / "results.csv", index=False)
    pd.DataFrame(thresholds).to_csv(out / "thresholds.csv", index=False)
    pd.DataFrame(monthly).to_csv(out / "monthly_metrics.csv", index=False)
    pd.DataFrame(bins).to_csv(out / "calibration_bins.csv", index=False)
    write_json(out / "metric_notes.json", {
        "probabilities": "Conditional on a non-doji next candle; dojis remain in forecast/coverage counts",
        "tie_rule": "p_up == 0.5 maps to UP",
        "coinflip_0.5": "Constant 0.5 probability baseline, not sampled random directions; its thresholded accuracy equals always-UP accuracy",
        "hard_rule_baselines": "Same/opposite rules encode deterministic labels as p=0 or p=1; these are not calibrated confidences and are not model-selection candidates",
        "log_loss_clipping": "Probabilities clipped to [0.000001, 0.999999] only for log-loss evaluation",
        "calibrator": "LogisticRegression on raw log-odds, C=1000000, max_iter=500, random_state=20261024",
        "returns_and_percent_features": "Fractions: 0.01 denotes 1%; standardization fits on base-model training only",
        "no_trading_metrics": "Classification study only; no PnL, fees, funding or execution simulation",
    })
    return summaries_df


def save_predictions(predictions: pd.DataFrame, out: Path) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    # One timestamp per row, with every model/baseline forecast in named columns.
    # Deliberately omit raw prices and volumes from the public forecast ledger.
    static_columns = ["prediction_time", "current_open_time", "target_open_time",
                      "label_end_time", "current_color", "target_color", "y",
                      "fold_start_utc", "fold_end_utc"]
    ordered = predictions[static_columns].drop_duplicates("prediction_time").set_index("prediction_time")
    for name, frame in predictions.groupby("model", sort=False):
        if frame.prediction_time.duplicated().any():
            raise ValueError(f"Duplicate forecast for model {name}")
        forecast = frame.set_index("prediction_time")
        ordered[f"{name}__p_up"] = forecast.p_up
        ordered[f"{name}__direction"] = pd.Series(
            np.where(forecast.p_up >= 0.5, "UP", "DOWN"), index=forecast.index)
        if name in MODELS:
            ordered[f"{name}__raw_p_up"] = forecast.raw_p_up
    ordered = ordered.sort_index().reset_index()
    ordered["prediction_utc"] = pd.to_datetime(ordered.prediction_time, unit="ms", utc=True).dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    ordered["label_end_utc"] = pd.to_datetime(ordered.label_end_time, unit="ms", utc=True).dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    full_path = out / "predictions.csv.gz"
    ordered.to_csv(full_path, index=False, float_format="%.12g", compression={"method": "gzip", "mtime": 0})
    shards = out / "predictions_monthly"
    shards.mkdir(exist_ok=True)
    months = pd.to_datetime(ordered.prediction_time, unit="ms", utc=True).dt.strftime("%Y-%m")
    for month, subset in ordered.groupby(months, sort=True):
        subset.to_csv(shards / f"predictions_{month}.csv", index=False, float_format="%.12g")
    return full_path


def run_phase(X, meta, year: int, names: tuple[str, ...], out: Path):
    out.mkdir(parents=True, exist_ok=True)
    predictions, audits, last_artifact = [], [], None
    for month in (1, 4, 7, 10):
        start_dt = pd.Timestamp(year=year, month=month, day=1, tz="UTC")
        end_dt = start_dt + pd.DateOffset(months=3)
        start, end = milliseconds(start_dt), milliseconds(end_dt)
        template = None
        for name in names:
            artifact, forecast, audit = fit_fold(X, meta, name, start, end)
            predictions.append(forecast)
            audits.append(audit)
            last_artifact = artifact
            if template is None:
                template = forecast
            fold_score = score(forecast)
            print(json.dumps(json_safe({"event": "fold_complete", "year": year,
                  "quarter": (month - 1) // 3 + 1, "model": name,
                  "accuracy": fold_score["accuracy"], "log_loss": fold_score["log_loss"],
                  "scored_count": fold_score["scored_count"]})), flush=True)
        predictions.extend(baseline_predictions(template))
    combined = pd.concat(predictions, ignore_index=True)
    forecast_path = save_predictions(combined, out)
    summary = report_tables(combined, out)
    pd.DataFrame(audits).to_csv(out / "split_audit.csv", index=False)
    write_json(out / "split_audit.json", audits)
    if len(names) == 1:
        joblib.dump(last_artifact, out / "research_model.joblib", compress=3)
    return summary, forecast_path


def predict_latest(artifact: dict, bars: pd.DataFrame, asof: str, threshold: float = 0.55) -> dict:
    if artifact.get("bar_ms") != BAR_MS:
        raise ValueError("Saved model candle interval does not match 4-hour input")
    asof_ms = milliseconds(asof)
    available_at = milliseconds(artifact["calibration_label_cutoff_exclusive_utc"])
    if asof_ms < available_at:
        raise ValueError("Requested --asof precedes saved model availability; backward leakage prohibited")
    bars = bars[bars.close_time + 1 <= asof_ms].copy().reset_index(drop=True)
    if bars.empty:
        raise ValueError("No closed candle exists at or before --asof")
    prediction_time = int(bars.close_time.iloc[-1] + 1)
    if prediction_time < available_at:
        raise ValueError("Latest closed bar precedes saved model availability; backward leakage prohibited")
    X, eligible = build_features(bars)
    if not eligible.iloc[-1]:
        raise ValueError("Latest closed candle lacks 97 contiguous valid history bars")
    columns = artifact["feature_columns"]
    if list(X.columns) != columns:
        raise ValueError("Feature schema differs from saved model")
    probability = float(artifact["calibrator"].predict_proba(
        raw_logit(artifact["model"], X.iloc[[-1]]))[0, 1])
    target_end = prediction_time + BAR_MS
    confidence = max(probability, 1 - probability)
    return {
        "study_type": "historical_research_model_not_live_trading",
        "asof_utc": iso(asof_ms), "information_boundary_utc": iso(prediction_time),
        "prediction_created_asof_utc": iso(asof_ms),
        "target_open_utc": iso(prediction_time), "target_end_exclusive_utc": iso(target_end),
        "latest_closed_candle_open_utc": iso(int(bars.open_time.iloc[-1])),
        "stale_input": asof_ms >= target_end,
        "model_name": artifact["model_name"],
        "model_fit_cutoff_exclusive_utc": artifact["fit_label_cutoff_exclusive_utc"],
        "model_calibration_cutoff_exclusive_utc": artifact["calibration_label_cutoff_exclusive_utc"],
        "probability_definition": artifact["probability_definition"],
        "p_up_conditional_non_doji": probability,
        "p_down_conditional_non_doji": 1 - probability,
        "direction": "UP" if probability >= 0.5 else "DOWN",
        "confidence": confidence, "confidence_threshold": threshold,
        "abstain": confidence < threshold or asof_ms >= target_end,
        "execution_assumption": "No order or claimed fill price; only a direction forecast",
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--phase", choices=("development", "evaluation", "all"), default="all")
    parser.add_argument("--protocol", type=Path, default=Path(__file__).with_name("settings.json"))
    parser.add_argument("--predict-model", type=Path)
    parser.add_argument("--asof", help="Explicit UTC timestamp required for prediction mode")
    parser.add_argument("--threshold", type=float, default=0.55)
    args = parser.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    bars = read_bars(args.data)
    with threadpool_limits(limits=2):
        if args.predict_model:
            if not args.asof:
                parser.error("--predict-model requires --asof")
            if not 0.5 <= args.threshold <= 1:
                parser.error("--threshold must be between 0.5 and 1")
            # Only load a model artifact produced by this study or another trusted source.
            forecast = predict_latest(joblib.load(args.predict_model), bars, args.asof, args.threshold)
            write_json(args.out / "prediction.json", forecast)
            print(json.dumps(forecast, indent=2))
            return 0
        X, meta = build_dataset(bars)
        protocol_digest = sha256(args.protocol) if args.protocol.exists() else None
        data_digest = sha256(args.data)
        code_digest = sha256(Path(__file__))
        config = {"seed": SEED, "bar_ms": BAR_MS, "features": list(X.columns), "models": list(MODELS),
                  "protocol_sha256": protocol_digest, "data_sha256": data_digest,
                  "model_code_sha256": code_digest}
        selection_path = args.out / "selection.json"
        if args.phase in ("development", "all"):
            if selection_path.exists():
                raise FileExistsError("Frozen selection already exists; use --phase evaluation or a new output directory")
            write_json(args.out / "environment.json", {
                "python": sys.version, "platform": platform.platform(),
                "numpy": np.__version__, "pandas": pd.__version__,
                "scikit_learn": sklearn.__version__, "joblib": joblib.__version__,
                "threadpool_limit": 2, **config,
            })
            write_json(args.out / "feature_columns.json", list(X.columns))
            development, forecast_path = run_phase(X, meta, 2024, MODELS, args.out / "development")
            candidates = development[development.model.isin(MODELS)].sort_values(["log_loss", "model"])
            candidates.to_csv(args.out / "candidates.csv", index=False)
            selected_name = str(candidates.iloc[0].model)
            selection = {**config, "selected_model": selected_name,
                         "selection_criterion": "minimum concatenated 2024 calibrated log_loss",
                         "development_prediction_sha256": sha256(forecast_path),
                         "development_result_sha256": sha256(args.out / "development" / "results.csv"),
                         "development_candidate_metrics": candidates.to_dict(orient="records"),
                         "frozen_before_evaluation": True,
                         "no_profitable_trading_or_predictive_edge_claim": True}
            write_json(selection_path, selection)
            print(json.dumps({"event": "selection_frozen", "selected_model": selected_name}), flush=True)
        if args.phase in ("evaluation", "all"):
            if not selection_path.exists():
                raise FileNotFoundError("Development must create selection.json before evaluation")
            selection = json.loads(selection_path.read_text())
            for key, expected in config.items():
                if selection.get(key) != expected:
                    raise ValueError(f"Frozen selection mismatch: {key}")
            dev_path = args.out / "development" / "predictions.csv.gz"
            if sha256(dev_path) != selection["development_prediction_sha256"]:
                raise ValueError("Development predictions changed after selection freeze")
            winner = selection["selected_model"]
            if winner not in MODELS:
                raise ValueError("Selected model is not preregistered")
            if (args.out / "evaluation" / "results.csv").exists():
                raise FileExistsError("Evaluation already completed; preserve original output")
            run_phase(X, meta, 2025, (winner,), args.out / "evaluation")
            print(json.dumps({"event": "evaluation_complete", "selected_model": winner}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
