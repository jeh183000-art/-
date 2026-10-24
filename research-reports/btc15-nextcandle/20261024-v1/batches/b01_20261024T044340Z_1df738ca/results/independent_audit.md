# Independent prediction audit

**PASS — 3261 checks; 0 failures.**

Auditor does not import model.py, sklearn metrics, or serialized model objects. It recomputes targets, chronological eligibility, metric arithmetic and split counts from canonical raw data.

Selected model: `hist_gradient_boosting`. Numerical tolerance: `1e-09`.

## Paired daily-block bootstrap

Accuracy differences are percentage points; intervals resample whole UTC days.

| Baseline | Difference (pp) | 95% interval (pp) |
|---|---:|---:|
| historical_bullish_rate | 2.4697 | [1.7815, 3.1325] |
| opposite_color_to_current | 0.5825 | [0.0313, 1.1367] |

Post-run uncertainty diagnostic only; no tuning or model selection. Whole UTC days are resampled with replacement, retaining paired model/baseline errors. Independence between days is a heuristic; this does not account for multi-day dependence, regime shifts, all researcher degrees of freedom, or live execution costs. Percentile intervals are not a guarantee of future accuracy.

## Scope and limits

Validates files and timestamp rules; flags alone cannot independently establish real-world experiment chronology or verify which rows were passed into a fitting process. Predictions are historical, and this audit does not demonstrate trading profitability.
