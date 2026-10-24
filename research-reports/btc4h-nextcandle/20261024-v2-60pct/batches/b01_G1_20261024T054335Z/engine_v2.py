"""Frozen BTCUSDT 4h V2 classification experiment. No trading or PnL.

Development: python engine_v2.py --phase development --group G1
Selection:   python engine_v2.py --phase select
Evaluation:  python engine_v2.py --phase evaluation

Evaluation verifies the frozen selection BEFORE opening any 2026 data file.
All probabilities/thresholds use round-trip-safe 17-digit CSV serialization.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import platform
import sys
import warnings
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import ExtraTreesClassifier, HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.exceptions import ConvergenceWarning
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import balanced_accuracy_score, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC
from threadpoolctl import threadpool_limits

import features_v2

ROOT = Path(__file__).resolve().parent
BAR_MS = 14_400_000
DAY_MS = 86_400_000
EPS = 1e-6
FLOAT_FORMAT = "%.17g"
CONTROL_NAMES = ("always_up", "always_down", "past_majority", "same_currentcolor", "opposite_currentcolor")
STATIC = ("current_open_time", "prediction_time", "target_open_time", "label_end_time", "current_color", "target_color", "y")


def native(x):
    if isinstance(x, dict):
        return {str(k): native(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [native(v) for v in x]
    if isinstance(x, np.ndarray):
        return native(x.tolist())
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (np.bool_,)):
        return bool(x)
    if isinstance(x, (float, np.floating)):
        return float(x) if np.isfinite(x) else None
    if isinstance(x, Path):
        return str(x)
    return x


def write_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(native(obj), ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def ms(value):
    t = pd.Timestamp(value)
    t = t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")
    return int(t.value // 1_000_000)


def iso(value):
    if value is None or pd.isna(value):
        return None
    return pd.Timestamp(int(value), unit="ms", tz="UTC").isoformat()


def read_csv(path):
    return pd.read_csv(path, float_precision="round_trip")


def save_csv(frame, path, compressed=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    compression = {"method": "gzip", "mtime": 0} if compressed else None
    frame.to_csv(path, index=False, float_format=FLOAT_FORMAT, compression=compression, lineterminator="\n")


def write_exclusive_json(path, obj):
    """An interrupted run remains recorded; never silently rerun a holdout."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(native(obj), ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def settings_and_hash(path):
    path = Path(path)
    s = json.loads(path.read_text())
    prereg = path.with_name("preregistration.json")
    if prereg.exists() and json.loads(prereg.read_text())["settings_sha256"] != digest(path):
        raise ValueError("Settings differ from the preregistration")
    if s["bar_ms"] != BAR_MS:
        raise ValueError("This engine is only for the frozen four-hour experiment")
    return s, digest(path)


def dataset_paths(folder, evaluation=False):
    suffix = "2026-01_2026-09" if evaluation else "2020-01_2025-12"
    return {
        "btc4h": Path(folder) / f"BTCUSDT_4h_{suffix}.csv.gz",
        "btc15m": Path(folder) / f"BTCUSDT_15m_{suffix}.csv.gz",
        "eth4h": Path(folder) / f"ETHUSDT_4h_{suffix}.csv.gz",
    }


def load_inputs(folder, evaluation=False):
    return {k: read_csv(v) for k, v in dataset_paths(folder, evaluation).items()}


def make_config(settings_path, data_dir):
    return {
        "settings_sha256": digest(settings_path),
        "engine_sha256": digest(__file__),
        "features_sha256": digest(features_v2.__file__),
        "v1_reference_sha256": digest(Path(settings_path).parent / "reference" / "v1_model.py"),
        "feature_specification_sha256": digest(Path(settings_path).parent / "feature_specification.json"),
        "engine_freeze_sha256": digest(Path(settings_path).parent / "engine_freeze.json"),
        "development_data_sha256": {k: digest(v) for k, v in dataset_paths(data_dir).items()},
        "bar_ms": BAR_MS,
        "float_format": FLOAT_FORMAT,
    }


def verify_code_freeze(settings_path, data_dir, holdout_dir=None):
    """Check frozen source/input bytes; holdout hashes are checked only on evaluation."""
    root = Path(settings_path).resolve().parent
    freeze = json.loads((root / "engine_freeze.json").read_text())
    if freeze.get("settings_sha256", digest(settings_path)) != digest(settings_path):
        raise ValueError("Engine freeze settings mismatch")
    for key in ("code_sha256", "development_data_sha256"):
        if not freeze.get(key):
            raise ValueError("Missing freeze map: " + key)
        for name, expected in freeze[key].items():
            if digest(root / name) != expected:
                raise ValueError("Frozen bytes changed: " + name)
    mandatory = {"engine_v2.py", "features_v2.py", "reference/v1_model.py", "feature_specification.json", "settings.json"}
    if not mandatory.issubset(freeze["code_sha256"]):
        raise ValueError("Code freeze must include engine, features, specification, settings and V1 reference")
    for path in dataset_paths(data_dir).values():
        relative = str(path.resolve().relative_to(root))
        if freeze["development_data_sha256"].get(relative) != digest(path):
            raise ValueError("Development input differs from frozen source")
    if holdout_dir is not None:
        if not freeze.get("holdout_data_sha256"):
            raise ValueError("Missing frozen holdout data hashes")
        for path in dataset_paths(holdout_dir, evaluation=True).values():
            relative = str(path.resolve().relative_to(root))
            if freeze["holdout_data_sha256"].get(relative) != digest(path):
                raise ValueError("Holdout input differs from frozen source")
    return freeze


def verify_feature_schema(groups, settings_path):
    spec = json.loads((Path(settings_path).parent / "feature_specification.json").read_text())
    if spec["features_code_sha256"] != digest(features_v2.__file__):
        raise ValueError("Features differ from the frozen feature specification")
    for group, X in groups.items():
        if list(X.columns) != spec["groups"][group]["columns"]:
            raise ValueError("Ordered feature schema changed for " + group)


def quarter_windows(year, final_month=10):
    for month in (1, 4, 7, 10):
        if month > final_month:
            break
        start = pd.Timestamp(year=year, month=month, day=1, tz="UTC")
        end = start + pd.DateOffset(months=3)
        yield ms(start), ms(end)


def split_masks(meta, group, start, end, calibration_days, train_days=None):
    cal_start = start - int(calibration_days) * DAY_MS
    eligible = meta[f"eligible_{group}"].astype(bool) & meta.target_available.astype(bool)
    labeled = eligible & meta.y.notna()
    fit = labeled & (meta.label_end_time < cal_start)
    train_start = None if train_days is None else cal_start - int(train_days) * DAY_MS
    if train_start is not None:
        fit &= meta.prediction_time >= train_start
    calibration = labeled & (meta.prediction_time >= cal_start) & (meta.label_end_time < start)
    test = eligible & (meta.prediction_time >= start) & (meta.prediction_time < end)
    prior = labeled & (meta.label_end_time < start)
    return fit, calibration, test, prior, cal_start, train_start


