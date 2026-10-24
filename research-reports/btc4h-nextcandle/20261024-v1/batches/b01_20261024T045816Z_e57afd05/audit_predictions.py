#!/usr/bin/env python3
"""Independent audit of 4-hour forecast ledgers. Does not import model.py or refit models.

Run only after both phases finish:
  python audit_predictions.py --out results
Paired day-block bootstrap is a post-run diagnostic, never a selection rule.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd
from scipy.stats import rankdata

BAR = 14_400_000
SEED = 20261024
TOLERANCE = 1e-9


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def native(value):
    if isinstance(value, dict):
        return {str(k): native(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [native(v) for v in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return float(value) if np.isfinite(value) else None
    if isinstance(value, (np.bool_,)):
        return bool(value)
    return value


def ms(value) -> int:
    return int(pd.Timestamp(value).value // 1_000_000)


def summarize(y: np.ndarray, probabilities: np.ndarray, threshold=0.5) -> dict:
    """Independent NumPy arithmetic; no sklearn metrics/model helpers."""
    p = np.asarray(probabilities, dtype=float)
    y = np.asarray(y, dtype=float)
    valid = np.isfinite(y)
    selected = np.maximum(p, 1-p) >= threshold
    chosen = valid & selected
    truth = y[chosen]
    q = p[chosen]
    prediction = q >= .5
    out = {
        "forecast_count": len(y), "non_doji_count": valid.sum(),
        "doji_count": (~valid).sum(), "selected_count": selected.sum(),
        "scored_count": chosen.sum(), "coverage": selected.mean(),
        "scored_coverage": chosen.sum()/valid.sum() if valid.any() else np.nan,
        "predicted_up_count": prediction.sum(), "predicted_down_count": (~prediction).sum(),
    }
    keys = ("accuracy", "balanced_accuracy", "bullish_precision", "bearish_precision", "log_loss", "brier", "roc_auc")
    if len(truth) == 0:
        return dict(out, **{k: np.nan for k in keys})
    positive = truth == 1
    negative = truth == 0
    clipped = np.clip(q, 1e-6, 1-1e-6)
    ranks = rankdata(q, method="average")
    out.update({
        "accuracy": (prediction == positive).mean(),
        "balanced_accuracy": ((prediction[positive]).mean() + (~prediction[negative]).mean())/2 if positive.any() and negative.any() else np.nan,
        "bullish_precision": truth[prediction].mean() if prediction.any() else np.nan,
        "bearish_precision": (1-truth[~prediction]).mean() if (~prediction).any() else np.nan,
        "log_loss": -(truth*np.log(clipped)+(1-truth)*np.log1p(-clipped)).mean(),
        "brier": ((q-truth)**2).mean(),
        "roc_auc": (ranks[positive].sum()-positive.sum()*(positive.sum()+1)/2)/(positive.sum()*negative.sum()) if positive.any() and negative.any() else np.nan,
    })
    return out


def raw_metadata(bars: pd.DataFrame) -> pd.DataFrame:
    """Derive label, availability and feature-validity without model functions."""
    rows = np.arange(len(bars))
    boundaries = np.r_[True, np.diff(bars.open_time.to_numpy()) != BAR]
    segment_start = np.maximum.accumulate(np.where(boundaries, rows, 0))
    eligible = rows - segment_start >= 96
    # All price-based features are finite after warmup for audited positive OHLC.
    # Explicitly check every volume/quote/trade denominator in the fixed recipe.
    for window in (1, 4, 16, 96):
        eligible &= bars.volume.rolling(window).sum().gt(0).to_numpy()
    for column in ("quote_volume", "trades"):
        eligible &= bars[column].rolling(16).sum().gt(0).to_numpy()
    target = bars.iloc[1:].reset_index(drop=True)
    current = bars.iloc[:-1].reset_index(drop=True)
    adjacent = target.open_time.eq(current.open_time+BAR)
    color = np.sign(target.close.to_numpy()-target.open.to_numpy())
    return pd.DataFrame({
        "current_open_time": current.open_time,
        "target_open_time": target.open_time,
        "prediction_time": current.close_time+1,
        "label_end_time": target.close_time+1,
        "current_color": np.sign(current.close.to_numpy()-current.open.to_numpy()),
        "target_color": color,
        "y": np.where(color == 0, np.nan, (color+1)/2),
        "eligible": eligible[:-1] & adjacent.to_numpy(),
    })


class Auditor:
    def __init__(self):
        self.checks = []

    def check(self, label, passed, details=None):
        self.checks.append({"check": label, "passed": bool(passed), "details": details})

    def close(self, label, actual, expected):
        if pd.isna(actual) and pd.isna(expected):
            good = True
        elif pd.isna(actual) or pd.isna(expected):
            good = False
        else:
            good = abs(float(actual)-float(expected)) <= TOLERANCE
        self.check(label, good, {"actual": actual, "expected": expected} if not good else None)


def compare_scores(audit, label, row, truth, p, threshold):
    recomputed = summarize(truth, p, threshold)
    for field, expected in recomputed.items():
        audit.close(f"{label}/{field}", row[field], expected)
    return recomputed


def audit_phase(audit, root, phase, year, raw_meta, winner):
    folder = root / phase
    ledger = pd.read_csv(folder / "predictions.csv.gz")
    summary = pd.read_csv(folder / "results.csv")
    thresholds = pd.read_csv(folder / "thresholds.csv")
    monthly = pd.read_csv(folder / "monthly_metrics.csv")
    start, end = ms(f"{year}-01-01T00:00:00Z"), ms(f"{year+1}-01-01T00:00:00Z")
    expected = raw_meta[raw_meta.eligible & raw_meta.prediction_time.between(start, end-1)]
    audit.check(f"{phase}/unique_timestamps", not ledger.prediction_time.duplicated().any())
    audit.check(f"{phase}/sorted_timestamps", ledger.prediction_time.is_monotonic_increasing)
    audit.check(f"{phase}/expected_timestamp_set", np.array_equal(ledger.prediction_time, expected.prediction_time), {"actual": len(ledger), "expected": len(expected), "calendar_bars": int((end-start)/BAR)})
    audit.check(f"{phase}/strict_4h_grid", (ledger.prediction_time % BAR == 0).all())
    audit.check(f"{phase}/expected_year_only", ledger.prediction_time.between(start, end-1).all())
    audit.check(f"{phase}/zero_2026_predictions", (ledger.prediction_time < ms("2026-01-01T00:00:00Z")).all())
    aligned = raw_meta.set_index("prediction_time").reindex(ledger.prediction_time)
    for field in ("current_open_time", "target_open_time", "label_end_time", "current_color", "target_color", "y"):
        audit.check(f"{phase}/raw_alignment/{field}", np.array_equal(ledger[field].to_numpy(), aligned[field].to_numpy(), equal_nan=True))
    audit.check(f"{phase}/prediction_at_target_open", ledger.prediction_time.eq(ledger.target_open_time).all())
    audit.check(f"{phase}/one_bar_horizon", ledger.label_end_time.eq(ledger.prediction_time+BAR).all())
    for field, timestamp in (("prediction_utc", "prediction_time"), ("label_end_utc", "label_end_time")):
        converted = pd.to_datetime(ledger[field], utc=True).astype("int64")//1_000_000
        audit.check(f"{phase}/{field}", np.array_equal(converted, ledger[timestamp]))
    names = [c.removesuffix("__p_up") for c in ledger.columns if c.endswith("__p_up")]
    required_models = {"logistic", "hist_gradient_boosting"} if phase == "development" else {winner}
    required_models |= {"historical_bullish_rate", "coinflip_0.5", "same_color_as_current", "opposite_color_to_current"}
    audit.check(f"{phase}/exact_model_set", set(names) == required_models)
    audit.check(f"{phase}/summary_model_set", set(summary.model) == required_models and not summary.model.duplicated().any())
    audit.check(f"{phase}/threshold_rows", len(thresholds) == len(names)*3)
    truth = ledger.y.to_numpy()
    recalc = []
    month_labels = pd.to_datetime(ledger.prediction_time, unit="ms", utc=True).dt.strftime("%Y-%m")
    for name in names:
        p = ledger[name+"__p_up"].to_numpy()
        audit.check(f"{phase}/{name}/valid_probabilities", np.isfinite(p).all() and ((p >= 0) & (p <= 1)).all())
        audit.check(f"{phase}/{name}/direction", np.array_equal(ledger[name+"__direction"].to_numpy(), np.where(p >= .5, "UP", "DOWN")))
        row = summary[summary.model.eq(name)].iloc[0]
        recalculated = compare_scores(audit, f"{phase}/{name}/summary", row, truth, p, .5)
        recalc.append({"phase": phase, "model": name, **recalculated})
        for threshold in (.50, .55, .60):
            rows = thresholds[thresholds.model.eq(name) & thresholds.threshold.eq(threshold)]
            audit.check(f"{phase}/{name}/threshold_{threshold}/unique", len(rows) == 1)
            if len(rows) == 1:
                compare_scores(audit, f"{phase}/{name}/threshold_{threshold}", rows.iloc[0], truth, p, threshold)
        for month in month_labels.unique():
            mask = month_labels.eq(month).to_numpy()
            rows = monthly[monthly.model.eq(name) & monthly.month.eq(month)]
            audit.check(f"{phase}/{name}/{month}/unique", len(rows) == 1)
            if len(rows) == 1:
                compare_scores(audit, f"{phase}/{name}/{month}", rows.iloc[0], truth[mask], p[mask], .5)
    # Check every split against raw-derived sample masks, not model audit flags.
    split_rows = pd.read_csv(folder / "split_audit.csv")
    audit.check(f"{phase}/split_row_count", len(split_rows) == 4*(2 if phase == "development" else 1))
    labeled = raw_meta.eligible & raw_meta.y.notna()
    for _, split in split_rows.iterrows():
        test_start, test_end = ms(split.test_start_utc), ms(split.test_end_utc)
        calibration_start = test_start-90*24*60*60*1000
        fit = labeled & (raw_meta.label_end_time < calibration_start)
        calibration = labeled & (raw_meta.prediction_time >= calibration_start) & (raw_meta.label_end_time < test_start)
        test = raw_meta.eligible & raw_meta.prediction_time.between(test_start, test_end-1)
        prior = labeled & (raw_meta.label_end_time < test_start)
        label = f"{phase}/{split.model}/{split.test_start_utc}/split"
        audit.check(label+"/calibration_90days", ms(split.calibration_start_utc) == calibration_start)
        audit.check(label+"/strict_fit_label_cutoff", ms(split.fit_last_label_end_utc) < calibration_start)
        audit.check(label+"/strict_calibration_label_cutoff", ms(split.calibration_last_label_end_utc) < test_start)
        audit.check(label+"/disjoint", not (fit & calibration).any())
        for field, expected_n in (("fit_samples", fit.sum()), ("calibration_samples", calibration.sum()), ("test_forecasts", test.sum()), ("test_doji", raw_meta.loc[test, "target_color"].eq(0).sum())):
            audit.close(label+"/"+field, split[field], expected_n)
        for field, expected_t in (("fit_first_prediction_utc", raw_meta.loc[fit, "prediction_time"].min()), ("fit_last_label_end_utc", raw_meta.loc[fit, "label_end_time"].max()), ("calibration_first_prediction_utc", raw_meta.loc[calibration, "prediction_time"].min()), ("calibration_last_label_end_utc", raw_meta.loc[calibration, "label_end_time"].max()), ("test_first_prediction_utc", raw_meta.loc[test, "prediction_time"].min())):
            audit.check(label+"/"+field, ms(split[field]) == expected_t)
        prior_rate = raw_meta.loc[prior, "y"].mean()
        audit.close(label+"/historical_bullish_rate", split.prior_bullish_rate, prior_rate)
        forecast_mask = ledger.prediction_time.between(test_start, test_end-1)
        audit.check(label+"/baseline_probability", np.allclose(ledger.loc[forecast_mask, "historical_bullish_rate__p_up"], prior_rate, rtol=0, atol=TOLERANCE))
        audit.check(label+"/fold_labels", ledger.loc[forecast_mask, "fold_start_utc"].eq(split.test_start_utc).all() and ledger.loc[forecast_mask, "fold_end_utc"].eq(split.test_end_utc).all())
    historical_up = ledger.historical_bullish_rate__p_up >= .5
    same = np.where(ledger.current_color == 0, historical_up, ledger.current_color > 0).astype(float)
    opposite = np.where(ledger.current_color == 0, historical_up, ledger.current_color < 0).astype(float)
    audit.check(f"{phase}/same_color_baseline", np.array_equal(same, ledger.same_color_as_current__p_up))
    audit.check(f"{phase}/opposite_color_baseline", np.array_equal(opposite, ledger.opposite_color_to_current__p_up))
    audit.check(f"{phase}/constant_05_baseline", ledger["coinflip_0.5__p_up"].eq(.5).all())
    shards = pd.concat([pd.read_csv(p) for p in sorted((folder/"predictions_monthly").glob("*.csv"))], ignore_index=True)
    audit.check(f"{phase}/monthly_shards_equal_ledger", shards.equals(ledger))
    return ledger, recalc


def bootstrap(ledger, winner):
    """Paired iid daily-block resampling; does not claim iid individual bars."""
    scored = ledger[ledger.y.notna()].copy()
    days = (scored.prediction_time.to_numpy()//86_400_000).astype(int)
    truth = scored.y.to_numpy()
    selected_correct = (scored[winner+"__p_up"].to_numpy() >= .5) == truth
    result = []
    rng = np.random.default_rng(SEED)
    for baseline in ("historical_bullish_rate", "opposite_color_to_current"):
        baseline_correct = (scored[baseline+"__p_up"].to_numpy() >= .5) == truth
        deltas = selected_correct.astype(int)-baseline_correct.astype(int)
        daily = pd.DataFrame({"day": days, "delta": deltas}).groupby("day").agg(delta_sum=("delta", "sum"), count=("delta", "size"))
        blocks = daily.to_numpy()
        indices = rng.integers(0, len(blocks), size=(1000, len(blocks)))
        sampled = blocks[indices]
        values = sampled[:, :, 0].sum(axis=1)/sampled[:, :, 1].sum(axis=1)
        lo, hi = np.quantile(values, [.025, .975])
        result.append({"selected_model": winner, "baseline": baseline, "scored_bars": len(scored), "day_blocks": len(blocks), "replicates": 1000, "seed": SEED, "accuracy_difference": deltas.mean(), "ci95_lower": lo, "ci95_upper": hi, "ci_excludes_zero": bool(lo > 0 or hi < 0)})
    return result


def main():
    here = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=here/"results")
    parser.add_argument("--data", type=Path, default=here/"data/BTCUSDT_4h_2022-01_2025-12.csv.gz")
    args = parser.parse_args()
    root = args.out
    audit = Auditor()
    selection = json.loads((root/"selection.json").read_text())
    prereg = json.loads((here/"preregistration.json").read_text())
    settings = json.loads((here/"settings.json").read_text())
    environment = json.loads((root/"environment.json").read_text())
    winner = selection["selected_model"]
    hashes = {
        "data_sha256": digest(args.data), "model_code_sha256": digest(here/"model.py"),
        "protocol_sha256": digest(here/"settings.json"),
        "development_prediction_sha256": digest(root/"development/predictions.csv.gz"),
        "development_result_sha256": digest(root/"development/results.csv"),
    }
    for field, expected in hashes.items():
        audit.check("selection/hash/"+field, selection[field] == expected)
        if field in environment:
            audit.check("environment/hash/"+field, environment[field] == expected)
    audit.check("preregistration/settings_hash", prereg["settings_sha256"] == hashes["protocol_sha256"])
    audit.check("selection/frozen_flag", selection["frozen_before_evaluation"] is True)
    audit.check("selection/preregistered_candidates", selection["models"] == list(settings["models"]))
    audit.check("selection/seed", selection["seed"] == SEED)
    # A tiny arithmetic sentinel catches a broken independent scoring helper.
    sentinel = summarize(np.array([0., 1., 0., 1., np.nan]), np.array([.1, .9, .8, .2, .9]))
    audit.close("audit_metric_self_check/accuracy", sentinel["accuracy"], .5)
    audit.close("audit_metric_self_check/brier", sentinel["brier"], .325)
    audit.close("audit_metric_self_check/dojis", sentinel["doji_count"], 1)
    bars = pd.read_csv(args.data)
    audit.check("raw/unique_times", not bars.open_time.duplicated().any())
    audit.check("raw/strict_4h", np.all(np.diff(bars.open_time) == BAR))
    audit.check("raw/utc_4h_boundaries", np.all(bars.open_time % BAR == 0))
    audit.check("raw/4h_close_timestamps", np.all(bars.close_time == bars.open_time + BAR - 1))
    audit.check("protocol/4h_interval", settings["interval_minutes"] == 240)
    raw_meta = raw_metadata(bars)
    _, development_scores = audit_phase(audit, root, "development", 2024, raw_meta, winner)
    evaluation, evaluation_scores = audit_phase(audit, root, "evaluation", 2025, raw_meta, winner)
    candidates = [x for x in development_scores if x["model"] in settings["models"]]
    independent_winner = sorted(candidates, key=lambda x: (x["log_loss"], x["model"]))[0]["model"]
    audit.check("selection/minimum_2024_log_loss", winner == independent_winner, {"selected": winner, "recomputed": independent_winner})
    diagnostics = bootstrap(evaluation, winner)
    failures = [x for x in audit.checks if not x["passed"]]
    report = {
        "status": "PASS" if not failures else "FAIL", "check_count": len(audit.checks), "failed_count": len(failures),
        "independence": "Auditor does not import model.py, sklearn metrics, or serialized model objects. It recomputes targets, chronological eligibility, metric arithmetic and split counts from canonical raw data.",
        "tolerance": TOLERANCE, "selected_model": winner, "hashes": hashes,
        "auditor_sha256": digest(Path(__file__)), "failures": failures, "checks": audit.checks,
        "paired_day_block_bootstrap": diagnostics,
        "bootstrap_limits": "Post-run uncertainty diagnostic only; no tuning or model selection. Whole UTC days are resampled with replacement, retaining paired model/baseline errors. Independence between days is a heuristic; this does not account for multi-day dependence, regime shifts, all researcher degrees of freedom, or live execution costs. Percentile intervals are not a guarantee of future accuracy.",
        "limits": "Validates files and timestamp rules; flags alone cannot independently establish real-world experiment chronology or verify which rows were passed into a fitting process. Predictions are historical, and this audit does not demonstrate trading profitability.",
    }
    (root/"independent_audit.json").write_text(json.dumps(native(report), ensure_ascii=False, indent=2, allow_nan=False)+"\n")
    pd.DataFrame(development_scores+evaluation_scores).to_csv(root/"independent_audit.metrics.csv", index=False)
    pd.DataFrame(diagnostics).to_csv(root/"independent_audit.bootstrap.csv", index=False)
    lines = ["# Independent prediction audit", "", f"**{report['status']} — {len(audit.checks)} checks; {len(failures)} failures.**", "", report["independence"], "", f"Selected model: `{winner}`. Numerical tolerance: `{TOLERANCE}`.", "", "## Paired daily-block bootstrap", "", "Accuracy differences are percentage points; intervals resample whole UTC days.", "", "| Baseline | Difference (pp) | 95% interval (pp) |", "|---|---:|---:|"]
    for row in diagnostics:
        lines.append(f"| {row['baseline']} | {100*row['accuracy_difference']:.4f} | [{100*row['ci95_lower']:.4f}, {100*row['ci95_upper']:.4f}] |")
    lines.extend(["", report["bootstrap_limits"], "", "## Scope and limits", "", report["limits"]])
    if failures:
        lines.extend(["", "## Failures", "", *[f"- {x['check']}: {x['details']}" for x in failures]])
    (root/"independent_audit.md").write_text("\n".join(lines)+"\n")
    print(json.dumps(native({"status": report["status"], "checks": len(audit.checks), "failures": failures, "bootstrap": diagnostics}), indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
