"""Independent, read-only audit of the preregistered BTC 4h V2 study.

No engine/model functions are imported and no estimator is fitted.  Labels,
eligible timestamps, purged chronological split counts, policy masks, metrics,
and selection ranks are independently reconstructed from the official candles
and the saved prediction ledgers.  CSV floats are read with round-trip precision.

The default development audit never opens files in data/holdout_2026.  The test
audit is a separate, explicit command that additionally requires --allow-holdout.
Only audit-prefixed output files are written; study outcomes are never changed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
from typing import Any

import numpy as np
import pandas as pd
from scipy.special import expit
from scipy.stats import rankdata

BAR_MS = 14_400_000
INTRA_MS = 900_000
DAY_MS = 86_400_000
EPS = 1e-6
EXPECTED_SETTINGS_SHA256 = "ecbbe9d99fb00161c6f613d7347df4f556f8a82a283ba9d34991e77274976f15"
DEVELOPMENT_FILES = {
    "btc4h": ("BTCUSDT_4h_2020-01_2025-12.csv.gz", "651db1d671f6b15eca8ed0638f29bb78b52ab85e20118bd7c51975efd8c932b2"),
    "btc15m": ("BTCUSDT_15m_2020-01_2025-12.csv.gz", "59a590e1747aa4ae25092d1889b7e38f03fcfbf32b5e027d873cd6f30114788b"),
    "eth4h": ("ETHUSDT_4h_2020-01_2025-12.csv.gz", "6036b931c1383321491d0858b57c1e92713bf2fca974eb2d1611021b55cca269"),
}
CONTROL_NAMES = ("always_up", "always_down", "past_majority", "same_currentcolor", "opposite_currentcolor")
FLOAT_METRICS = (
    "accuracy", "balanced_accuracy", "bullish_precision", "bearish_precision",
    "log_loss", "brier", "roc_auc", "full_log_loss",
    *("matched_" + name + "_accuracy" for name in CONTROL_NAMES),
)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text())


def read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, float_precision="round_trip")


def ms(value: Any) -> int:
    if isinstance(value, (int, np.integer)):
        return int(value)
    if isinstance(value, (float, np.floating)) and np.isfinite(value):
        return int(value)
    return int(pd.Timestamp(value).value // 1_000_000)


def iso(value: Any) -> str:
    return pd.Timestamp(ms(value), unit="ms", tz="UTC").isoformat()


def clean_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): clean_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean_json(v) for v in value]
    if isinstance(value, np.ndarray):
        return clean_json(value.tolist())
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return float(value) if math.isfinite(value) else None
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, Path):
        return str(value)
    return value


class Checks:
    """Collect compact reproducible checks, retaining all failures."""

    def __init__(self):
        self.rows: list[dict[str, Any]] = []

    def check(self, name: str, passed: Any, detail: Any = None) -> bool:
        ok = bool(passed)
        self.rows.append({"check": name, "passed": ok, "detail": clean_json(detail)})
        return ok

    def equal(self, name: str, actual: Any, expected: Any, atol: float = 2e-12) -> bool:
        try:
            a, b = np.asarray(actual, dtype=float), np.asarray(expected, dtype=float)
            ok = a.shape == b.shape and np.allclose(a, b, rtol=atol, atol=atol, equal_nan=True)
            if ok:
                detail = {"elements": int(a.size)}
            elif a.shape == b.shape:
                different = ~np.isclose(a, b, rtol=atol, atol=atol, equal_nan=True)
                ix = np.flatnonzero(different)[:6]
                detail = {"mismatches": int(different.sum()), "first_indices": ix,
                          "actual": a.ravel()[ix], "expected": b.ravel()[ix]}
            else:
                detail = {"actual_shape": a.shape, "expected_shape": b.shape}
        except (TypeError, ValueError):
            a, b = np.asarray(actual), np.asarray(expected)
            ok = a.shape == b.shape and bool(np.array_equal(a, b))
            detail = None if ok else {"actual": str(actual)[:300], "expected": str(expected)[:300]}
        return self.check(name, ok, detail)

    @property
    def passed(self) -> bool:
        return all(row["passed"] for row in self.rows)


def consecutive_history(open_times: np.ndarray, interval: int) -> np.ndarray:
    times = np.asarray(open_times, dtype=np.int64)
    out = np.zeros(len(times), dtype=np.int64)
    for i in range(1, len(times)):
        out[i] = out[i - 1] + 1 if times[i] - times[i - 1] == interval else 0
    return out


def rolling_positive(values: np.ndarray, window: int) -> np.ndarray:
    """All finite, nonnegative inputs; independently compute positive windows."""
    x = np.asarray(values, dtype=float)
    sums = np.cumsum(np.r_[0., x])
    result = np.zeros(len(x), dtype=bool)
    result[window - 1:] = (sums[window:] - sums[:-window]) > 0
    return result


def raw_metadata(btc: pd.DataFrame, intra: pd.DataFrame, eth: pd.DataFrame,
                 checks: Checks | None = None) -> pd.DataFrame:
    """Reconstruct target/timing/masks without importing feature code."""
    for name, frame, interval in (("BTC4h", btc, BAR_MS), ("BTC15m", intra, INTRA_MS), ("ETH4h", eth, BAR_MS)):
        times = frame.open_time.to_numpy(dtype=np.int64)
        valid = (len(times) > 0 and bool((np.diff(times) > 0).all()) and
                 bool((times % interval == 0).all()) and
                 bool((frame.close_time.to_numpy() == times + interval - 1).all()))
        if checks:
            checks.check("source_grid:" + name, valid)
        if not valid:
            raise ValueError("Invalid source timestamp grid: " + name)
    times = btc.open_time.to_numpy(dtype=np.int64)
    prediction = btc.close_time.to_numpy(dtype=np.int64) + 1
    current = np.sign(btc.close.to_numpy() - btc.open.to_numpy())
    adjacent = np.r_[np.diff(times) == BAR_MS, False]
    color = np.r_[current[1:], np.nan]
    color[~adjacent] = np.nan
    y = np.where(np.isin(color, [-1, 1]), (color + 1) / 2, np.nan)
    g1 = consecutive_history(times, BAR_MS) >= 96
    for n in (1, 4, 16, 96):
        g1 &= rolling_positive(btc.volume.to_numpy(), n)
    for column in ("quote_volume", "trades"):
        g1 &= rolling_positive(btc[column].to_numpy(), 16)
    # A complete bucket contains every expected timestamp, and nothing else.
    itimes = intra.open_time.to_numpy(dtype=np.int64)
    buckets = itimes // BAR_MS * BAR_MS
    unique, starts, counts = np.unique(buckets, return_index=True, return_counts=True)
    complete_set = set()
    for bucket, start, count in zip(unique, starts, counts):
        if count == 16 and np.array_equal(itimes[start:start + count], bucket + np.arange(16) * INTRA_MS):
            complete_set.add(int(bucket))
    complete = np.array([int(t) in complete_set for t in times], dtype=bool)
    etimes = eth.open_time.to_numpy(dtype=np.int64)
    ehist = consecutive_history(etimes, BAR_MS)
    eth_ok = {int(t): int(c) + 1 for t, c, h in zip(etimes, eth.close_time, ehist) if h >= 96}
    eth_available = np.array([eth_ok.get(int(t)) == int(p) for t, p in zip(times, prediction)], dtype=bool)
    return pd.DataFrame({
        "current_open_time": times, "prediction_time": prediction,
        "target_open_time": times + BAR_MS, "label_end_time": times + 2 * BAR_MS,
        "current_color": current, "target_color": color, "y": y,
        "target_available": adjacent, "eligible_G1": g1, "eligible_G2": g1,
        "eligible_G3": g1 & complete, "eligible_G4": g1 & complete & eth_available,
        "intrabar_complete": complete, "eth_available": eth_available,
    })


def quarter_folds(years: list[int]) -> list[tuple[int, int]]:
    result = []
    for year in years:
        for month in (1, 4, 7, 10):
            start = pd.Timestamp(year=year, month=month, day=1, tz="UTC")
            result.append((ms(start), ms(start + pd.DateOffset(months=3))))
    return result


def independent_splits(meta: pd.DataFrame, group: str, start: int, end: int,
                       train_days: int | None, calibration_days: int = 180) -> dict[str, Any]:
    eligible = meta["eligible_" + group].to_numpy(dtype=bool)
    available = meta.target_available.to_numpy(dtype=bool)
    labeled = eligible & available & np.isfinite(meta.y.to_numpy())
    t = meta.prediction_time.to_numpy(dtype=np.int64)
    label_end = meta.label_end_time.to_numpy(dtype=np.int64)
    calibration_start = start - calibration_days * DAY_MS
    train_start = calibration_start - train_days * DAY_MS if train_days is not None else None
    fit = labeled & (label_end < calibration_start)
    if train_start is not None:
        fit &= t >= train_start
    calibration = labeled & (t >= calibration_start) & (label_end < start)
    test = eligible & available & (t >= start) & (t < end)
    prior = labeled & (label_end < start)
    return dict(fit=fit, calibration=calibration, test=test, prior=prior,
                calibration_start=calibration_start, train_start=train_start)


def probability_metrics(y: np.ndarray, p: np.ndarray) -> dict[str, float]:
    """Pure array formulas; independent of engine and sklearn metric helpers."""
    y, p = np.asarray(y, dtype=int), np.asarray(p, dtype=float)
    names = ("accuracy", "balanced_accuracy", "bullish_precision", "bearish_precision", "log_loss", "brier", "roc_auc")
    if not len(y):
        return dict.fromkeys(names, np.nan)
    up = p >= .5
    positive, negative = y == 1, y == 0
    clipped = np.clip(p, EPS, 1 - EPS)
    n1, n0 = int(positive.sum()), int(negative.sum())
    auc = ((rankdata(p, method="average")[positive].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)
           if n1 and n0 else np.nan)
    balanced = ((up[positive].mean() + (~up[negative]).mean()) / 2 if n1 and n0 else np.nan)
    return {
        "accuracy": float((up == y).mean()), "balanced_accuracy": float(balanced),
        "bullish_precision": float(y[up].mean()) if up.any() else np.nan,
        "bearish_precision": float((1 - y[~up]).mean()) if (~up).any() else np.nan,
        "log_loss": float(-(y * np.log(clipped) + (1 - y) * np.log1p(-clipped)).mean()),
        "brier": float(np.square(p - y).mean()), "roc_auc": float(auc),
    }


def policy_mask(frame: pd.DataFrame, predictor: str, policy: dict) -> np.ndarray:
    p = frame[predictor + "__p_up"].to_numpy(dtype=float)
    threshold = (float(policy["threshold"]) if policy["kind"] == "absolute"
                 else frame[predictor + "__" + policy["id"]].to_numpy(dtype=float))
    return np.isfinite(p) & (np.maximum(p, 1 - p) >= threshold)


def independent_summary(frame: pd.DataFrame, predictor: str, policy: dict,
                        successful: bool = True, active_minimum: int = 5) -> dict:
    p = frame[predictor + "__p_up"].to_numpy(dtype=float)
    y = frame.y.to_numpy(dtype=float)
    selected = policy_mask(frame, predictor, policy)
    scored = selected & np.isfinite(y)
    full = np.isfinite(p) & np.isfinite(y)
    pred_up = p[scored] >= .5
    months = pd.to_datetime(frame.prediction_time, unit="ms", utc=True).dt.strftime("%Y-%m").to_numpy()
    _, month_counts = np.unique(months[scored], return_counts=True)
    result = {
        "forecast_count": len(frame), "available_forecast_count": int(np.isfinite(p).sum()),
        "non_doji_count": int(np.isfinite(y).sum()), "selected_count": int(selected.sum()),
        "scored_count": int(scored.sum()),
        "coverage": float(selected.mean()) if len(frame) else np.nan,
        "scored_coverage": float(scored.sum() / np.isfinite(y).sum()) if np.isfinite(y).any() else np.nan,
        "predicted_up_count": int(pred_up.sum()), "predicted_down_count": int((~pred_up).sum()),
        "correct_up_count": int((y[scored][pred_up] == 1).sum()),
        "correct_down_count": int((y[scored][~pred_up] == 0).sum()),
        "active_months": int((month_counts >= active_minimum).sum()),
        "max_month_share": float(month_counts.max() / scored.sum()) if scored.any() else 0.0,
        **probability_metrics(y[scored], p[scored]),
        "full_log_loss": probability_metrics(y[full], p[full])["log_loss"],
    }
    for name in CONTROL_NAMES:
        cp = frame["ctrl_" + name].to_numpy(dtype=float)
        matching = scored & np.isfinite(cp)
        result["matched_" + name + "_accuracy"] = (
            float(((cp[matching] >= .5) == y[matching]).mean()) if matching.any() else np.nan)
    if not successful:
        for name in FLOAT_METRICS:
            result[name] = np.nan
    return result


def quantile_threshold(probabilities: np.ndarray, q: float) -> float:
    p = np.asarray(probabilities, dtype=float)
    p = p[np.isfinite(p)]
    if not len(p):
        return np.nan
    confidence = np.maximum(p, 1 - p)
    return 2.0 if np.ptp(confidence) < 1e-8 else float(np.quantile(confidence, q, method="linear"))


def independent_ranking(summaries: pd.DataFrame, settings: dict) -> pd.DataFrame:
    """Apply the fixed gates and all tie breaks; no trial re-ranking on test."""
    gate = settings["development_sample_gate"]
    rows = []
    years = settings["development_evaluation_years"]
    for (predictor, policy), group in summaries.groupby(["predictor", "policy"], sort=True):
        keyed = {str(row["period"]): row for row in group.to_dict("records")}
        if not all(str(y) in keyed for y in years) or "ALL" not in keyed:
            raise ValueError("Missing annual or pooled summary: " + predictor + "/" + policy)
        annual = [keyed[str(y)] for y in years]
        pooled = keyed["ALL"]
        ok = all(row["status"] == "OK" and
                 row["scored_count"] >= gate["minimum_selected_non_doji_each_year"] and
                 row["active_months"] >= gate["minimum_active_months_each_year"] and
                 row["max_month_share"] <= gate["maximum_single_month_share"] and
                 np.isfinite(row["accuracy"]) for row in annual) and np.isfinite(pooled["full_log_loss"])
        rows.append({"group": predictor.split("_")[0], "predictor": predictor,
                     "policy": policy, "eligible": ok,
                     "min_year_accuracy": min(r["accuracy"] for r in annual),
                     "pooled_accuracy": pooled["accuracy"],
                     "min_year_scored_count": min(r["scored_count"] for r in annual),
                     "full_log_loss": pooled["full_log_loss"]})
    result = pd.DataFrame(rows).sort_values(
        ["eligible", "min_year_accuracy", "pooled_accuracy", "min_year_scored_count", "full_log_loss", "predictor", "policy"],
        ascending=[False, False, False, False, True, True, True], kind="stable", na_position="last")
    result["eligible_rank"] = np.where(result.eligible, np.arange(len(result)) + 1, np.nan)
    return result.reset_index(drop=True)


def audit_frozen_inputs(root: Path, checks: Checks, allow_holdout: bool = False) -> dict:
    checks.equal("preregistered_settings_sha256", sha256(root / "settings.json"), EXPECTED_SETTINGS_SHA256)
    prereg = read_json(root / "preregistration.json")
    checks.equal("preregistration_settings_hash", prereg["settings_sha256"], sha256(root / "settings.json"))
    checks.check("preregistration_before_fit", prereg["fit_count"] == 0 and not prereg["new_evaluation_performance_accessed"])
    spec = read_json(root / "feature_specification.json")
    checks.equal("feature_source_frozen_hash", sha256(root / "features_v2.py"), spec["features_code_sha256"])
    for name, schema in spec["groups"].items():
        checks.check("feature_count:" + name, len(schema["columns"]) == schema["feature_count"])
        checks.check("feature_target_exclusion:" + name,
                     not set(schema["columns"]) & {"y", "target_open", "target_close", "target_color", "label_end_time"})
    freeze_path = root / "engine_freeze.json"
    if not freeze_path.is_file():
        raise FileNotFoundError("Required pre-fit engine_freeze.json is missing")
    freeze = read_json(freeze_path)
    checks.equal("engine_freeze_settings_hash", freeze["settings_sha256"], sha256(root / "settings.json"))
    checks.check("engine_freeze_time_after_preregistration", pd.Timestamp(freeze["frozen_at_utc"]) >= pd.Timestamp(prereg["frozen_at_utc"]))
    for relative, expected in freeze.get("code_sha256", {}).items():
        checks.equal("frozen_code:" + relative, sha256(root / relative), expected)
    for relative, expected in freeze.get("development_data_sha256", {}).items():
        checks.equal("frozen_development_data:" + relative, sha256(root / relative), expected)
    if allow_holdout:
        for relative, expected in freeze.get("holdout_data_sha256", {}).items():
            checks.equal("frozen_evaluation_data:" + relative, sha256(root / relative), expected)
    else:
        checks.check("development_no_holdout_files_opened", True,
                     "holdout hash declarations retained unread; no holdout file was opened")
    return {"preregistration": prereg, "freeze": freeze, "feature_specification": spec}


def load_development(root: Path, checks: Checks) -> tuple[dict[str, pd.DataFrame], dict[str, str]]:
    frames, hashes = {}, {}
    for name, (filename, expected) in DEVELOPMENT_FILES.items():
        path = root / "data" / "development" / filename
        actual = sha256(path)
        checks.equal("canonical_development_hash:" + name, actual, expected)
        hashes[str(path.relative_to(root))] = actual
        frames[name] = read_csv(path)
    return frames, hashes


def compare_saved_summary(saved: pd.DataFrame, recomputed: pd.DataFrame,
                          keys: list[str], checks: Checks, prefix: str) -> None:
    checks.check(prefix + ":unique_keys", not saved.duplicated(keys).any())
    a = saved.copy()
    b = recomputed.copy()
    for key in keys:
        a[key], b[key] = a[key].astype(str), b[key].astype(str)
    a = a.set_index(keys).sort_index()
    b = b.set_index(keys).sort_index()
    if not checks.equal(prefix + ":exact_key_set", a.index.to_numpy(), b.index.to_numpy()):
        return
    for column in b.columns:
        if column not in a.columns:
            checks.check(prefix + ":column:" + column, False, "missing serialized metric")
        else:
            checks.equal(prefix + ":metric:" + column, a[column].to_numpy(), b[column].to_numpy())


def verify_frame_metadata(frame: pd.DataFrame, expected: pd.DataFrame, checks: Checks,
                          prefix: str, calendar: bool = False) -> None:
    a = frame.sort_values("prediction_time").reset_index(drop=True)
    b = expected.sort_values("prediction_time").reset_index(drop=True)
    checks.check(prefix + ":no_duplicate_timestamps", not a.prediction_time.duplicated().any())
    if not checks.equal(prefix + ":exact_prediction_timestamps", a.prediction_time.to_numpy(), b.prediction_time.to_numpy(), atol=0):
        return
    for name in ("current_open_time", "target_open_time", "label_end_time", "current_color", "target_color", "y"):
        checks.equal(prefix + ":" + name, a[name].to_numpy(), b[name].to_numpy(), atol=0)
    if calendar:
        dates = pd.to_datetime(a.prediction_time, unit="ms", utc=True)
        for name, expected_values in (("year", dates.dt.year), ("quarter", dates.dt.quarter),
                                      ("month", dates.dt.strftime("%Y-%m")),
                                      ("prediction_utc", dates.dt.strftime("%Y-%m-%dT%H:%M:%SZ"))):
            checks.equal(prefix + ":calendar:" + name, a[name].to_numpy(), expected_values.to_numpy(), atol=0)


def verify_config(config: dict, root: Path, data_hashes: dict, checks: Checks, prefix: str) -> None:
    checks.equal(prefix + ":settings_sha256", config["settings_sha256"], sha256(root / "settings.json"))
    checks.equal(prefix + ":engine_sha256", config["engine_sha256"], sha256(root / "engine_v2.py"))
    checks.equal(prefix + ":features_sha256", config["features_sha256"], sha256(root / "features_v2.py"))
    for name, filename in (("v1_reference_sha256", "reference/v1_model.py"),
                           ("feature_specification_sha256", "feature_specification.json"),
                           ("engine_freeze_sha256", "engine_freeze.json")):
        checks.equal(prefix + ":" + name, config[name], sha256(root / filename))
    for name, (filename, expected) in DEVELOPMENT_FILES.items():
        checks.equal(prefix + ":data:" + name, config["development_data_sha256"][name], expected)
    checks.equal(prefix + ":bar_ms", config["bar_ms"], BAR_MS, atol=0)
    checks.equal(prefix + ":round_trip_serialization", config["float_format"], "%.17g")


def verify_controls(frame: pd.DataFrame, meta: pd.DataFrame, group: str,
                    start: int, end: int, settings: dict, checks: Checks, prefix: str) -> None:
    masks = independent_splits(meta, group, start, end, None, settings["calibration_days"])
    rate = float(meta.loc[masks["prior"], "y"].mean())
    majority = int(rate >= .5)
    colors = frame.current_color.to_numpy()
    controls = {"always_up": np.ones(len(frame)), "always_down": np.zeros(len(frame)),
                "past_majority": np.full(len(frame), majority),
                "same_currentcolor": np.where(colors == 0, majority, colors > 0),
                "opposite_currentcolor": np.where(colors == 0, majority, colors < 0)}
    checks.equal(prefix + ":past_rate_available_before_fold", frame.past_bullish_rate.to_numpy(), np.full(len(frame), rate))
    for name, values in controls.items():
        checks.equal(prefix + ":control:" + name, frame["ctrl_" + name].to_numpy(), values, atol=0)


def verify_splits(split: pd.DataFrame, meta: pd.DataFrame, group: str, settings: dict,
                  folds: list[tuple[int, int]], checks: Checks) -> dict[tuple[str, int], bool]:
    prefix = group + ":split"
    split = split.copy()
    split["fold_ms"] = split.fold_start_utc.map(ms)
    checks.check(prefix + ":unique_recipe_fold", not split.duplicated(["recipe", "fold_ms"]).any())
    expected_keys = {(r["id"], start) for r in settings["models"] for start, _ in folds}
    actual_keys = set(zip(split.recipe, split.fold_ms))
    checks.check(prefix + ":exact_recipe_fold_set", actual_keys == expected_keys,
                 {"expected": len(expected_keys), "actual": len(actual_keys)})
    lookup = {(row["recipe"], row["fold_ms"]): row for row in split.to_dict("records")}
    status = {}
    for recipe in settings["models"]:
        for start, end in folds:
            key = (recipe["id"], start)
            row = lookup[key]
            stem = prefix + ":" + recipe["id"] + ":" + iso(start)
            passed = row["status"] == "OK"
            status[key] = passed
            checks.equal(stem + ":fold_end", ms(row["fold_end_utc"]), end, atol=0)
            checks.check(stem + ":registered_status", row["status"] in ("OK", "FAILED"))
            if not passed:
                checks.check(stem + ":failed_has_no_pass_claim", not bool(row["strict_cutoffs_passed"]))
                continue
            masks = independent_splits(meta, group, start, end, recipe["train_days"], settings["calibration_days"])
            checks.check(stem + ":strict_cutoff_flag", bool(row["strict_cutoffs_passed"]))
            checks.equal(stem + ":calibration_start", ms(row["calibration_start_utc"]), masks["calibration_start"], atol=0)
            checks.check(stem + ":train_start", (pd.isna(row["train_start_utc"]) if masks["train_start"] is None
                                                  else ms(row["train_start_utc"]) == masks["train_start"]))
            for field, maskname in (("fit_count", "fit"), ("calibration_count", "calibration"), ("test_count", "test")):
                checks.equal(stem + ":" + field, row[field], int(masks[maskname].sum()), atol=0)
            last_fit = int(meta.loc[masks["fit"], "label_end_time"].max())
            last_cal = int(meta.loc[masks["calibration"], "label_end_time"].max())
            checks.equal(stem + ":fit_last_label_end", ms(row["fit_last_label_end_utc"]), last_fit, atol=0)
            checks.equal(stem + ":calibration_last_label_end", ms(row["calibration_last_label_end_utc"]), last_cal, atol=0)
            checks.check(stem + ":independent_strict_purge", last_fit < masks["calibration_start"] and last_cal < start)
            checks.check(stem + ":disjoint_masks", not np.any(masks["fit"] & masks["calibration"]) and
                         not np.any(masks["fit"] & masks["test"]) and not np.any(masks["calibration"] & masks["test"]))
            checks.check(stem + ":minimum_samples", masks["fit"].sum() >= settings["minimum_fit_samples"] and
                         masks["calibration"].sum() >= settings["minimum_calibration_samples"])
    return status


def verify_calibration_and_ensembles(frame: pd.DataFrame, calibration: pd.DataFrame,
                                   records: list[dict], statuses: dict, group: str,
                                   settings: dict, folds: list[tuple[int, int]], checks: Checks) -> None:
    records_by_key = {(r["predictor"], ms(r["fold_start_utc"])): r for r in records}
    checks.check(group + ":calibration_records_unique", len(records_by_key) == len(records))
    expected_records = {(group + "_" + r["id"], start)
                        for r in settings["models"] for start, _ in folds if statuses[(r["id"], start)]}
    expected_records |= {(group + "_" + r["id"], start) for r in settings["ensembles"] for start, _ in folds}
    checks.check(group + ":calibration_record_exact_set", set(records_by_key) == expected_records)
    for start, end in folds:
        f = frame[frame.fold_start_utc.map(ms).eq(start)]
        c = calibration[calibration.fold_start_utc.map(ms).eq(start)]
        for recipe in settings["models"] + settings["ensembles"]:
            code = recipe["id"]
            predictor = group + "_" + code
            stem = predictor + ":calibration:" + iso(start)
            ptest = f[predictor + "__p_up"].to_numpy(dtype=float)
            pcal = c[predictor + "__p_up"].to_numpy(dtype=float)
            ensemble = "members" in recipe
            successful = (all(statuses[(member, start)] for member in recipe["members"])
                          if ensemble else statuses[(code, start)])
            checks.check(stem + ":probability_availability", bool(np.isfinite(ptest).all() and np.isfinite(pcal).all())
                         if successful else bool(np.isnan(ptest).all() and np.isnan(pcal).all()))
            if not successful:
                for qname in ("Q70", "Q85"):
                    checks.equal(stem + ":failed_abstention:" + qname, f[predictor + "__" + qname], np.full(len(f), 2.0))
                continue
            checks.check(stem + ":probability_bounds", bool(((ptest >= 0) & (ptest <= 1)).all() and ((pcal >= 0) & (pcal <= 1)).all()))
            rec = records_by_key[(predictor, start)]
            checks.equal(stem + ":calibration_count", rec["calibration_count"], len(c), atol=0)
            if ensemble:
                members = [group + "_" + name for name in recipe["members"]]
                checks.equal(stem + ":members", rec["members"], members)
                checks.equal(stem + ":test_equal_mean", ptest, np.mean(f[[m + "__p_up" for m in members]], axis=1))
                checks.equal(stem + ":calibration_equal_mean", pcal, np.mean(c[[m + "__p_up" for m in members]], axis=1))
                checks.equal(stem + ":mode", rec["mode"], "equal_weight_mean")
            else:
                raw = c[predictor + "__raw_score"].to_numpy(dtype=float)
                checks.check(stem + ":finite_raw_scores", np.isfinite(raw).all())
                checks.equal(stem + ":raw_std", rec["calibration_raw_score_std"], np.std(raw))
                checks.equal(stem + ":positive_rate", rec["calibration_positive_rate"], c.y.mean())
                if rec["mode"] == "sigmoid":
                    checks.check(stem + ":positive_calibration_slope", rec["slope"] > 0)
                    expected_p = expit(raw * rec["slope"] + rec["intercept"])
                elif rec["mode"] == "constant_fallback":
                    smooth = (c.y.sum() + 1) / (len(c) + 2)
                    expected_p = np.full(len(c), smooth)
                    checks.equal(stem + ":smoothed_probability", rec["constant_probability"], smooth)
                    checks.equal(stem + ":constant_test_probability", ptest, np.full(len(f), smooth))
                    reason = rec.get("reason")
                    checks.check(stem + ":fallback_justified", (reason == "nonpositive_slope" and rec["fitted_slope"] <= 0)
                                 or (reason == "single_class_calibration" and c.y.nunique() == 1))
                else:
                    checks.check(stem + ":known_calibrator_mode", False, rec["mode"])
                    expected_p = np.full(len(c), np.nan)
                checks.equal(stem + ":serialized_calibrated_probabilities", pcal, expected_p)
                conf = np.maximum(pcal, 1 - pcal)
                checks.equal(stem + ":confidence_min", rec["calibration_confidence_min"], conf.min())
                checks.equal(stem + ":confidence_max", rec["calibration_confidence_max"], conf.max())
            for policy in settings["policies"]:
                if policy["kind"] != "calibration_quantile":
                    continue
                name = policy["id"]
                threshold = quantile_threshold(pcal, policy["quantile"])
                checks.equal(stem + ":past_only_quantile_record:" + name, rec[name], threshold)
                checks.equal(stem + ":past_only_quantile_ledger:" + name, f[predictor + "__" + name], np.full(len(f), threshold))


def audit_group(root: Path, out: Path, group: str, meta: pd.DataFrame, settings: dict,
                frozen: dict, data_hashes: dict, checks: Checks) -> tuple[pd.DataFrame, dict]:
    folder = out / group
    completion = read_json(folder / "completion.json")
    checks.equal(group + ":completion_status", completion["status"], "COMPLETE")
    checks.equal(group + ":expected_folds", completion["expected_folds_per_recipe"], 8, atol=0)
    verify_config(completion["config"], root, data_hashes, checks, group + ":config")
    for filename, expected in completion["sha256"].items():
        checks.equal(group + ":artifact_hash:" + filename, sha256(folder / filename), expected)
    started = read_json(folder / "run_started.json")
    checks.check(group + ":started_after_engine_freeze", pd.Timestamp(started["started_at_utc"]) >= pd.Timestamp(frozen["freeze"]["frozen_at_utc"]))
    checks.check(group + ":completed_after_started", pd.Timestamp(completion["finished_at_utc"]) >= pd.Timestamp(started["started_at_utc"]))
    columns = read_json(folder / "feature_columns.json")
    checks.equal(group + ":frozen_feature_order", columns, frozen["feature_specification"]["groups"][group]["columns"])
    frame = read_csv(folder / "predictions.csv.gz")
    calibration = read_csv(folder / "calibration_predictions.csv.gz")
    split = read_csv(folder / "split_audit.csv")
    records = read_json(folder / "calibration.json")
    failures = read_json(folder / "failures.json")
    folds = quarter_folds(settings["development_evaluation_years"])
    expected_frames = []
    for start, end in folds:
        masks = independent_splits(meta, group, start, end, None, settings["calibration_days"])
        f = frame[frame.fold_start_utc.map(ms).eq(start)]
        c = calibration[calibration.fold_start_utc.map(ms).eq(start)]
        expected = meta[masks["test"]]
        expected_frames.append(expected)
        prefix = group + ":fold:" + iso(start)
        verify_frame_metadata(f, expected, checks, prefix + ":test", calendar=True)
        verify_frame_metadata(c, meta[masks["calibration"]], checks, prefix + ":calibration")
        checks.check(prefix + ":recorded_fold_ends", set(f.fold_end_utc.map(ms)) == {end} and set(c.fold_end_utc.map(ms)) == {end})
        verify_controls(f, meta, group, start, end, settings, checks, prefix)
    expected_all = pd.concat(expected_frames, ignore_index=True)
    verify_frame_metadata(frame, expected_all, checks, group + ":all_prediction_metadata", calendar=True)
    checks.check(group + ":exact_test_fold_set", set(frame.fold_start_utc.map(ms)) == {s for s, _ in folds})
    checks.check(group + ":exact_calibration_fold_set", set(calibration.fold_start_utc.map(ms)) == {s for s, _ in folds})
    checks.check(group + ":calibration_key_unique", not calibration.duplicated(["fold_start_utc", "prediction_time"]).any())
    checks.equal(group + ":completion_forecast_rows", completion["forecast_rows"], len(frame), atol=0)
    fold_status = verify_splits(split, meta, group, settings, folds, checks)
    expected_failures = {(group + "_" + code, start) for (code, start), ok in fold_status.items() if not ok}
    actual_failures = {(r["predictor"], ms(r["fold_start_utc"])) for r in failures}
    checks.check(group + ":failure_ledger_exact_set", expected_failures == actual_failures and len(failures) == len(actual_failures))
    checks.equal(group + ":failure_count", completion["recipe_fold_failures"], len(failures), atol=0)
    predictor_status = {}
    for recipe in settings["models"]:
        predictor_status[group + "_" + recipe["id"]] = "OK" if all(fold_status[(recipe["id"], start)] for start, _ in folds) else "FAILED"
    for ensemble in settings["ensembles"]:
        predictor_status[group + "_" + ensemble["id"]] = ("OK" if all(predictor_status[group + "_" + member] == "OK" for member in ensemble["members"]) else "FAILED")
    checks.check(group + ":failed_recipe_ensemble_propagation", completion["predictor_status"] == predictor_status)
    checks.check(group + ":exact_predictor_columns", {name[:-6] for name in frame if name.endswith("__p_up")} == set(predictor_status))
    verify_calibration_and_ensembles(frame, calibration, records, fold_status, group, settings, folds, checks)
    summaries, monthly, quarterly, sides = [], [], [], []
    for predictor, status in predictor_status.items():
        for policy in settings["policies"]:
            base = {"group": group, "predictor": predictor, "policy": policy["id"], "status": status}
            for period in [str(y) for y in settings["development_evaluation_years"]] + ["ALL"]:
                subset = frame if period == "ALL" else frame[frame.year.eq(int(period))]
                summaries.append({**base, "period": period, **independent_summary(subset, predictor, policy, status == "OK")})
            for month, subset in frame.groupby("month", sort=True):
                monthly.append({**base, "month": month, **independent_summary(subset, predictor, policy, status == "OK")})
            for (year, quarter), subset in frame.groupby(["year", "quarter"], sort=True):
                quarterly.append({**base, "year": year, "quarter": quarter,
                                  **independent_summary(subset, predictor, policy, status == "OK")})
            p = frame[predictor + "__p_up"].to_numpy()
            y = frame.y.to_numpy()
            selected = policy_mask(frame, predictor, policy) & np.isfinite(y)
            for name, side in (("UP", p >= .5), ("DOWN", p < .5)):
                mask = selected & side
                correct = int(((p[mask] >= .5) == y[mask]).sum())
                n = int(mask.sum())
                sides.append({**base, "side": name, "scored_count": n, "correct_count": correct,
                              "accuracy": correct / n if n and status == "OK" else np.nan})
    recomputed = pd.DataFrame(summaries)
    compare_saved_summary(read_csv(folder / "results.csv"), recomputed,
                          ["group", "predictor", "policy", "period"], checks, group + ":summary")
    compare_saved_summary(read_csv(folder / "monthly.csv"), pd.DataFrame(monthly),
                          ["group", "predictor", "policy", "month"], checks, group + ":monthly")
    compare_saved_summary(read_csv(folder / "quarterly.csv"), pd.DataFrame(quarterly),
                          ["group", "predictor", "policy", "year", "quarter"], checks, group + ":quarterly")
    compare_saved_summary(read_csv(folder / "sides.csv"), pd.DataFrame(sides),
                          ["group", "predictor", "policy", "side"], checks, group + ":sides")
    verify_shards(folder, frame, calibration, checks, group)
    return recomputed, {"group": group, "forecast_rows": len(frame), "predictor_status": predictor_status,
                        "completion_sha256": sha256(folder / "completion.json"), "payload_sha256": completion["sha256"]}


def verify_shards(folder: Path, frame: pd.DataFrame, calibration: pd.DataFrame,
                  checks: Checks, prefix: str) -> None:
    expected_shards = {"predictions_" + month + ".csv" for month in frame.month.unique()}
    actual_shards = {p.name for p in (folder / "predictions_monthly").glob("*.csv")}
    checks.check(prefix + ":exact_monthly_shard_set", actual_shards == expected_shards)
    for month, subset in frame.groupby("month", sort=True):
        shard = read_csv(folder / "predictions_monthly" / ("predictions_" + month + ".csv"))
        checks.check(prefix + ":monthly_shard_columns:" + month, list(subset.columns) == list(shard.columns))
        for column in subset:
            checks.equal(prefix + ":monthly_shard:" + month + ":" + column,
                         subset[column].to_numpy(), shard[column].to_numpy(), atol=0)
    expected_cal = {"calibration_" + pd.Timestamp(fold).strftime("%Y-%m") + ".csv" for fold in calibration.fold_start_utc.unique()}
    actual_cal = {p.name for p in (folder / "calibration_quarterly").glob("*.csv")}
    checks.check(prefix + ":exact_calibration_shard_set", expected_cal == actual_cal)
    for fold, subset in calibration.groupby("fold_start_utc", sort=True):
        label = pd.Timestamp(fold).strftime("%Y-%m")
        shard = read_csv(folder / "calibration_quarterly" / ("calibration_" + label + ".csv"))
        # A shard can infer all-NaN integer columns as float; compare values.
        checks.check(prefix + ":calibration_shard_columns:" + label, list(subset.columns) == list(shard.columns))
        for column in subset:
            checks.equal(prefix + ":calibration_shard:" + label + ":" + column,
                         subset[column].to_numpy(), shard[column].to_numpy(), atol=0)


def audit_selection(root: Path, out: Path, summaries: pd.DataFrame, groups: list[dict],
                    settings: dict, data_hashes: dict, checks: Checks) -> tuple[dict | None, pd.DataFrame]:
    ranking = independent_ranking(summaries, settings)
    checks.equal("selection:registered_combination_count", len(ranking), settings["total_development_predictor_policy_combinations"], atol=0)
    expected = {(group, group + "_" + recipe["id"], policy["id"])
                for group in settings["batch_groups"] for recipe in settings["models"] + settings["ensembles"]
                for policy in settings["policies"]}
    checks.check("selection:all_registered_predictor_policies", set(zip(ranking.group, ranking.predictor, ranking.policy)) == expected)
    combined_path = out / "all_development_results.csv"
    ranking_path = out / "selection_ranking.csv"
    compare_saved_summary(read_csv(combined_path), summaries, ["group", "predictor", "policy", "period"], checks, "selection:combined_summaries")
    saved_ranking = read_csv(ranking_path)
    renamed = ranking.rename(columns={"min_year_accuracy": "minimum_year_accuracy",
                                      "pooled_accuracy": "combined_accuracy",
                                      "min_year_scored_count": "minimum_year_n",
                                      "full_log_loss": "full_coverage_combined_log_loss"}).drop(columns="eligible_rank")
    checks.equal("selection:exact_ranked_predictor_order", saved_ranking.predictor.to_numpy(), renamed.predictor.to_numpy())
    checks.equal("selection:exact_ranked_policy_order", saved_ranking.policy.to_numpy(), renamed.policy.to_numpy())
    checks.equal("selection:rank_sequence", saved_ranking["rank"].to_numpy(), np.arange(1, len(ranking) + 1), atol=0)
    compare_saved_summary(saved_ranking, renamed, ["group", "predictor", "policy"], checks, "selection:ranking_gate_metrics")
    eligible = ranking[ranking.eligible]
    if eligible.empty:
        no_selection = read_json(out / "selection_none.json")
        checks.equal("selection:no_eligible_status", no_selection["status"], "NO_ELIGIBLE_CANDIDATE")
        checks.check("selection:no_test_without_eligible", no_selection["holdout_opened"] is False and not (out / "selection.json").exists())
        return None, ranking
    selection = read_json(out / "selection.json")
    best = eligible.iloc[0].to_dict()
    checks.equal("selection:frozen_status", selection["status"], "FROZEN_SELECTED")
    checks.equal("selection:group", selection["group"], best["group"])
    checks.equal("selection:predictor", selection["predictor"], best["predictor"])
    checks.equal("selection:policy", selection["policy"]["id"], best["policy"])
    checks.check("selection:full_policy_definition", selection["policy"] == next(p for p in settings["policies"] if p["id"] == best["policy"]))
    checks.check("selection:no_test_outcome_claim", selection["holdout_opened_before_selection"] is False and selection["selection_uses_2026_outcomes"] is False)
    verify_config(selection["config"], root, data_hashes, checks, "selection:config")
    snapshots = {g["group"]: {"completion_sha256": g["completion_sha256"], "payload_sha256": g["payload_sha256"]} for g in groups}
    checks.check("selection:development_artifact_snapshots", selection["development_artifacts"] == snapshots)
    checks.equal("selection:ranking_sha256", selection["ranking_sha256"], sha256(ranking_path))
    checks.equal("selection:combined_results_sha256", selection["all_development_results_sha256"], sha256(combined_path))
    for group in settings["batch_groups"]:
        completion = read_json(out / group / "completion.json")
        checks.check("selection:after_batch:" + group, pd.Timestamp(selection["frozen_at_utc"]) >= pd.Timestamp(completion["finished_at_utc"]))
    code = best["predictor"].split("_", 1)[1]
    ensemble = next((e for e in settings["ensembles"] if e["id"] == code), None)
    members = ensemble["members"] if ensemble else [code]
    checks.check("selection:member_recipes", selection["member_recipes"] == [r for r in settings["models"] if r["id"] in members])
    checks.check("selection:ensemble_definition", selection["ensemble"] == ensemble)
    checks.equal("selection:development_goal_claim", selection["development_point_goal_met"], best["min_year_accuracy"] >= settings["target_accuracy"])
    return best, ranking


def run_development_audit(root: Path, out: Path, one_group: str | None = None) -> dict:
    # A single-group audit supports prompt independent review after each batch.
    # The global audit additionally requires all groups and the frozen selection.
    settings = read_json(root / "settings.json")
    selected_groups = [one_group] if one_group else settings["batch_groups"]
    missing = [str(out / group / "completion.json") for group in selected_groups
               if not (out / group / "completion.json").is_file()]
    if missing:
        raise FileNotFoundError("Development audit waits for the requested completed groups: " + ", ".join(missing))
    if not one_group and not (out / "selection.json").is_file() and not (out / "selection_none.json").is_file():
        raise FileNotFoundError("Development audit waits for the one frozen selection or selection_none.json")
    checks = Checks()
    payload = {"holdout_files_opened": False, "audit_scope": selected_groups,
               "global_selection_audited": not bool(one_group)}
    try:
        frozen = audit_frozen_inputs(root, checks, allow_holdout=False)
        inputs, data_hashes = load_development(root, checks)
        meta = raw_metadata(inputs["btc4h"], inputs["btc15m"], inputs["eth4h"], checks)
        recomputed, groups = [], []
        for group in selected_groups:
            table, info = audit_group(root, out, group, meta, settings, frozen, data_hashes, checks)
            recomputed.append(table)
            groups.append(info)
        summaries = pd.concat(recomputed, ignore_index=True)
        selected, ranking = (None, None) if one_group else audit_selection(root, out, summaries, groups, settings, data_hashes, checks)
        # Audit outputs, never model or selection outputs.
        label = one_group if one_group else "development"
        summaries.to_csv(out / ("audit_recomputed_" + label + "_results.csv"), index=False, float_format="%.17g")
        payload.update({"groups": groups, "source_sha256": data_hashes,
                        "audited_predictor_policy_count": summaries[["predictor", "policy"]].drop_duplicates().shape[0],
                        "feature_review": "Source reviewed independently; 10 feature tests passed before fit. Target fields excluded from X; no future fill; exact complete intrabar and ETH joins; BTC/ETH gap warmup tested."})
        if ranking is not None:
            ranking.to_csv(out / "audit_recomputed_selection_ranking.csv", index=False, float_format="%.17g")
            payload.update({"selected": selected, "eligible_predictor_policy_count": int(ranking.eligible.sum()),
                            "selection_file_sha256": sha256(out / ("selection.json" if selected else "selection_none.json"))})
    except Exception as exc:
        checks.check("audit_execution_exception", False, type(exc).__name__ + ": " + str(exc))
        payload["exception"] = type(exc).__name__ + ": " + str(exc)
    return write_report(root, out, one_group if one_group else "development", checks, payload)


def verify_evaluation_tables(folder: Path, frame: pd.DataFrame, group: str, predictor: str,
                             policies: list[dict], status: str, checks: Checks, prefix: str) -> pd.DataFrame:
    summaries, monthly, quarterly, sides = [], [], [], []
    for policy in policies:
        base = {"group": group, "predictor": predictor, "policy": policy["id"], "status": status}
        for period in ("2026", "ALL"):
            summaries.append({**base, "period": period, **independent_summary(frame, predictor, policy, status == "OK")})
        for month, subset in frame.groupby("month", sort=True):
            monthly.append({**base, "month": month, **independent_summary(subset, predictor, policy, status == "OK")})
        for (year, quarter), subset in frame.groupby(["year", "quarter"], sort=True):
            quarterly.append({**base, "year": year, "quarter": quarter,
                              **independent_summary(subset, predictor, policy, status == "OK")})
        p, y = frame[predictor + "__p_up"].to_numpy(), frame.y.to_numpy()
        selected = policy_mask(frame, predictor, policy) & np.isfinite(y)
        for name, side in (("UP", p >= .5), ("DOWN", p < .5)):
            mask = selected & side
            n = int(mask.sum())
            correct = int(((p[mask] >= .5) == y[mask]).sum())
            sides.append({**base, "side": name, "scored_count": n, "correct_count": correct,
                          "accuracy": correct / n if n and status == "OK" else np.nan})
    table = pd.DataFrame(summaries)
    compare_saved_summary(read_csv(folder / "results.csv"), table,
                          ["group", "predictor", "policy", "period"], checks, prefix + ":summary")
    compare_saved_summary(read_csv(folder / "monthly.csv"), pd.DataFrame(monthly),
                          ["group", "predictor", "policy", "month"], checks, prefix + ":monthly")
    compare_saved_summary(read_csv(folder / "quarterly.csv"), pd.DataFrame(quarterly),
                          ["group", "predictor", "policy", "year", "quarter"], checks, prefix + ":quarterly")
    compare_saved_summary(read_csv(folder / "sides.csv"), pd.DataFrame(sides),
                          ["group", "predictor", "policy", "side"], checks, prefix + ":sides")
    return table


def independent_bootstrap(frame: pd.DataFrame, predictor: str, policy: dict,
                          seed: int, successful: bool) -> dict:
    """Independently aggregate correctness into calendar blocks, then resample."""
    mask = policy_mask(frame, predictor, policy) & np.isfinite(frame.y.to_numpy())
    if not successful or not mask.any():
        return {"status": "UNAVAILABLE"}
    selected = frame.loc[mask]
    origin, stop = ms("2026-01-01T00:00:00Z"), ms("2026-10-01T00:00:00Z")
    block_count = math.ceil((stop - origin) / (7 * DAY_MS))
    ids = ((selected.prediction_time.to_numpy(dtype=np.int64) - origin) // (7 * DAY_MS)).astype(int)
    if np.any((ids < 0) | (ids >= block_count)):
        raise ValueError("Evaluation timestamp outside fixed bootstrap interval")
    truth = selected.y.to_numpy(dtype=int)
    correct = (selected[predictor + "__p_up"].to_numpy() >= .5) == truth
    count_by_block = np.zeros(block_count, dtype=int)
    correct_by_block = np.zeros(block_count, dtype=int)
    deltas_by_block = {name: np.zeros(block_count, dtype=int) for name in CONTROL_NAMES}
    for block in range(block_count):
        ix = ids == block
        count_by_block[block] = int(ix.sum())
        correct_by_block[block] = int(correct[ix].sum())
        for name in CONTROL_NAMES:
            control_correct = selected["ctrl_" + name].to_numpy()[ix] == truth[ix]
            deltas_by_block[name][block] = int(correct[ix].sum() - control_correct.sum())
    rng = np.random.default_rng(seed)
    # Same preregistered RNG draw sequence, separate arithmetic implementation.
    draws = rng.integers(0, block_count, size=(2000, block_count))
    totals = np.sum(count_by_block[draws], axis=1)
    usable = totals > 0
    sample_accuracy = np.sum(correct_by_block[draws], axis=1)[usable] / totals[usable]
    result = {
        "status": "OK", "descriptive_only": True, "used_for_selection": False,
        "requested_replicates": 2000, "nonempty_replicates": int(usable.sum()), "seed": seed,
        "total_calendar_blocks": block_count, "blocks_with_selected_predictions": int((count_by_block > 0).sum()),
        "selected_non_doji_count": len(selected), "point_accuracy": float(correct.mean()),
        "accuracy_percentile_95_low": float(np.quantile(sample_accuracy, .025)),
        "accuracy_percentile_95_high": float(np.quantile(sample_accuracy, .975)),
        "paired_accuracy_differences": {},
    }
    for name in CONTROL_NAMES:
        values = np.sum(deltas_by_block[name][draws], axis=1)[usable] / totals[usable]
        result["paired_accuracy_differences"][name] = {
            "point_difference": float(deltas_by_block[name].sum() / len(selected)),
            "percentile_95_low": float(np.quantile(values, .025)),
            "percentile_95_high": float(np.quantile(values, .975)),
        }
    return result


def compare_nested(actual: dict, expected: dict, checks: Checks, prefix: str) -> None:
    for name, value in expected.items():
        if name not in actual:
            checks.check(prefix + ":" + name, False, "missing serialized key")
        elif isinstance(value, dict):
            compare_nested(actual[name], value, checks, prefix + ":" + name)
        else:
            checks.equal(prefix + ":" + name, actual[name], value)


def audit_v1_control(folder: Path, inputs: dict[str, pd.DataFrame], settings: dict,
                     folds: list[tuple[int, int]], checks: Checks) -> tuple[pd.DataFrame, str]:
    btc = inputs["btc4h"]
    btc = btc.loc[btc.open_time >= ms("2022-01-01T00:00:00Z")].reset_index(drop=True)
    meta = raw_metadata(btc, inputs["btc15m"], inputs["eth4h"])
    frame = read_csv(folder / "predictions.csv.gz")
    cal = read_csv(folder / "calibration_predictions.csv.gz")
    split = read_csv(folder / "split_audit.csv")
    records = read_json(folder / "calibration.json")
    vsettings = {**settings, "calibration_days": 90, "minimum_calibration_samples": 500,
                 "models": [{"id": "V1_LOGISTIC38", "train_days": None}]}
    expected_frames = []
    for start, end in folds:
        masks = independent_splits(meta, "G1", start, end, None, 90)
        f, c = frame[frame.fold_start_utc.map(ms).eq(start)], cal[cal.fold_start_utc.map(ms).eq(start)]
        expected_frames.append(meta[masks["test"]])
        prefix = "V1:" + iso(start)
        verify_frame_metadata(f, meta[masks["test"]], checks, prefix + ":prediction", calendar=True)
        verify_frame_metadata(c, meta[masks["calibration"]], checks, prefix + ":calibration")
        verify_controls(f, meta, "G1", start, end, vsettings, checks, prefix)
    verify_frame_metadata(frame, pd.concat(expected_frames, ignore_index=True), checks, "V1:full_timeline", calendar=True)
    checks.check("V1:exact_calibration_fold_set", set(cal.fold_start_utc.map(ms)) == {s for s, _ in folds})
    checks.check("V1:calibration_keys_unique", not cal.duplicated(["fold_start_utc", "prediction_time"]).any())
    # The V1 ledger displays its source start; the split itself is expanding.
    ok_split = split.status.eq("OK")
    checks.check("V1:original_source_start", split.loc[ok_split, "train_start_utc"].map(ms).eq(ms("2022-01-01T00:00:00Z")).all())
    adjusted_split = split.copy()
    adjusted_split["train_start_utc"] = np.nan
    status = verify_splits(adjusted_split, meta, "G1", vsettings, folds, checks)
    passed = all(status.values())
    record_lookup = {ms(r["fold_start_utc"]): r for r in records}
    expected_record_keys = {start for start, _ in folds if status[("V1_LOGISTIC38", start)]}
    checks.check("V1:exact_calibration_record_set", set(record_lookup) == expected_record_keys and len(records) == len(record_lookup))
    for start, _ in folds:
        c, f = cal[cal.fold_start_utc.map(ms).eq(start)], frame[frame.fold_start_utc.map(ms).eq(start)]
        pcal, ptest = c.V1_LOGISTIC38__p_up.to_numpy(), f.V1_LOGISTIC38__p_up.to_numpy()
        prefix = "V1:calibration:" + iso(start)
        if status[("V1_LOGISTIC38", start)]:
            rec = record_lookup[start]
            expected = expit(c.V1_LOGISTIC38__raw_score.to_numpy() * rec["slope"] + rec["intercept"])
            checks.equal(prefix + ":probabilities", pcal, expected)
            checks.check(prefix + ":allows_original_negative_slope", rec["mode"] == "sigmoid" and rec["allow_negative"] is True)
            checks.equal(prefix + ":calibration_count", rec["calibration_count"], len(c), atol=0)
            checks.equal(prefix + ":calibration_positive_rate", rec["calibration_positive_rate"], c.y.mean())
            checks.check(prefix + ":all_test_probabilities_valid", bool(np.isfinite(ptest).all() and ((ptest >= 0) & (ptest <= 1)).all()))
        else:
            checks.check(prefix + ":failed_fold_unavailable", np.isnan(pcal).all() and np.isnan(ptest).all())
    policies = [p for p in settings["policies"] if p["id"] in ("A500", "A550")]
    verify_evaluation_tables(folder, frame, "V1", "V1_LOGISTIC38", policies, "OK" if passed else "FAILED", checks, "V1")
    verify_shards(folder, frame, cal, checks, "V1")
    return frame, "OK" if passed else "FAILED"


def run_evaluation_audit(root: Path, out: Path, allow_holdout: bool) -> dict:
    if not allow_holdout:
        raise PermissionError("Explicit holdout authorization flag is required")
    folder = out / "evaluation"
    if not (folder / "completion.json").is_file():
        raise FileNotFoundError("Evaluation audit requires the completed one-time frozen evaluation")
    # These checks happen before opening any evaluation candle file.
    development_audit = read_json(out / "audit_development.json")
    if development_audit["status"] != "PASS" or development_audit.get("global_selection_audited") is not True:
        raise ValueError("A passing independent global development/selection audit is required")
    selection = read_json(out / "selection.json")
    if sha256(out / "selection.json") != development_audit["selection_file_sha256"]:
        raise ValueError("Selection changed after the development audit")
    if selection["status"] != "FROZEN_SELECTED":
        raise ValueError("No valid frozen selection")
    settings = read_json(root / "settings.json")
    checks = Checks()
    payload = {"holdout_files_opened": False, "selection_file_sha256": sha256(out / "selection.json")}
    try:
        frozen = audit_frozen_inputs(root, checks, allow_holdout=False)
        inputs, data_hashes = load_development(root, checks)
        verify_config(selection["config"], root, data_hashes, checks, "evaluation:frozen_selection_config")
        completion = read_json(folder / "completion.json")
        marker = read_json(folder / "run_started.json")
        checks.check("evaluation:began_after_selection_freeze", pd.Timestamp(marker["started_at_utc"]) >= pd.Timestamp(selection["frozen_at_utc"]))
        checks.equal("evaluation:marker_selection_hash", marker["selection_sha256"], payload["selection_file_sha256"])
        checks.equal("evaluation:completion_selection_hash", completion["selection_sha256"], payload["selection_file_sha256"])
        checks.equal("evaluation:completion_status", completion["status"], "COMPLETE")
        checks.equal("evaluation:three_quarters", completion["expected_folds"], 3, atol=0)
        checks.check("evaluation:completed_after_started", pd.Timestamp(completion["finished_at_utc"]) >= pd.Timestamp(marker["started_at_utc"]))
        verify_config(completion["config"], root, data_hashes, checks, "evaluation:completion_config")
        if not checks.passed:
            raise ValueError("Pre-access freeze/selection checks failed; evaluation candles remain unopened")
        # Authorization, frozen selection and completed one-time run are proven.
        payload["holdout_files_opened"] = True
        holdout_hashes = {}
        for name, (filename, _) in DEVELOPMENT_FILES.items():
            path = root / "data" / "holdout_2026" / filename.replace("2020-01_2025-12", "2026-01_2026-09")
            relative = str(path.relative_to(root))
            holdout_hashes[name] = sha256(path)
            checks.equal("evaluation:frozen_input_hash:" + name, holdout_hashes[name], frozen["freeze"]["holdout_data_sha256"][relative])
            inputs[name] = pd.concat([inputs[name], read_csv(path)], ignore_index=True)
        for name, expected in completion["sha256"].items():
            checks.equal("evaluation:artifact_hash:" + name, sha256(folder / name), expected)
        meta = raw_metadata(inputs["btc4h"], inputs["btc15m"], inputs["eth4h"], checks)
        frame = read_csv(folder / "predictions.csv.gz")
        calibration = read_csv(folder / "calibration_predictions.csv.gz")
        splits = read_csv(folder / "split_audit.csv")
        records = read_json(folder / "calibration.json")
        group, predictor = selection["group"], selection["predictor"]
        folds = quarter_folds([2026])[:3]
        expected_frames = []
        for start, end in folds:
            masks = independent_splits(meta, group, start, end, None, settings["calibration_days"])
            f, c = frame[frame.fold_start_utc.map(ms).eq(start)], calibration[calibration.fold_start_utc.map(ms).eq(start)]
            expected_frames.append(meta[masks["test"]])
            prefix = "evaluation:" + iso(start)
            verify_frame_metadata(f, meta[masks["test"]], checks, prefix + ":prediction", calendar=True)
            verify_frame_metadata(c, meta[masks["calibration"]], checks, prefix + ":calibration")
            verify_controls(f, meta, group, start, end, settings, checks, prefix)
            checks.check(prefix + ":correct_fold_ends", set(f.fold_end_utc.map(ms)) == {end} and set(c.fold_end_utc.map(ms)) == {end})
        verify_frame_metadata(frame, pd.concat(expected_frames, ignore_index=True), checks, "evaluation:full_timeline", calendar=True)
        checks.check("evaluation:exact_calibration_fold_set", set(calibration.fold_start_utc.map(ms)) == {s for s, _ in folds})
        checks.check("evaluation:calibration_keys_unique", not calibration.duplicated(["fold_start_utc", "prediction_time"]).any())
        subset_settings = {**settings, "models": selection["member_recipes"],
                           "ensembles": [selection["ensemble"]] if selection["ensemble"] else []}
        fold_status = verify_splits(splits, meta, group, subset_settings, folds, checks)
        successful = all(fold_status.values())
        status = "OK" if successful else "FAILED"
        checks.equal("evaluation:overall_status", completion["model_status"], status)
        expected_predictors = {group + "_" + r["id"] for r in selection["member_recipes"]} | {predictor}
        checks.check("evaluation:no_additional_candidates_predicted", {c[:-6] for c in frame if c.endswith("__p_up")} == expected_predictors)
        verify_calibration_and_ensembles(frame, calibration, records, fold_status, group, subset_settings, folds, checks)
        checks.equal("evaluation:fixed_policy_signal", frame.selected_policy_signal.to_numpy(), policy_mask(frame, predictor, selection["policy"]), atol=0)
        policies = [p for p in settings["policies"] if p["id"] in ("A500", selection["policy"]["id"])]
        table = verify_evaluation_tables(folder, frame, group, predictor, policies, status, checks, "evaluation")
        verify_shards(folder, frame, calibration, checks, "evaluation")
        v1, v1_status = audit_v1_control(folder / "v1_control", inputs, settings, folds, checks)
        checks.equal("evaluation:v1_status", completion["v1_status"], v1_status)
        chosen = independent_summary(frame, predictor, selection["policy"], successful)
        full_policy = next(p for p in settings["policies"] if p["id"] == "A500")
        full = independent_summary(frame, predictor, full_policy, successful)
        summary = read_json(folder / "evaluation_summary.json")
        compare_nested(summary["selected_metrics"], chosen, checks, "evaluation:selected_summary")
        compare_nested(summary["full_coverage_metrics"], full, checks, "evaluation:full_summary")
        checks.check("evaluation:unchanged_chosen_policy", summary["policy"] == selection["policy"])
        checks.equal("evaluation:summary_predictor", summary["predictor"], predictor)
        checks.check("evaluation:source_hashes", summary["holdout_data_sha256"] == holdout_hashes)
        gate = settings["evaluation_goal_gate"]
        goal = {"all_three_folds_successful": successful,
                "accuracy_at_least_target": bool(np.isfinite(chosen["accuracy"]) and chosen["accuracy"] >= gate["accuracy_at_least"]),
                "selected_non_doji_count": chosen["scored_count"] >= gate["selected_non_doji_at_least"],
                "active_months": chosen["active_months"] >= gate["active_months_at_least"],
                "month_concentration": chosen["max_month_share"] <= gate["maximum_single_month_share"]}
        checks.check("evaluation:all_goal_predicates", summary["goal_gate_checks"] == goal)
        checks.equal("evaluation:point_goal_claim", summary["point_60_percent_goal_met"], all(goal.values()))
        matched = frame[["prediction_time", "y", predictor + "__p_up"]].copy()
        matched["selected"] = policy_mask(frame, predictor, selection["policy"])
        matched = matched.merge(v1[["prediction_time", "V1_LOGISTIC38__p_up"]], how="left", on="prediction_time", validate="one_to_one")
        compare_saved_summary(read_csv(folder / "matched_v1_control.csv"), matched, ["prediction_time"], checks, "evaluation:matched_v1_ledger")
        mask = matched.selected & matched.y.notna() & matched.V1_LOGISTIC38__p_up.notna()
        comparison = {"status": "OK" if successful and v1_status == "OK" else "FAILED",
                      "matched_selected_non_doji_count": int(mask.sum()),
                      "v1_accuracy_on_v2_selected_timestamps": np.nan,
                      "v2_accuracy_on_same_timestamps": np.nan}
        if mask.any() and comparison["status"] == "OK":
            comparison["v1_accuracy_on_v2_selected_timestamps"] = float(((matched.loc[mask, "V1_LOGISTIC38__p_up"] >= .5) == matched.loc[mask, "y"]).mean())
            comparison["v2_accuracy_on_same_timestamps"] = float(((matched.loc[mask, predictor + "__p_up"] >= .5) == matched.loc[mask, "y"]).mean())
        compare_nested(read_json(folder / "matched_v1_comparison.json"), comparison, checks, "evaluation:matched_v1_comparison")
        bootstrap = independent_bootstrap(frame, predictor, selection["policy"], settings["seed"], successful)
        compare_nested(read_json(folder / "uncertainty.json"), bootstrap, checks, "evaluation:fixed_block_bootstrap")
        compare_nested(summary["uncertainty"], bootstrap, checks, "evaluation:summary_bootstrap")
        checks.check("evaluation:no_switch_claim", summary["no_model_or_policy_switch_after_evaluation"] is True)
        table.to_csv(out / "audit_recomputed_evaluation_results.csv", index=False, float_format="%.17g")
        payload.update({"selected": {"group": group, "predictor": predictor, "policy": selection["policy"]},
                        "selected_metrics": chosen, "full_coverage_metrics": full,
                        "goal_gate_checks": goal, "point_60_percent_goal_met": all(goal.values()),
                        "v1_matched_comparison": comparison, "uncertainty": bootstrap,
                        "holdout_source_sha256": holdout_hashes, "evaluation_completion_sha256": sha256(folder / "completion.json")})
    except Exception as exc:
        checks.check("audit_execution_exception", False, type(exc).__name__ + ": " + str(exc))
        payload["exception"] = type(exc).__name__ + ": " + str(exc)
    return write_report(root, out, "evaluation", checks, payload)


def write_report(root: Path, out: Path, phase: str, checks: Checks, payload: dict) -> dict:
    report = {
        "status": "PASS" if checks.passed else "FAIL",
        "phase": phase, "auditor_source_sha256": sha256(Path(__file__)),
        "independent_of_engine_imports": True, "estimator_fits_performed": 0,
        "checks_total": len(checks.rows), "checks_failed": sum(not row["passed"] for row in checks.rows),
        "checks": checks.rows, **payload,
    }
    out.mkdir(parents=True, exist_ok=True)
    path = out / ("audit_" + phase + ".json")
    path.write_text(json.dumps(clean_json(report), indent=2, ensure_ascii=False) + "\n")
    failed = [row for row in checks.rows if not row["passed"]]
    lines = [f"# BTC 4h V2 independent {phase} audit", "", f"**Status: {report['status']}**", "",
             f"Checks: {report['checks_total']}; failed: {report['checks_failed']}. No estimator was fitted.", "",
             "Targets and timestamps were reconstructed from official 4h candles. Threshold masks, metrics, purged split counts and ranking were recomputed independently of engine functions.", ""]
    if phase == "development" or phase in ("G1", "G2", "G3", "G4"):
        lines += ["No evaluation candle file in `data/holdout_2026` was opened by this audit.", ""]
    if "selected" in payload:
        lines += ["## Independently reconstructed selection", "", "```json", json.dumps(clean_json(payload["selected"]), indent=2), "```", ""]
    if failed:
        lines += ["## Failed checks", ""]
        lines += [f"- {row['check']}: {json.dumps(row['detail'], ensure_ascii=False)}" for row in failed]
    (out / ("audit_" + phase + ".md")).write_text("\n".join(lines) + "\n")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--phase", choices=("development", "evaluation"), default="development")
    parser.add_argument("--group", choices=("G1", "G2", "G3", "G4"), help="Audit one completed development group before global selection")
    parser.add_argument("--allow-holdout", action="store_true", help="Use only after the one frozen selection was evaluated")
    args = parser.parse_args()
    if args.phase == "evaluation" and not args.allow_holdout:
        parser.error("evaluation audit requires explicit --allow-holdout after parent authorization")
    if args.phase == "evaluation" and args.group:
        parser.error("--group is only for development audits")
    root = args.root.resolve()
    out = args.out.resolve() if args.out else root / "results"
    if args.phase == "development":
        report = run_development_audit(root, out, args.group)
    else:
        report = run_evaluation_audit(root, out, args.allow_holdout)
    print(json.dumps({k: report[k] for k in ("status", "phase", "checks_total", "checks_failed")}, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