def create_model(recipe, seed):
    kind, params = recipe["kind"], recipe["params"]
    imputer = SimpleImputer(strategy="median", keep_empty_features=True)
    if kind == "logistic":
        estimator = LogisticRegression(**params, max_iter=1000, random_state=seed)
        return make_pipeline(imputer, StandardScaler(), estimator)
    if kind == "svc":
        estimator = SVC(**params, probability=False, cache_size=256, random_state=seed)
        return make_pipeline(imputer, StandardScaler(), estimator)
    if kind == "hgb":
        estimator = HistGradientBoostingClassifier(**params, early_stopping=False, random_state=seed)
    elif kind == "extra_trees":
        estimator = ExtraTreesClassifier(**params, n_jobs=2, random_state=seed)
    elif kind == "random_forest":
        estimator = RandomForestClassifier(**params, n_jobs=2, random_state=seed)
    else:
        raise ValueError(f"Unregistered model kind: {kind}")
    return make_pipeline(imputer, estimator)


def raw_scores(model, X):
    if hasattr(model, "decision_function"):
        score = np.asarray(model.decision_function(X), dtype=float)
    else:
        p = np.clip(model.predict_proba(X)[:, 1], EPS, 1 - EPS)
        score = np.log(p) - np.log1p(-p)
    score = score.reshape(-1, 1)
    if not np.isfinite(score).all():
        raise ValueError("Non-finite raw model score")
    return score


def fit_calibrator(scores, y, seed, C=1.0, allow_negative=False, max_iter=1000):
    scores = np.asarray(scores, dtype=float).reshape(-1, 1)
    y = np.asarray(y, dtype=int)
    smooth = float((y.sum() + 1) / (len(y) + 2))
    if len(np.unique(y)) < 2:
        return {"mode": "constant_fallback", "reason": "single_class_calibration", "model": None,
                "constant_probability": smooth, "slope": 0.0, "fitted_slope": None,
                "intercept": float(np.log(smooth / (1 - smooth)))}
    calibrator = LogisticRegression(C=C, max_iter=max_iter, random_state=seed)
    calibrator.fit(scores, y)
    slope = float(calibrator.coef_[0, 0])
    intercept = float(calibrator.intercept_[0])
    if not allow_negative and slope <= 0:
        return {"mode": "constant_fallback", "reason": "nonpositive_slope", "model": None,
                "constant_probability": smooth, "slope": 0.0, "fitted_slope": slope,
                "fitted_intercept": intercept, "intercept": float(np.log(smooth / (1 - smooth)))}
    return {"mode": "sigmoid", "model": calibrator, "constant_probability": None,
            "slope": slope, "fitted_slope": slope, "intercept": intercept}


def calibrate(calibrator, scores):
    if calibrator["mode"] == "constant_fallback":
        return np.full(len(scores), calibrator["constant_probability"], dtype=float)
    return calibrator["model"].predict_proba(np.asarray(scores).reshape(-1, 1))[:, 1]


def quantile_thresholds(calibration_probabilities, policies):
    p = np.asarray(calibration_probabilities, dtype=float)
    if not len(p) or not np.isfinite(p).all():
        raise ValueError("Invalid past calibration probabilities")
    confidence = np.maximum(p, 1 - p)
    constant = np.ptp(confidence) < 1e-8
    return {pol["id"]: (2.0 if constant else float(np.quantile(confidence, pol["quantile"], method="linear")))
            for pol in policies if pol["kind"] == "calibration_quantile"}


def scaffold(meta, group, start, end, settings):
    fit, cal, test, prior, cal_start, _ = split_masks(meta, group, start, end, settings["calibration_days"])
    if not test.any() or not prior.any():
        raise ValueError("No test rows or known historical baseline labels")
    rate = float(meta.loc[prior, "y"].mean())
    f = meta.loc[test, list(STATIC)].copy()
    f["fold_start_utc"], f["fold_end_utc"] = iso(start), iso(end)
    times = pd.to_datetime(f.prediction_time, unit="ms", utc=True)
    f["prediction_utc"] = times.dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    f["year"], f["month"], f["quarter"] = times.dt.year, times.dt.strftime("%Y-%m"), times.dt.quarter
    f["past_bullish_rate"] = rate
    majority = int(rate >= 0.5)
    f["ctrl_always_up"], f["ctrl_always_down"], f["ctrl_past_majority"] = 1, 0, majority
    f["ctrl_same_currentcolor"] = np.where(f.current_color == 0, majority, f.current_color > 0).astype(int)
    f["ctrl_opposite_currentcolor"] = np.where(f.current_color == 0, majority, f.current_color < 0).astype(int)
    c = meta.loc[cal, list(STATIC)].copy()
    c["fold_start_utc"], c["fold_end_utc"] = iso(start), iso(end)
    return f, c


def fit_recipe(X, meta, group, recipe, start, end, settings):
    fit, cal, test, _, cal_start, train_start = split_masks(
        meta, group, start, end, settings["calibration_days"], recipe["train_days"])
    if fit.sum() < settings["minimum_fit_samples"] or cal.sum() < settings["minimum_calibration_samples"]:
        raise ValueError(f"Insufficient fit/calibration samples: {fit.sum()}/{cal.sum()}")
    if not test.any():
        raise ValueError("No forecast rows")
    if meta.loc[fit, "label_end_time"].max() >= cal_start or meta.loc[cal, "label_end_time"].max() >= start:
        raise ValueError("Label availability boundary failure")
    if (fit & cal).any() or (fit & test).any() or (cal & test).any():
        raise ValueError("Overlapping time splits")
    model = create_model(recipe, settings["seed"])
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        model.fit(X.loc[fit], meta.loc[fit, "y"].astype(int))
        cal_scores = raw_scores(model, X.loc[cal])
        calibrator = fit_calibrator(cal_scores, meta.loc[cal, "y"], settings["seed"],
                                    C=settings["calibrator"]["C"],
                                    max_iter=settings["calibrator"]["max_iter"])
        if any(issubclass(w.category, ConvergenceWarning) for w in caught):
            raise RuntimeError("ConvergenceWarning: " + "; ".join(str(w.message) for w in caught))
    pcal = calibrate(calibrator, cal_scores)
    ptest = calibrate(calibrator, raw_scores(model, X.loc[test]))
    if not np.isfinite(ptest).all() or ((ptest < 0) | (ptest > 1)).any():
        raise ValueError("Invalid calibrated forecast probability")
    thresholds = quantile_thresholds(pcal, settings["policies"])
    split = {"group": group, "recipe": recipe["id"], "fold_start_utc": iso(start), "fold_end_utc": iso(end),
             "calibration_start_utc": iso(cal_start), "train_start_utc": iso(train_start),
             "fit_count": int(fit.sum()), "calibration_count": int(cal.sum()), "test_count": int(test.sum()),
             "fit_last_label_end_utc": iso(meta.loc[fit, "label_end_time"].max()),
             "calibration_last_label_end_utc": iso(meta.loc[cal, "label_end_time"].max()),
             "strict_cutoffs_passed": True, "status": "OK",
             "warnings": "; ".join(str(w.message) for w in caught)}
    cal_record = {k: v for k, v in calibrator.items() if k != "model"}
    cal_record.update({"group": group, "recipe": recipe["id"], "fold_start_utc": iso(start),
                      "calibration_count": int(cal.sum()), "calibration_raw_score_std": float(np.std(cal_scores)),
                      "calibration_positive_rate": float(meta.loc[cal, "y"].mean()),
                      "calibration_confidence_min": float(np.maximum(pcal, 1-pcal).min()),
                      "calibration_confidence_max": float(np.maximum(pcal, 1-pcal).max()), **thresholds})
    artifact = {"model": model, "calibrator": calibrator, "feature_columns": list(X.columns),
                "group": group, "recipe": recipe, "bar_ms": BAR_MS, "thresholds": thresholds,
                "fit_cutoff_utc": iso(cal_start), "calibration_cutoff_utc": iso(start)}
    return artifact, ptest, pcal, cal_scores.ravel(), split, cal_record


