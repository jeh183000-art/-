"""Target alignment and causality checks; these do not fit real-data models."""
import unittest

import numpy as np
import pandas as pd

from model import BAR_MS, build_dataset, build_features, milliseconds, predict_latest, split_masks, validate_bars


def synthetic_bars(count=400, start="2024-01-01T00:00:00Z"):
    t = np.arange(count)
    opening = 100 + t * 0.01
    closing = opening + np.where(t % 2 == 0, 0.15, -0.1)
    opens = milliseconds(start) + t * BAR_MS
    return pd.DataFrame({
        "open_time": opens, "open": opening,
        "high": np.maximum(opening, closing) + 0.2,
        "low": np.minimum(opening, closing) - 0.2,
        "close": closing, "volume": 100.0 + t % 10,
        "close_time": opens + BAR_MS - 1,
        "quote_volume": (100.0 + t % 10) * opening,
        "trades": 50 + t % 5, "taker_buy_volume": (100.0 + t % 10) * 0.55,
    })


class AlignmentTests(unittest.TestCase):
    def test_target_uses_next_open_not_current_close(self):
        bars = synthetic_bars()
        bars.loc[100, ["open", "high", "low", "close"]] = [100, 111, 99, 110]
        bars.loc[101, ["open", "high", "low", "close"]] = [120, 121, 114, 115]
        _, meta = build_dataset(validate_bars(bars))
        self.assertEqual(meta.loc[100, "y"], 0)
        self.assertGreater(bars.loc[101, "close"], bars.loc[100, "close"])

    def test_doji_does_not_change_next_candle_alignment(self):
        bars = synthetic_bars()
        bars.loc[101, "close"] = bars.loc[101, "open"]
        _, meta = build_dataset(validate_bars(bars))
        self.assertTrue(pd.isna(meta.loc[100, "y"]))
        self.assertEqual(meta.loc[100, "target_color"], 0)
        self.assertEqual(meta.loc[101, "target_open_time"], bars.loc[102, "open_time"])
        self.assertEqual(meta.loc[101, "y"], 1)
        self.assertEqual(len(meta), len(bars))

    def test_gap_is_not_connected_to_next_observed_candle(self):
        bars = synthetic_bars().drop(index=150).reset_index(drop=True)
        _, meta = build_dataset(validate_bars(bars))
        self.assertFalse(meta.loc[149, "target_available"])
        self.assertTrue(pd.isna(meta.loc[149, "y"]))
        self.assertFalse(meta.loc[150:245, "feature_eligible"].any())
        self.assertTrue(meta.loc[246, "feature_eligible"])

    def test_feature_future_invariance(self):
        original = synthetic_bars()
        changed = original.copy()
        changed.loc[251:, ["open", "high", "low", "close"]] *= 7
        changed.loc[251:, ["volume", "quote_volume", "trades", "taker_buy_volume"]] *= 3
        X_original, eligible_original = build_features(original)
        X_changed, eligible_changed = build_features(changed)
        pd.testing.assert_frame_equal(X_original.loc[:250], X_changed.loc[:250])
        pd.testing.assert_series_equal(eligible_original.loc[:250], eligible_changed.loc[:250])
        self.assertEqual(len(X_original.columns), 38)
        self.assertFalse(eligible_original.iloc[:96].any())
        self.assertTrue(eligible_original.iloc[96])

    def test_last_bar_has_no_fabricated_label(self):
        _, meta = build_dataset(synthetic_bars())
        self.assertFalse(meta.target_available.iloc[-1])
        self.assertTrue(pd.isna(meta.y.iloc[-1]))

    def test_duplicate_and_missing_columns_rejected(self):
        bars = synthetic_bars()
        with self.assertRaises(ValueError):
            validate_bars(pd.concat([bars.iloc[:1], bars]))
        with self.assertRaises(ValueError):
            validate_bars(bars.drop(columns="taker_buy_volume"))

    def test_cutoff_purging_is_strict(self):
        test_start = milliseconds("2024-07-01T00:00:00Z")
        cal_start = test_start - 90 * 24 * 60 * 60 * 1000
        prediction = np.array([cal_start - 2 * BAR_MS, cal_start - BAR_MS,
                               cal_start, test_start - 2 * BAR_MS,
                               test_start - BAR_MS, test_start])
        meta = pd.DataFrame({
            "prediction_time": prediction, "label_end_time": prediction + BAR_MS,
            "feature_eligible": True, "target_available": True, "y": 1.0,
        })
        fit, cal, test, _, found_cal_start = split_masks(meta, test_start, test_start + BAR_MS)
        self.assertEqual(found_cal_start, cal_start)
        self.assertEqual(np.flatnonzero(fit).tolist(), [0])
        self.assertEqual(np.flatnonzero(cal).tolist(), [2, 3])
        self.assertEqual(np.flatnonzero(test).tolist(), [5])

    def test_predict_rejects_asof_before_model_availability(self):
        artifact = {"calibration_label_cutoff_exclusive_utc": "2025-10-01T00:00:00Z"}
        with self.assertRaisesRegex(ValueError, "backward leakage"):
            predict_latest(artifact, synthetic_bars(), "2024-01-01T01:00:00Z")

    def test_predict_rejects_old_bars_even_when_asof_is_later(self):
        artifact = {"calibration_label_cutoff_exclusive_utc": "2025-10-01T00:00:00Z"}
        with self.assertRaisesRegex(ValueError, "Latest closed bar"):
            predict_latest(artifact, synthetic_bars(), "2026-10-24T00:00:00Z")


if __name__ == "__main__":
    unittest.main(verbosity=2)
