# BTC 4h V2 independent evaluation audit

**Status: PASS**

Checks: 1239; failed: 0. No estimator was fitted.

Targets and timestamps were reconstructed from official 4h candles. Threshold masks, metrics, purged split counts and ranking were recomputed independently of engine functions.

## Independently reconstructed selection

```json
{
  "group": "G1",
  "predictor": "G1_R07",
  "policy": {
    "id": "Q85",
    "kind": "calibration_quantile",
    "quantile": 0.85
  }
}
```