def policy_mask(frame, predictor, policy):
    p = frame[predictor + "__p_up"].to_numpy(dtype=float)
    threshold = (float(policy["threshold"]) if policy["kind"] == "absolute"
                 else frame[predictor + "__" + policy["id"]].to_numpy(dtype=float))
    return np.isfinite(p) & (np.maximum(p, 1-p) >= threshold)


def score(frame, predictor, policy, status="OK", active_month_min=5):
    p = frame[predictor + "__p_up"].to_numpy(dtype=float)
    y = frame.y.to_numpy(dtype=float)
    finite = np.isfinite(p)
    valid = np.isfinite(y)
    selected = policy_mask(frame, predictor, policy)
    scored = selected & valid
    truth, q = y[scored].astype(int), p[scored]
    pred = q >= 0.5
    monthly = frame.loc[scored].groupby("month").size()
    full = finite & valid
    out = {
        "forecast_count": len(frame), "available_forecast_count": int(finite.sum()),
        "non_doji_count": int(valid.sum()), "selected_count": int(selected.sum()), "scored_count": int(scored.sum()),
        "coverage": float(selected.mean()) if len(frame) else np.nan,
        "scored_coverage": float(scored.sum()/valid.sum()) if valid.any() else np.nan,
        "predicted_up_count": int(pred.sum()), "predicted_down_count": int((~pred).sum()),
        "correct_up_count": int((truth[pred] == 1).sum()), "correct_down_count": int((truth[~pred] == 0).sum()),
        "active_months": int((monthly >= active_month_min).sum()),
        "max_month_share": float(monthly.max()/scored.sum()) if scored.any() else 0.0,
    }
    metrics = ("accuracy", "balanced_accuracy", "bullish_precision", "bearish_precision",
               "log_loss", "brier", "roc_auc", "full_log_loss")
    out.update({k: np.nan for k in metrics})
    out.update({"matched_" + c + "_accuracy": np.nan for c in CONTROL_NAMES})
    if status != "OK":
        return out
    if full.any():
        qfull = np.clip(p[full], EPS, 1-EPS)
        out["full_log_loss"] = float(-(y[full]*np.log(qfull)+(1-y[full])*np.log1p(-qfull)).mean())
    if not len(truth):
        return out
    clipped = np.clip(q, EPS, 1-EPS)
    out.update({
        "accuracy": float((pred == truth).mean()),
        "balanced_accuracy": float(balanced_accuracy_score(truth, pred)) if len(np.unique(truth)) == 2 else np.nan,
        "bullish_precision": float(truth[pred].mean()) if pred.any() else np.nan,
        "bearish_precision": float((1-truth[~pred]).mean()) if (~pred).any() else np.nan,
        "log_loss": float(-(truth*np.log(clipped)+(1-truth)*np.log1p(-clipped)).mean()),
        "brier": float(((q-truth)**2).mean()),
        "roc_auc": float(roc_auc_score(truth, q)) if len(np.unique(truth)) == 2 else np.nan,
    })
    for c in CONTROL_NAMES:
        out["matched_" + c + "_accuracy"] = float((frame.loc[scored, "ctrl_" + c].to_numpy() == truth).mean())
    return out


def report_tables(frame, group, predictor_ids, policies, statuses, out, years, active_month_min=5):
    records, monthly, quarterly, sides = [], [], [], []
    for predictor in predictor_ids:
        status = statuses[predictor]
        for policy in policies:
            base = {"group": group, "predictor": predictor, "policy": policy["id"], "status": status}
            for period in [str(y) for y in years] + ["ALL"]:
                subset = frame if period == "ALL" else frame[frame.year.eq(int(period))]
                records.append({**base, "period": period, **score(subset, predictor, policy, status, active_month_min)})
            for month, subset in frame.groupby("month", sort=True):
                monthly.append({**base, "month": month, **score(subset, predictor, policy, status, active_month_min)})
            for (year, quarter), subset in frame.groupby(["year", "quarter"], sort=True):
                quarterly.append({**base, "year": year, "quarter": quarter,
                                  **score(subset, predictor, policy, status, active_month_min)})
            p = frame[predictor + "__p_up"].to_numpy()
            selected = policy_mask(frame, predictor, policy) & frame.y.notna().to_numpy()
            for name, side in (("UP", p >= 0.5), ("DOWN", p < 0.5)):
                mask = selected & side
                n = int(mask.sum())
                correct = int(((p[mask] >= 0.5) == frame.loc[mask, "y"].to_numpy()).sum())
                sides.append({**base, "side": name, "scored_count": n, "correct_count": correct,
                              "accuracy": correct/n if n and status == "OK" else np.nan})
    result = pd.DataFrame(records)
    save_csv(result, Path(out) / "results.csv")
    save_csv(pd.DataFrame(monthly), Path(out) / "monthly.csv")
    save_csv(pd.DataFrame(quarterly), Path(out) / "quarterly.csv")
    save_csv(pd.DataFrame(sides), Path(out) / "sides.csv")
    return result


def save_forecasts(frame, folder):
    save_csv(frame, Path(folder) / "predictions.csv.gz", compressed=True)
    for month, subset in frame.groupby("month", sort=True):
        save_csv(subset, Path(folder) / "predictions_monthly" / f"predictions_{month}.csv")


def save_calibration(frame, folder):
    save_csv(frame, Path(folder) / "calibration_predictions.csv.gz", compressed=True)
    for fold, subset in frame.groupby("fold_start_utc", sort=True):
        label = pd.Timestamp(fold).strftime("%Y-%m")
        save_csv(subset, Path(folder) / "calibration_quarterly" / f"calibration_{label}.csv")


def add_predictor(frame, calibration_frame, predictor, ptest, pcal, thresholds, raw=None):
    frame[predictor + "__p_up"] = ptest
    calibration_frame[predictor + "__p_up"] = pcal
    if raw is not None:
        calibration_frame[predictor + "__raw_score"] = raw
    for name, value in thresholds.items():
        frame[predictor + "__" + name] = value


