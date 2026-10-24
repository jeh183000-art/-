# BTC 4h V2 independent development audit

**Status: PASS**

Checks: 18764; failed: 0. No estimator was fitted.

Targets and timestamps were reconstructed from official 4h candles. Threshold masks, metrics, purged split counts and ranking were recomputed independently of engine functions.

No evaluation candle file in `data/holdout_2026` was opened by this audit.

## Independently reconstructed selection

```json
{
  "group": "G1",
  "predictor": "G1_R07",
  "policy": "Q85",
  "eligible": true,
  "min_year_accuracy": 0.6023738872403561,
  "pooled_accuracy": 0.6047548291233283,
  "min_year_scored_count": 336,
  "full_log_loss": 0.6887199731035883,
  "eligible_rank": 1.0
}
```

