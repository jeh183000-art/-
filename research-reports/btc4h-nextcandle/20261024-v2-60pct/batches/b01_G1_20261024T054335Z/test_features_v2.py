"""Synthetic no-fit tests for V2 causal features and next-candle alignment."""
import importlib.util
from pathlib import Path
import unittest

import numpy as np
import pandas as pd

from features_v2 import (BAR_MS, INTRA_MS, baseline_features, build_features,
                         intrabar_features, validate_bars)


START = int(pd.Timestamp("2024-01-01T00:00:00Z").value // 1_000_000)


def candles(count=320, interval=BAR_MS, level=100.0):
    t = np.arange(count)
    opening = level + 0.01 * t + 0.3 * np.sin(t / 3)
    closing = opening + 0.15 * np.sin(t / 5) + 0.03
    volume = 100 + t % 9
    opens = START + t * interval
    return pd.DataFrame({
        "open_time": opens, "open": opening,
        "high": np.maximum(opening, closing) + 0.2,
        "low": np.minimum(opening, closing) - 0.2,
        "close": closing, "volume": volume.astype(float),
        "close_time": opens + interval - 1,
        "quote_volume": opening * volume,
        "trades": 50 + t % 5,
        "taker_buy_volume": volume * (0.5 + 0.1 * np.sin(t / 7)),
    })


def inputs(count=320):
    return candles(count), candles(count * 16, INTRA_MS), candles(count, level=20)


class FeatureTests(unittest.TestCase):
    def test_baseline_exactly_matches_frozen_v1(self):
        module_path = Path(__file__).resolve().parent / "reference" / "v1_model.py"
        spec = importlib.util.spec_from_file_location("frozen_v1_features", module_path)
        old = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(old)
        bars = validate_bars(candles())
        expected, expected_eligible = old.build_features(bars)
        actual, actual_eligible = baseline_features(bars)
        pd.testing.assert_frame_equal(actual, expected, check_exact=True)
        pd.testing.assert_series_equal(actual_eligible, expected_eligible)

    def test_all_feature_groups_ignore_future_changes_in_every_input(self):
        btc, intra, eth = inputs()
        X0, meta0 = build_features(btc, intra, eth)
        boundary = int(btc.loc[220, "close_time"] + 1)
        modified = []
        for source in (btc, intra, eth):
            frame = source.copy()
            future = frame.open_time >= boundary
            frame.loc[future, ["open", "high", "low", "close"]] *= 4
            frame.loc[future, ["volume", "quote_volume", "trades", "taker_buy_volume"]] *= 3
            modified.append(frame)
        X1, meta1 = build_features(*modified)
        for name in X0:
            pd.testing.assert_frame_equal(X0[name].iloc[:221], X1[name].iloc[:221], check_exact=True)
            pd.testing.assert_series_equal(meta0[f"eligible_{name}"].iloc[:221], meta1[f"eligible_{name}"].iloc[:221])
        self.assertTrue(meta0.eligible_G4.iloc[220])

    def test_partial_current_intrabar_bucket_is_ineligible(self):
        btc, intra, eth = inputs()
        missing_index = 150 * 16 + 7
        partial = intra.drop(index=missing_index).reset_index(drop=True)
        X, meta = build_features(btc, partial, eth)
        self.assertTrue(meta.eligible_G1.iloc[150])
        self.assertTrue(meta.eligible_G2.iloc[150])
        self.assertFalse(meta.intrabar_complete.iloc[150])
        self.assertFalse(meta.eligible_G3.iloc[150])
        self.assertFalse(meta.eligible_G4.iloc[150])
        self.assertTrue(meta.eligible_G3.iloc[151])
        self.assertTrue(X["G3"].filter(like="intra_").iloc[150].isna().all())

    def test_later_intrabar_buckets_cannot_fill_missing_current_bucket(self):
        btc, intra, eth = inputs()
        boundary = START + 151 * BAR_MS
        historical = intra[intra.open_time < boundary]
        without_last = historical.iloc[:-1].copy()
        a, ma = build_features(btc, without_last, eth)
        b, mb = build_features(btc, pd.concat([without_last, intra[intra.open_time >= boundary]], ignore_index=True), eth)
        self.assertFalse(ma.eligible_G3.iloc[150])
        self.assertFalse(mb.eligible_G3.iloc[150])
        pd.testing.assert_series_equal(a["G3"].iloc[150], b["G3"].iloc[150])

    def test_next_open_label_and_doji_axis_preserved(self):
        btc = candles()
        btc.loc[100, ["open", "high", "low", "close"]] = [100, 111, 99, 110]
        btc.loc[101, ["open", "high", "low", "close"]] = [120, 121, 114, 115]
        btc.loc[102, "close"] = btc.loc[102, "open"]
        X, meta = build_features(btc)
        self.assertEqual(meta.loc[100, "y"], 0)
        self.assertTrue(np.isnan(meta.loc[101, "y"]))
        self.assertEqual(meta.loc[101, "target_color"], 0)
        self.assertEqual(meta.loc[102, "target_open_time"], btc.loc[103, "open_time"])
        self.assertFalse(meta.target_available.iloc[-1])
        self.assertTrue(pd.isna(meta.y.iloc[-1]))
        for frame in X.values():
            self.assertNotIn("y", frame)
            self.assertNotIn("target_color", frame)
            self.assertNotIn("target_open", frame)

    def test_btc_gap_resets_history_and_never_connects_target(self):
        btc, intra, eth = inputs(400)
        btc = btc.drop(index=150).reset_index(drop=True)
        _, meta = build_features(btc, intra, eth)
        self.assertFalse(meta.target_available.iloc[149])
        self.assertTrue(pd.isna(meta.y.iloc[149]))
        for name in ("G1", "G2", "G3", "G4"):
            self.assertFalse(meta[f"eligible_{name}"].iloc[150:246].any())
            self.assertTrue(meta[f"eligible_{name}"].iloc[246])

    def test_eth_exact_join_never_forward_fills_missing_bar(self):
        btc, intra, eth = inputs(400)
        eth = eth.drop(index=150).reset_index(drop=True)
        X, meta = build_features(btc, intra, eth)
        self.assertTrue(meta.eligible_G3.iloc[150])
        self.assertFalse(meta.eligible_G4.iloc[150])
        self.assertTrue(pd.isna(X["G4"].loc[150, "eth_body_pct"]))
        self.assertFalse(meta.eligible_G4.iloc[151:247].any())
        self.assertTrue(meta.eligible_G4.iloc[247])

    def test_undefined_intrabar_ratios_remain_nan_with_known_missing_flag(self):
        btc, intra, eth = inputs()
        ids = np.arange(150 * 16 + 12, 151 * 16)
        intra.loc[ids, ["volume", "quote_volume", "trades", "taker_buy_volume"]] = 0
        X, meta = build_features(btc, intra, eth)
        self.assertTrue(meta.eligible_G3.iloc[150])
        self.assertTrue(pd.isna(X["G3"].loc[150, "intra_taker_fraction_last4"]))
        self.assertEqual(X["G3"].loc[150, "intra_taker_last4_missing"], 1)
        self.assertEqual(X["G3"].loc[150, "intra_zero_volume_fraction"], .25)

    def test_intrabar_bucket_arithmetic_and_bounds(self):
        btc, intra, eth = inputs()
        aggregated = intrabar_features(intra)
        i = 140
        window = intra.iloc[i * 16:(i + 1) * 16]
        row = aggregated.loc[START + i * BAR_MS]
        self.assertAlmostEqual(row.intra_return_last_4, window.close.iloc[-1] / window.open.iloc[-4] - 1)
        self.assertAlmostEqual(row.intra_taker_fraction_16, window.taker_buy_volume.sum() / window.volume.sum())
        self.assertAlmostEqual(row.intra_volume_share_last4, window.volume.iloc[-4:].sum() / window.volume.sum())
        self.assertGreaterEqual(row.intra_close_location, 0)
        self.assertLessEqual(row.intra_close_location, 1)
        self.assertLessEqual(row.intra_max_drawdown_closes, 0)

    def test_schema_sizes_and_no_input_mutation(self):
        source = inputs()
        copies = tuple(frame.copy(deep=True) for frame in source)
        X, meta = build_features(*source)
        self.assertEqual(list(X), ["G1", "G2", "G3", "G4"])
        self.assertEqual(X["G1"].shape[1], 38)
        counts = [frame.shape[1] for frame in X.values()]
        self.assertEqual(counts, sorted(counts))
        self.assertLess(counts[-1], 200)
        for original, copied in zip(source, copies):
            pd.testing.assert_frame_equal(original, copied)
        self.assertEqual(meta.prediction_time.iloc[100], btc_boundary := START + 101 * BAR_MS)
        self.assertEqual(meta.label_end_time.iloc[100], btc_boundary + BAR_MS)


if __name__ == "__main__":
    unittest.main(verbosity=2)