def develop_group(group, settings, settings_path, data_dir, out):
    folder = Path(out) / group
    folder.mkdir(parents=True, exist_ok=True)
    if (folder / "run_started.json").exists():
        raise FileExistsError(f"Preserve prior/partial group run: {folder}")
    verify_code_freeze(settings_path, data_dir)
    config = make_config(settings_path, data_dir)
    write_exclusive_json(folder / "run_started.json", {"started_at_utc": now(), "group": group, "config": config})
    inputs = load_inputs(data_dir)
    groups, meta = features_v2.build_features(inputs["btc4h"], inputs["btc15m"], inputs["eth4h"])
    verify_feature_schema(groups, settings_path)
    X = groups[group]
    write_json(folder / "feature_columns.json", list(X.columns))
    write_json(folder / "environment.json", {
        "python": sys.version, "platform": platform.platform(), "numpy": np.__version__,
        "pandas": pd.__version__, "scikit_learn": sklearn.__version__, "joblib": joblib.__version__,
        "threadpool_limit": 2, "settings": settings, "config": config,
    })
    all_frames, all_calibration, splits, calibration_records, failures = [], [], [], [], []
    failed = set()
    for year in settings["development_evaluation_years"]:
        for start, end in quarter_windows(year):
            frame, cframe = scaffold(meta, group, start, end, settings)
            fold_failed = set()
            for recipe in settings["models"]:
                predictor = group + "_" + recipe["id"]
                try:
                    artifact, ptest, pcal, raw, split, calrec = fit_recipe(X, meta, group, recipe, start, end, settings)
                    add_predictor(frame, cframe, predictor, ptest, pcal, artifact["thresholds"], raw)
                    splits.append(split)
                    calrec["predictor"] = predictor
                    calibration_records.append(calrec)
                    event = {"event": "recipe_fold_complete", "group": group, "recipe": recipe["id"],
                             "quarter_start": iso(start), "status": "OK", "calibration_mode": calrec["mode"]}
                except Exception as exc:
                    failed.add(predictor)
                    fold_failed.add(recipe["id"])
                    add_predictor(frame, cframe, predictor, np.full(len(frame), np.nan), np.full(len(cframe), np.nan),
                                  {"Q70": 2.0, "Q85": 2.0}, np.full(len(cframe), np.nan))
                    error = {"group": group, "predictor": predictor, "recipe": recipe["id"], "fold_start_utc": iso(start),
                             "status": "FAILED", "error": type(exc).__name__ + ": " + str(exc)}
                    failures.append(error)
                    splits.append({**error, "fold_end_utc": iso(end), "strict_cutoffs_passed": False})
                    event = {"event": "recipe_fold_failed", **error}
                print(json.dumps(native(event)), flush=True)
            for ensemble in settings["ensembles"]:
                predictor = group + "_" + ensemble["id"]
                members = [group + "_" + r for r in ensemble["members"]]
                if any(r in fold_failed for r in ensemble["members"]):
                    failed.add(predictor)
                    ptest, pcal = np.full(len(frame), np.nan), np.full(len(cframe), np.nan)
                    thresholds = {"Q70": 2.0, "Q85": 2.0}
                    mode = "FAILED_MEMBER"
                else:
                    ptest = frame[[m + "__p_up" for m in members]].to_numpy().mean(axis=1)
                    pcal = cframe[[m + "__p_up" for m in members]].to_numpy().mean(axis=1)
                    thresholds = quantile_thresholds(pcal, settings["policies"])
                    mode = "equal_weight_mean"
                add_predictor(frame, cframe, predictor, ptest, pcal, thresholds)
                calibration_records.append({"group": group, "predictor": predictor, "recipe": ensemble["id"],
                                            "fold_start_utc": iso(start), "mode": mode, "members": members,
                                            "calibration_count": len(cframe), **thresholds})
            all_frames.append(frame)
            all_calibration.append(cframe)
    combined = pd.concat(all_frames, ignore_index=True).sort_values("prediction_time").reset_index(drop=True)
    if combined.prediction_time.duplicated().any():
        raise ValueError("Duplicate forecast timestamp")
    predictors = [group + "_" + r["id"] for r in settings["models"] + settings["ensembles"]]
    statuses = {p: ("FAILED" if p in failed else "OK") for p in predictors}
    for ensemble in settings["ensembles"]:
        if any(group + "_" + member in failed for member in ensemble["members"]):
            statuses[group + "_" + ensemble["id"]] = "FAILED"
    save_forecasts(combined, folder)
    save_calibration(pd.concat(all_calibration, ignore_index=True), folder)
    report_tables(combined, group, predictors, settings["policies"], statuses, folder,
                  settings["development_evaluation_years"],
                  settings["development_sample_gate"]["active_month_minimum_predictions"])
    save_csv(pd.DataFrame(splits), folder / "split_audit.csv")
    write_json(folder / "calibration.json", calibration_records)
    write_json(folder / "failures.json", failures)
    payload = ["predictions.csv.gz", "calibration_predictions.csv.gz", "results.csv", "monthly.csv", "quarterly.csv", "sides.csv",
               "split_audit.csv", "calibration.json", "failures.json", "feature_columns.json"]
    payload += [str(p.relative_to(folder)) for p in sorted((folder / "predictions_monthly").glob("*.csv"))]
    payload += [str(p.relative_to(folder)) for p in sorted((folder / "calibration_quarterly").glob("*.csv"))]
    completion = {"status": "COMPLETE", "finished_at_utc": now(), "group": group,
                  "config": config, "expected_folds_per_recipe": 8, "predictor_status": statuses,
                  "recipe_fold_failures": len(failures), "forecast_rows": len(combined),
                  "sha256": {name: digest(folder / name) for name in payload}}
    write_json(folder / "completion.json", completion)
    print(json.dumps({"event": "group_complete", "group": group, "predictors": len(predictors),
                      "predictor_policy_combinations": len(predictors)*len(settings["policies"]),
                      "failed_predictors": sum(v != "OK" for v in statuses.values())}), flush=True)


def rank_candidates(results, settings):
    records = []
    gate = settings["development_sample_gate"]
    years = [str(y) for y in settings["development_evaluation_years"]]
    for (group, predictor, policy), f in results.groupby(["group", "predictor", "policy"], sort=True):
        f = f.copy()
        f["period"] = f.period.astype(str)
        rows = {period: f[f.period.eq(period)] for period in years + ["ALL"]}
        reasons = []
        if any(len(rows[p]) != 1 for p in rows):
            reasons.append("MISSING_OR_DUPLICATE_PERIOD")
        if not f.status.eq("OK").all():
            reasons.append("FAILED_RECIPE_OR_ENSEMBLE")
        metrics = {"minimum_year_accuracy": np.nan, "combined_accuracy": np.nan,
                   "minimum_year_n": 0, "full_coverage_combined_log_loss": np.nan}
        if not any(len(rows[p]) != 1 for p in rows):
            annual = [rows[y].iloc[0] for y in years]
            pooled = rows["ALL"].iloc[0]
            if any(r.scored_count < gate["minimum_selected_non_doji_each_year"] for r in annual):
                reasons.append("YEAR_SAMPLE_COUNT")
            if any(r.active_months < gate["minimum_active_months_each_year"] for r in annual):
                reasons.append("YEAR_ACTIVE_MONTHS")
            if any(r.max_month_share > gate["maximum_single_month_share"] for r in annual):
                reasons.append("MONTH_CONCENTRATION")
            if any(not np.isfinite(r.accuracy) for r in annual) or not np.isfinite(pooled.full_log_loss):
                reasons.append("NONFINITE_SCORE")
            metrics = {"minimum_year_accuracy": min(float(r.accuracy) for r in annual),
                       "combined_accuracy": float(pooled.accuracy),
                       "minimum_year_n": int(min(r.scored_count for r in annual)),
                       "full_coverage_combined_log_loss": float(pooled.full_log_loss)}
        records.append({"group": group, "predictor": predictor, "policy": policy, "eligible": not reasons,
                        "rejection_reasons": "|".join(reasons), **metrics})
    ranking = pd.DataFrame(records)
    if len(ranking):
        ranking = ranking.sort_values(
            ["eligible", "minimum_year_accuracy", "combined_accuracy", "minimum_year_n",
             "full_coverage_combined_log_loss", "predictor", "policy"],
            ascending=[False, False, False, False, True, True, True], na_position="last").reset_index(drop=True)
        ranking.insert(0, "rank", np.arange(1, len(ranking)+1))
    return ranking


def verify_development_artifacts(out, config, settings):
    snapshots, tables = {}, []
    for group in settings["batch_groups"]:
        folder = Path(out) / group
        completion_path = folder / "completion.json"
        completion = json.loads(completion_path.read_text())
        if completion["status"] != "COMPLETE" or completion["config"] != config:
            raise ValueError("Incomplete or changed development group: " + group)
        for name, expected in completion["sha256"].items():
            if digest(folder / name) != expected:
                raise ValueError("Development artifact changed: " + group + "/" + name)
        split = read_csv(folder / "split_audit.csv")
        for recipe in settings["models"]:
            folds = split[split.recipe.eq(recipe["id"])]
            if len(folds) != 8 or folds.fold_start_utc.nunique() != 8:
                raise ValueError("Every base recipe must record all eight development folds")
            expected_status = "OK" if folds.status.eq("OK").all() else "FAILED"
            if completion["predictor_status"][group + "_" + recipe["id"]] != expected_status:
                raise ValueError("Partial successful folds cannot be marked a complete recipe")
        result = read_csv(folder / "results.csv")
        for predictor, status in completion["predictor_status"].items():
            if not result.loc[result.predictor.eq(predictor), "status"].eq(status).all():
                raise ValueError("Result status differs from fold accounting")
        snapshots[group] = {"completion_sha256": digest(completion_path), "payload_sha256": completion["sha256"]}
        tables.append(result)
    return snapshots, pd.concat(tables, ignore_index=True)


def select_candidate(settings, settings_path, data_dir, out):
    out = Path(out)
    if (out / "selection.json").exists() or (out / "selection_none.json").exists():
        raise FileExistsError("Selection already frozen; do not overwrite")
    verify_code_freeze(settings_path, data_dir)
    config = make_config(settings_path, data_dir)
    snapshots, combined = verify_development_artifacts(out, config, settings)
    ranking = rank_candidates(combined, settings)
    if len(ranking) != settings["total_development_predictor_policy_combinations"]:
        raise ValueError("Not all registered predictor-policy combinations are present")
    save_csv(combined, out / "all_development_results.csv")
    save_csv(ranking, out / "selection_ranking.csv")
    eligible = ranking[ranking.eligible]
    if eligible.empty:
        write_json(out / "selection_none.json", {"status": "NO_ELIGIBLE_CANDIDATE", "config": config,
                   "created_at_utc": now(), "holdout_opened": False})
        print(json.dumps({"event": "no_eligible_candidate", "holdout_opened": False}), flush=True)
        return None
    selected = eligible.iloc[0].to_dict()
    code = selected["predictor"].split("_", 1)[1]
    recipe = next((r for r in settings["models"] if r["id"] == code), None)
    ensemble = next((e for e in settings["ensembles"] if e["id"] == code), None)
    members = [recipe["id"]] if recipe else ensemble["members"]
    policy = next(p for p in settings["policies"] if p["id"] == selected["policy"])
    selection = {
        "status": "FROZEN_SELECTED", "frozen_at_utc": now(), "config": config,
        "development_artifacts": snapshots, "ranking_sha256": digest(out / "selection_ranking.csv"),
        "all_development_results_sha256": digest(out / "all_development_results.csv"),
        "selected": selected, "group": selected["group"], "predictor": selected["predictor"],
        "policy": policy, "member_recipes": [r for r in settings["models"] if r["id"] in members],
        "ensemble": ensemble, "development_point_goal_met": bool(selected["minimum_year_accuracy"] >= 0.6),
        "holdout_opened_before_selection": False, "selection_uses_2026_outcomes": False,
    }
    write_exclusive_json(out / "selection.json", selection)
    print(json.dumps({"event": "selection_frozen", "predictor": selection["predictor"],
                      "policy": policy["id"], "minimum_development_year_accuracy": selected["minimum_year_accuracy"]}), flush=True)
    return selection


def validate_evaluation_guard(out, config, settings):
    """Only development files are accessed here; no holdout path is opened."""
    out = Path(out)
    selection_path = out / "selection.json"
    if not selection_path.exists():
        raise FileNotFoundError("A frozen selection is required before any holdout access")
    if (out / "evaluation" / "run_started.json").exists():
        raise FileExistsError("Holdout evaluation already started; one-time guard prevents reruns")
    selection = json.loads(selection_path.read_text())
    if selection.get("status") != "FROZEN_SELECTED" or selection["config"] != config:
        raise ValueError("Selection code/settings/development inputs changed")
    snapshots, combined = verify_development_artifacts(out, config, settings)
    if snapshots != selection["development_artifacts"]:
        raise ValueError("Development snapshot changed after selection")
    if digest(out / "selection_ranking.csv") != selection["ranking_sha256"]:
        raise ValueError("Frozen ranking changed")
    if digest(out / "all_development_results.csv") != selection["all_development_results_sha256"]:
        raise ValueError("Frozen combined development results changed")
    ranking = rank_candidates(combined, settings)
    eligible = ranking[ranking.eligible]
    if eligible.empty:
        raise ValueError("No eligible candidate; do not open holdout")
    best = eligible.iloc[0]
    if (best["predictor"], best["policy"], best["group"]) != (selection["predictor"], selection["policy"]["id"], selection["group"]):
        raise ValueError("Frozen candidate is not the preregistered ranking winner")
    validate_selection_payload(selection, settings)
    return selection


def validate_selection_payload(selection, settings):
    """IDs alone are insufficient: parameters and ensemble membership are frozen too."""
    group = selection["group"]
    if group not in settings["batch_groups"] or not selection["predictor"].startswith(group + "_"):
        raise ValueError("Unregistered selected feature group")
    code = selection["predictor"].split("_", 1)[1]
    recipe = next((r for r in settings["models"] if r["id"] == code), None)
    ensemble = next((e for e in settings["ensembles"] if e["id"] == code), None)
    if recipe is None and ensemble is None:
        raise ValueError("Unregistered selected predictor")
    members = [recipe["id"]] if recipe is not None else ensemble["members"]
    expected_recipes = [r for r in settings["models"] if r["id"] in members]
    policy = next((p for p in settings["policies"] if p["id"] == selection["policy"]["id"]), None)
    if selection["policy"] != policy or selection["member_recipes"] != expected_recipes or selection["ensemble"] != ensemble:
        raise ValueError("Selected policy, recipe parameters or ensemble membership were changed")


def fit_v1_control(X, meta, start, end, settings):
    """Exact original logistic recipe, on features rebuilt from 2022-start bars."""
    local = dict(settings, calibration_days=90)
    fit, cal, test, _, cal_start, _ = split_masks(meta, "G1", start, end, 90)
    if fit.sum() < 2000 or cal.sum() < 500 or not test.any():
        raise ValueError("Insufficient V1 fit/calibration/test samples")
    if meta.loc[fit, "label_end_time"].max() >= cal_start or meta.loc[cal, "label_end_time"].max() >= start:
        raise ValueError("V1 strict label cutoff failure")
    model = make_pipeline(StandardScaler(), LogisticRegression(C=0.1, max_iter=500, random_state=settings["seed"]))
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        model.fit(X.loc[fit], meta.loc[fit, "y"].astype(int))
        raw = raw_scores(model, X.loc[cal])
        # This frozen control retains V1's negative-slope behavior; no V2 fallback.
        calibration_model = LogisticRegression(C=1_000_000.0, max_iter=500, random_state=settings["seed"])
        calibration_model.fit(raw, meta.loc[cal, "y"].astype(int))
        if any(issubclass(w.category, ConvergenceWarning) for w in caught):
            raise RuntimeError("V1 ConvergenceWarning: " + "; ".join(str(w.message) for w in caught))
    calibrator = {"mode": "sigmoid", "model": calibration_model,
                  "slope": float(calibration_model.coef_[0, 0]),
                  "fitted_slope": float(calibration_model.coef_[0, 0]),
                  "intercept": float(calibration_model.intercept_[0]), "allow_negative": True}
    pcal = calibrate(calibrator, raw)
    ptest = calibrate(calibrator, raw_scores(model, X.loc[test]))
    frame, cframe = scaffold(meta, "G1", start, end, local)
    add_predictor(frame, cframe, "V1_LOGISTIC38", ptest, pcal, {}, raw.ravel())
    split = {"group": "V1", "recipe": "V1_LOGISTIC38", "fold_start_utc": iso(start), "fold_end_utc": iso(end),
             "calibration_start_utc": iso(cal_start), "train_start_utc": "2022-01-01T00:00:00+00:00",
             "fit_count": int(fit.sum()), "calibration_count": int(cal.sum()), "test_count": int(test.sum()),
             "fit_last_label_end_utc": iso(meta.loc[fit, "label_end_time"].max()),
             "calibration_last_label_end_utc": iso(meta.loc[cal, "label_end_time"].max()),
             "strict_cutoffs_passed": True, "status": "OK", "warnings": "; ".join(str(w.message) for w in caught)}
    cal_record = {k: v for k, v in calibrator.items() if k != "model"}
    cal_record.update({"group": "V1", "predictor": "V1_LOGISTIC38", "fold_start_utc": iso(start),
                      "calibration_count": int(cal.sum()), "calibration_positive_rate": float(meta.loc[cal, "y"].mean())})
    artifact = {"model": model, "calibrator": calibrator, "feature_columns": list(X.columns),
                "fit_cutoff_utc": iso(cal_start), "calibration_cutoff_utc": iso(start),
                "feature_history_start_utc": "2022-01-01T00:00:00+00:00", "bar_ms": BAR_MS}
    return artifact, frame, cframe, split, cal_record


def block_bootstrap(frame, predictor, policy, seed, status="OK", replicates=2000):
    """Descriptive percentile CIs, resampling fixed UTC seven-day blocks together."""
    selected = policy_mask(frame, predictor, policy) & frame.y.notna().to_numpy()
    if status != "OK" or not selected.any():
        return {"status": "UNAVAILABLE", "reason": "Failed recipe or no selected non-doji predictions"}
    origin, stop = ms("2026-01-01"), ms("2026-10-01")
    block_ms = 7 * DAY_MS
    nblocks = int(np.ceil((stop-origin)/block_ms))
    indexes = ((frame.loc[selected, "prediction_time"].to_numpy(dtype=np.int64)-origin)//block_ms).astype(int)
    if (indexes < 0).any() or (indexes >= nblocks).any():
        raise ValueError("Bootstrap timeline is outside the registered evaluation interval")
    y = frame.loc[selected, "y"].to_numpy(dtype=int)
    p = frame.loc[selected, predictor + "__p_up"].to_numpy()
    correct = ((p >= 0.5) == y).astype(float)
    counts = np.bincount(indexes, minlength=nblocks)
    wins = np.bincount(indexes, weights=correct, minlength=nblocks)
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, nblocks, size=(replicates, nblocks))
    denominator = counts[draws].sum(axis=1)
    usable = denominator > 0
    accuracy = wins[draws].sum(axis=1)[usable]/denominator[usable]
    intervals = {}
    for name in CONTROL_NAMES:
        baseline = (frame.loc[selected, "ctrl_" + name].to_numpy() == y).astype(float)
        delta = np.bincount(indexes, weights=correct-baseline, minlength=nblocks)
        values = delta[draws].sum(axis=1)[usable]/denominator[usable]
        intervals[name] = {"point_difference": float((correct-baseline).mean()),
                           "percentile_95_low": float(np.quantile(values, .025)),
                           "percentile_95_high": float(np.quantile(values, .975))}
    return {"status": "OK", "descriptive_only": True, "used_for_selection": False,
            "method": "Percentile bootstrap of fixed UTC 7-day blocks anchored at 2026-01-01; include empty blocks",
            "requested_replicates": replicates, "nonempty_replicates": int(usable.sum()),
            "seed": seed, "total_calendar_blocks": nblocks, "blocks_with_selected_predictions": int((counts > 0).sum()),
            "selected_non_doji_count": int(selected.sum()), "point_accuracy": float(correct.mean()),
            "accuracy_percentile_95_low": float(np.quantile(accuracy, .025)),
            "accuracy_percentile_95_high": float(np.quantile(accuracy, .975)),
            "paired_accuracy_differences": intervals,
            "caveat": "Time dependence and regime changes remain; this is not a guarantee of future accuracy."}


def evaluate_candidate(settings, settings_path, data_dir, holdout_dir, out):
    """Only the already frozen winner and the registered V1 control are fitted."""
    out = Path(out)
    config = make_config(settings_path, data_dir)
    selection = validate_evaluation_guard(out, config, settings)
    folder = out / "evaluation"
    marker = {"status": "STARTED_NO_RERUN", "started_at_utc": now(), "config": config,
              "selection_sha256": digest(out / "selection.json"),
              "predictor": selection["predictor"], "policy": selection["policy"]}
    # Exclusive creation is the last step before any holdout-file access.
    write_exclusive_json(folder / "run_started.json", marker)
    verify_code_freeze(settings_path, data_dir, holdout_dir)
    heldout_hashes = {k: digest(p) for k, p in dataset_paths(holdout_dir, evaluation=True).items()}
    write_json(folder / "provenance.json", {**marker, "holdout_data_sha256": heldout_hashes,
                                         "evaluation_end_exclusive_utc": "2026-10-01T00:00:00+00:00"})
    history = load_inputs(data_dir)
    future = load_inputs(holdout_dir, evaluation=True)
    inputs = {k: pd.concat([history[k], future[k]], ignore_index=True) for k in history}
    groups, meta = features_v2.build_features(inputs["btc4h"], inputs["btc15m"], inputs["eth4h"])
    verify_feature_schema(groups, settings_path)
    group, predictor = selection["group"], selection["predictor"]
    X = groups[group]
    # Rebuilding after the 2022 slice preserves V1's original 96-bar warmup.
    v1_bars = inputs["btc4h"].loc[inputs["btc4h"].open_time >= ms("2022-01-01")].reset_index(drop=True)
    v1_groups, v1_meta = features_v2.build_features(v1_bars)
    v1_X = v1_groups["G1"]
    frames, calibration_frames, splits, calibration_records, failures = [], [], [], [], []
    v1_frames, v1_calibration_frames, v1_splits, v1_records = [], [], [], []
    status, v1_status = "OK", "OK"
    final_artifact, final_v1 = None, None
    for start, end in quarter_windows(2026, final_month=7):
        frame, cframe = scaffold(meta, group, start, end, settings)
        artifacts = {}
        fold_failed = False
        for recipe in selection["member_recipes"]:
            member = group + "_" + recipe["id"]
            try:
                artifact, ptest, pcal, raw, split, calrec = fit_recipe(X, meta, group, recipe, start, end, settings)
                artifacts[member] = artifact
                add_predictor(frame, cframe, member, ptest, pcal, artifact["thresholds"], raw)
                splits.append(split)
                calibration_records.append(dict(calrec, predictor=member))
                print(json.dumps({"event": "evaluation_member_fold_complete", "predictor": member,
                                  "fold_start_utc": iso(start), "status": "OK"}), flush=True)
            except Exception as exc:
                fold_failed, status = True, "FAILED"
                add_predictor(frame, cframe, member, np.full(len(frame), np.nan), np.full(len(cframe), np.nan),
                              {"Q70": 2.0, "Q85": 2.0}, np.full(len(cframe), np.nan))
                error = {"predictor": member, "group": group, "recipe": recipe["id"], "fold_start_utc": iso(start),
                         "fold_end_utc": iso(end), "status": "FAILED", "strict_cutoffs_passed": False,
                         "error": type(exc).__name__ + ": " + str(exc)}
                failures.append(error)
                splits.append(error)
                print(json.dumps({"event": "evaluation_member_fold_failed", **error}), flush=True)
        members = [group + "_" + r["id"] for r in selection["member_recipes"]]
        if selection["ensemble"] is not None:
            if fold_failed:
                ptest, pcal = np.full(len(frame), np.nan), np.full(len(cframe), np.nan)
                thresholds = {"Q70": 2.0, "Q85": 2.0}
            else:
                ptest = frame[[m + "__p_up" for m in members]].to_numpy().mean(axis=1)
                pcal = cframe[[m + "__p_up" for m in members]].to_numpy().mean(axis=1)
                thresholds = quantile_thresholds(pcal, settings["policies"])
            add_predictor(frame, cframe, predictor, ptest, pcal, thresholds)
            calibration_records.append({"group": group, "predictor": predictor, "fold_start_utc": iso(start),
                                        "mode": "FAILED_MEMBER" if fold_failed else "equal_weight_mean",
                                        "members": members, "calibration_count": len(cframe), **thresholds})
        else:
            thresholds = {name: float(frame[predictor + "__" + name].iloc[0]) for name in ("Q70", "Q85")}
        frame["selected_policy_signal"] = policy_mask(frame, predictor, selection["policy"])
        frames.append(frame)
        calibration_frames.append(cframe)
        if not fold_failed:
            final_artifact = {"study_type": "historical_classification_research", "config": config,
                              "selection_sha256": marker["selection_sha256"],
                              "group": group, "predictor": predictor, "policy": selection["policy"],
                              "member_artifacts": artifacts, "thresholds": thresholds,
                              "feature_columns": list(X.columns), "bar_ms": BAR_MS,
                              "calibration_cutoff_utc": iso(start), "forecast_fold_end_utc": iso(end),
                              "probability_definition": "P(next 4h close > next 4h open | non-doji next candle)"}
        try:
            v1_artifact, vf, vc, vs, vr = fit_v1_control(v1_X, v1_meta, start, end, settings)
            final_v1 = v1_artifact
            v1_splits.append(vs)
            v1_records.append(vr)
            print(json.dumps({"event": "v1_control_fold_complete", "fold_start_utc": iso(start), "status": "OK"}), flush=True)
        except Exception as exc:
            v1_status = "FAILED"
            vf, vc = scaffold(v1_meta, "G1", start, end, dict(settings, calibration_days=90))
            add_predictor(vf, vc, "V1_LOGISTIC38", np.full(len(vf), np.nan), np.full(len(vc), np.nan),
                          {}, np.full(len(vc), np.nan))
            error = {"group": "V1", "predictor": "V1_LOGISTIC38", "recipe": "V1_LOGISTIC38",
                     "fold_start_utc": iso(start), "fold_end_utc": iso(end), "status": "FAILED",
                     "strict_cutoffs_passed": False, "error": type(exc).__name__ + ": " + str(exc)}
            failures.append(error)
            v1_splits.append(error)
            print(json.dumps({"event": "v1_control_fold_failed", **error}), flush=True)
        v1_frames.append(vf)
        v1_calibration_frames.append(vc)
    combined = pd.concat(frames, ignore_index=True).sort_values("prediction_time").reset_index(drop=True)
    v1_combined = pd.concat(v1_frames, ignore_index=True).sort_values("prediction_time").reset_index(drop=True)
    if combined.prediction_time.duplicated().any() or v1_combined.prediction_time.duplicated().any():
        raise ValueError("Duplicated evaluation forecast timestamp")
    policies = [p for p in settings["policies"] if p["id"] in {"A500", selection["policy"]["id"]}]
    results = report_tables(combined, group, [predictor], policies, {predictor: status}, folder, [2026],
                            settings["evaluation_goal_gate"]["active_month_minimum_predictions"])
    save_forecasts(combined, folder)
    save_calibration(pd.concat(calibration_frames, ignore_index=True), folder)
    save_csv(pd.DataFrame(splits), folder / "split_audit.csv")
    write_json(folder / "calibration.json", calibration_records)
    write_json(folder / "failures.json", failures)
    v1_folder = folder / "v1_control"
    v1_policies = [p for p in settings["policies"] if p["id"] in {"A500", "A550"}]
    report_tables(v1_combined, "V1", ["V1_LOGISTIC38"], v1_policies, {"V1_LOGISTIC38": v1_status}, v1_folder, [2026])
    save_forecasts(v1_combined, v1_folder)
    save_calibration(pd.concat(v1_calibration_frames, ignore_index=True), v1_folder)
    save_csv(pd.DataFrame(v1_splits), v1_folder / "split_audit.csv")
    write_json(v1_folder / "calibration.json", v1_records)
    if final_v1 is not None:
        joblib.dump(final_v1, v1_folder / "last_historical_model.joblib", compress=3)
    if final_artifact is not None:
        final_artifact["evaluation_status"] = status
        joblib.dump(final_artifact, folder / "selected_historical_model.joblib", compress=3)
    chosen = score(combined, predictor, selection["policy"], status,
                   settings["evaluation_goal_gate"]["active_month_minimum_predictions"])
    full_policy = next(p for p in settings["policies"] if p["id"] == "A500")
    full = score(combined, predictor, full_policy, status)
    matched = combined[["prediction_time", "y", predictor + "__p_up"]].copy()
    matched["selected"] = policy_mask(combined, predictor, selection["policy"])
    matched = matched.merge(v1_combined[["prediction_time", "V1_LOGISTIC38__p_up"]], on="prediction_time", how="left", validate="one_to_one")
    mask = matched.selected & matched.y.notna() & matched["V1_LOGISTIC38__p_up"].notna()
    comparison = {"status": "OK" if status == v1_status == "OK" else "FAILED",
                  "matched_selected_non_doji_count": int(mask.sum()),
                  "v1_accuracy_on_v2_selected_timestamps": np.nan,
                  "v2_accuracy_on_same_timestamps": np.nan}
    if mask.any() and status == v1_status == "OK":
        comparison.update({
            "v1_accuracy_on_v2_selected_timestamps": float(((matched.loc[mask, "V1_LOGISTIC38__p_up"] >= .5) == matched.loc[mask, "y"]).mean()),
            "v2_accuracy_on_same_timestamps": float(((matched.loc[mask, predictor + "__p_up"] >= .5) == matched.loc[mask, "y"]).mean())})
    save_csv(matched, folder / "matched_v1_control.csv")
    write_json(folder / "matched_v1_comparison.json", comparison)
    uncertainty = block_bootstrap(combined, predictor, selection["policy"], settings["seed"], status)
    write_json(folder / "uncertainty.json", uncertainty)
    gate = settings["evaluation_goal_gate"]
    gate_checks = {
        "all_three_folds_successful": status == "OK",
        "accuracy_at_least_target": bool(np.isfinite(chosen["accuracy"]) and chosen["accuracy"] >= gate["accuracy_at_least"]),
        "selected_non_doji_count": chosen["scored_count"] >= gate["selected_non_doji_at_least"],
        "active_months": chosen["active_months"] >= gate["active_months_at_least"],
        "month_concentration": chosen["max_month_share"] <= gate["maximum_single_month_share"],
    }
    summary = {"status": status, "predictor": predictor, "policy": selection["policy"], "config": config,
               "selection_sha256": marker["selection_sha256"], "holdout_data_sha256": heldout_hashes,
               "full_coverage_metrics": full, "selected_metrics": chosen,
               "goal_gate_checks": gate_checks, "point_60_percent_goal_met": all(gate_checks.values()),
               "v1_comparison": comparison, "uncertainty": uncertainty,
               "no_model_or_policy_switch_after_evaluation": True}
    write_json(folder / "evaluation_summary.json", summary)
    payload = [p for p in folder.rglob("*") if p.is_file() and p.name != "completion.json"]
    write_json(folder / "completion.json", {"status": "COMPLETE", "model_status": status,
               "finished_at_utc": now(), "config": config, "selection_sha256": marker["selection_sha256"],
               "expected_folds": 3, "v1_status": v1_status,
               "sha256": {str(p.relative_to(folder)): digest(p) for p in sorted(payload)}})
    print(json.dumps(native({"event": "evaluation_complete", "predictor": predictor, "policy": selection["policy"]["id"],
                      "status": status, "accuracy": chosen["accuracy"], "scored_count": chosen["scored_count"],
                      "goal_met": summary["point_60_percent_goal_met"]})), flush=True)
    return summary


def predict_with_artifact(artifact, groups, meta, asof):
    """Reusable historical inference API; inputs must contain only candles closed by asof."""
    if artifact.get("evaluation_status") != "OK":
        raise ValueError("Artifact did not complete all evaluation folds")
    cutoff = ms(artifact["calibration_cutoff_utc"])
    asof_ms = ms(asof)
    group = artifact["group"]
    X = groups[group]
    if list(X.columns) != artifact["feature_columns"]:
        raise ValueError("Artifact feature schema mismatch")
    eligible = meta[f"eligible_{group}"] & (meta.prediction_time <= asof_ms)
    if not eligible.any():
        raise ValueError("No eligible closed candle at the stated asof")
    index = meta.loc[eligible, "prediction_time"].idxmax()
    prediction_time = int(meta.loc[index, "prediction_time"])
    if prediction_time < cutoff:
        raise ValueError("Artifact calibration was not available at this prediction time")
    probabilities = []
    for member in artifact["member_artifacts"].values():
        probabilities.append(float(calibrate(member["calibrator"], raw_scores(member["model"], X.loc[[index]]))[0]))
    p = float(np.mean(probabilities))
    policy = artifact["policy"]
    threshold = policy["threshold"] if policy["kind"] == "absolute" else artifact["thresholds"][policy["id"]]
    stale = asof_ms >= prediction_time + BAR_MS
    return {"p_up_conditional_non_doji": p, "p_down_conditional_non_doji": 1-p,
            "direction": "UP" if p >= .5 else "DOWN", "confidence": max(p, 1-p),
            "threshold": threshold, "abstain": stale or max(p, 1-p) < threshold,
            "stale_input": stale, "prediction_time_utc": iso(prediction_time),
            "target_end_exclusive_utc": iso(prediction_time + BAR_MS),
            "artifact_available_utc": artifact["calibration_cutoff_utc"], "historical_research_only": True}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", required=True, choices=("development", "select", "evaluation"))
    parser.add_argument("--group", choices=("G1", "G2", "G3", "G4"))
    parser.add_argument("--settings", type=Path, default=ROOT / "settings.json")
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data" / "development")
    parser.add_argument("--holdout-dir", type=Path, default=ROOT / "data" / "holdout_2026")
    parser.add_argument("--out", type=Path, default=ROOT / "results")
    args = parser.parse_args(argv)
    settings, _ = settings_and_hash(args.settings)
    with threadpool_limits(limits=2):
        if args.phase == "development":
            if args.group is None:
                parser.error("--phase development requires --group")
            if (args.out / "selection.json").exists() or (args.out / "selection_none.json").exists():
                raise FileExistsError("Development is frozen after selection")
            develop_group(args.group, settings, args.settings, args.data_dir, args.out)
        elif args.phase == "select":
            select_candidate(settings, args.settings, args.data_dir, args.out)
        else:
            try:
                evaluate_candidate(settings, args.settings, args.data_dir, args.holdout_dir, args.out)
            except Exception as exc:
                marker = args.out / "evaluation" / "run_started.json"
                if marker.exists() and not (args.out / "evaluation" / "completion.json").exists():
                    write_json(args.out / "evaluation" / "fatal_error.json",
                               {"error": type(exc).__name__ + ": " + str(exc), "at_utc": now(),
                                "rerun_prohibited": True})
                raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

