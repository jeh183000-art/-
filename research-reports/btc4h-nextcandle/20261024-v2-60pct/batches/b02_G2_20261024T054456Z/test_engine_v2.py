"""Synthetic-only guards for the frozen experiment; never open market data."""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

import engine_v2 as e


def settings():
    return json.loads((Path(__file__).parent / "settings.json").read_text())


def ranking_rows(predictor, a, b, pooled, n=300, active=10, share=.2, status="OK", loss=.69):
    return [{"group": predictor.split("_")[0], "predictor": predictor, "policy": "A500",
             "period": year, "status": status, "accuracy": accuracy, "scored_count": n if year != "ALL" else 2*n,
             "active_months": active if year != "ALL" else 2*active, "max_month_share": share,
             "full_log_loss": loss}
            for year, accuracy in (("2024", a), ("2025", b), ("ALL", pooled))]


class SplitTests(unittest.TestCase):
    def test_strict_label_availability_and_rolling_window(self):
        start, end = e.ms("2024-01-01"), e.ms("2024-04-01")
        cal_start = start-10*e.DAY_MS
        train_start = cal_start-20*e.DAY_MS
        prediction = np.array([train_start-e.BAR_MS, train_start,
                               cal_start-e.BAR_MS, cal_start,
                               start-e.BAR_MS, start, end-e.BAR_MS, end])
        meta = pd.DataFrame({"prediction_time": prediction, "label_end_time": prediction+e.BAR_MS,
                             "eligible_G1": True, "target_available": True, "y": 1.})
        fit, cal, test, prior, cs, ts = e.split_masks(meta, "G1", start, end, 10, 20)
        self.assertEqual(cs, cal_start)
        self.assertEqual(ts, train_start)
        self.assertEqual(np.flatnonzero(fit).tolist(), [1])
        self.assertEqual(np.flatnonzero(cal).tolist(), [3])
        self.assertEqual(np.flatnonzero(test).tolist(), [5, 6])
        self.assertFalse((fit & cal).any())
        self.assertFalse((cal & test).any())
        self.assertFalse(bool(prior.iloc[4]))  # label end == start is purged

    def test_doji_kept_in_forecasts_but_not_fit(self):
        start = e.ms("2024-01-01")
        meta = pd.DataFrame({"prediction_time": [start-100*e.DAY_MS, start, start+e.BAR_MS],
                             "label_end_time": [start-100*e.DAY_MS+e.BAR_MS, start+e.BAR_MS, start+2*e.BAR_MS],
                             "eligible_G1": [True]*3, "target_available": [True]*3, "y": [np.nan, np.nan, 1.]})
        fit, cal, test, prior, *_ = e.split_masks(meta, "G1", start, start+3*e.BAR_MS, 10)
        self.assertFalse(fit.any())
        self.assertEqual(np.flatnonzero(test).tolist(), [1, 2])


class CalibrationTests(unittest.TestCase):
    def test_negative_slope_has_smoothed_constant_not_inversion(self):
        raw = np.linspace(-3, 3, 80)
        y = (raw < -.4).astype(int)
        fitted = e.fit_calibrator(raw, y, 7)
        self.assertEqual(fitted["mode"], "constant_fallback")
        self.assertLess(fitted["fitted_slope"], 0)
        self.assertEqual(fitted["slope"], 0)
        expected = (y.sum()+1)/(len(y)+2)
        np.testing.assert_array_equal(e.calibrate(fitted, [-100, 0, 100]), np.full(3, expected))

    def test_positive_calibration_is_monotone(self):
        raw = np.linspace(-3, 3, 80)
        fitted = e.fit_calibrator(raw, raw > 0, 7)
        self.assertEqual(fitted["mode"], "sigmoid")
        self.assertGreater(fitted["slope"], 0)
        self.assertTrue((np.diff(e.calibrate(fitted, [-2, -1, 0, 1, 2])) > 0).all())

    def test_quantiles_use_past_distribution_and_constant_abstains(self):
        policies = settings()["policies"]
        past = np.array([.51, .6, .72, .85])
        expected = np.quantile(np.maximum(past, 1-past), .7, method="linear")
        threshold = e.quantile_thresholds(past, policies)
        self.assertEqual(threshold["Q70"], expected)
        for future in (np.array([.5, .6, .7]), np.array([.01, .99, .95])):
            frame = pd.DataFrame({"G1_R01__p_up": future, "G1_R01__Q70": threshold["Q70"]})
            policy = next(p for p in policies if p["id"] == "Q70")
            np.testing.assert_array_equal(e.policy_mask(frame, "G1_R01", policy), np.maximum(future, 1-future) >= expected)
            self.assertEqual(threshold["Q70"], expected)
        constant = e.quantile_thresholds([.6]*100, policies)
        self.assertEqual(constant["Q70"], 2.0)
        self.assertEqual(constant["Q85"], 2.0)
        frame = pd.DataFrame({"G1_R01__p_up": [.99, .01, .5], "G1_R01__Q70": 2.0})
        self.assertFalse(e.policy_mask(frame, "G1_R01", policy).any())

    def test_preprocessing_fitted_only_on_training(self):
        recipe = settings()["models"][0]
        model = e.create_model(recipe, 7)
        X = pd.DataFrame({"first": [0., 1., np.nan, 3., 4., 5.], "empty": [np.nan]*6})
        model.fit(X, [0, 0, 1, 0, 1, 1])
        before = model.named_steps["simpleimputer"].statistics_.copy()
        model.predict_proba(pd.DataFrame({"first": [1e20, np.nan], "empty": [1e30, 1e30]}))
        np.testing.assert_array_equal(model.named_steps["simpleimputer"].statistics_, before)
        self.assertEqual(before[0], 3.)
        self.assertEqual(before[1], 0.)


class SelectionTests(unittest.TestCase):
    def test_rank_minimum_year_before_pooled_accuracy(self):
        rows = ranking_rows("G1_R01", .61, .51, .60) + ranking_rows("G1_R02", .55, .55, .55)
        ranking = e.rank_candidates(pd.DataFrame(rows), settings())
        self.assertEqual(ranking.iloc[0].predictor, "G1_R02")
        self.assertTrue(ranking.eligible.all())

    def test_gate_failure_and_partial_recipe_ineligible(self):
        rows = (ranking_rows("G1_R01", .8, .8, .8, n=199)
                + ranking_rows("G1_R02", .8, .8, .8, active=7)
                + ranking_rows("G1_R03", .8, .8, .8, share=.3)
                + ranking_rows("G1_R04", .8, .8, .8, status="FAILED")
                + ranking_rows("G1_R05", .52, .52, .52))
        ranking = e.rank_candidates(pd.DataFrame(rows), settings())
        self.assertEqual(ranking.iloc[0].predictor, "G1_R05")
        self.assertEqual(int(ranking.eligible.sum()), 1)

    def test_tie_breaks_logloss_then_lexical(self):
        rows = (ranking_rows("G1_R03", .55, .55, .55, loss=.7)
                + ranking_rows("G1_R02", .55, .55, .55, loss=.69)
                + ranking_rows("G1_R01", .55, .55, .55, loss=.69))
        ranking = e.rank_candidates(pd.DataFrame(rows), settings())
        self.assertEqual(ranking.predictor.tolist(), ["G1_R01", "G1_R02", "G1_R03"])

    def test_full_payload_must_match_registered_parameters(self):
        s = settings()
        original = {"group": "G1", "predictor": "G1_R01", "policy": s["policies"][4],
                    "member_recipes": [s["models"][0]], "ensemble": None}
        e.validate_selection_payload(original, s)
        altered = copy.deepcopy(original)
        altered["policy"]["threshold"] = .5
        with self.assertRaises(ValueError):
            e.validate_selection_payload(altered, s)
        altered = copy.deepcopy(original)
        altered["member_recipes"] = [s["models"][9]]
        with self.assertRaises(ValueError):
            e.validate_selection_payload(altered, s)
        altered = copy.deepcopy(original)
        altered["ensemble"] = s["ensembles"][0]
        with self.assertRaises(ValueError):
            e.validate_selection_payload(altered, s)


class GuardTests(unittest.TestCase):
    def test_no_holdout_loader_before_selection(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(e, "make_config", return_value={}), patch.object(e, "load_inputs") as loader:
                with self.assertRaisesRegex(FileNotFoundError, "frozen selection"):
                    e.evaluate_candidate(settings(), "unused", "unused", "never-open", folder)
                loader.assert_not_called()

    def test_one_time_marker_blocks_second_attempt(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            e.write_json(root/"selection.json", {"status": "FROZEN_SELECTED"})
            e.write_exclusive_json(root/"evaluation"/"run_started.json", {"first": True})
            with self.assertRaisesRegex(FileExistsError, "already started"):
                e.validate_evaluation_guard(root, {}, settings())
            with self.assertRaises(FileExistsError):
                e.write_exclusive_json(root/"evaluation"/"run_started.json", {"first": False})
            self.assertTrue(json.loads((root/"evaluation"/"run_started.json").read_text())["first"])

    def test_atomic_marker_exists_before_first_holdout_related_check(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            e.write_json(root/"selection.json", {"placeholder": True})
            selection = {"predictor": "G1_R01", "policy": settings()["policies"][0]}

            def refuse_after_marker(*args):
                self.assertTrue((root/"evaluation"/"run_started.json").exists())
                raise RuntimeError("Synthetic stop before any source is read")

            with patch.object(e, "make_config", return_value={}), \
                    patch.object(e, "validate_evaluation_guard", return_value=selection), \
                    patch.object(e, "verify_code_freeze", side_effect=refuse_after_marker), \
                    patch.object(e, "load_inputs") as loader:
                with self.assertRaisesRegex(RuntimeError, "Synthetic stop"):
                    e.evaluate_candidate(settings(), "unused", "unused", "never-open", root)
                loader.assert_not_called()


class AccountingTests(unittest.TestCase):
    def test_matched_controls_and_doji_accounting(self):
        frame = pd.DataFrame({"G1_R01__p_up": [.9, .1, .55, .8], "y": [1., 0., 0., np.nan],
                              "month": ["2026-01"]*4})
        for name in e.CONTROL_NAMES:
            frame["ctrl_"+name] = 1
        result = e.score(frame, "G1_R01", {"id": "A600", "kind": "absolute", "threshold": .6})
        self.assertEqual(result["selected_count"], 3)
        self.assertEqual(result["scored_count"], 2)
        self.assertEqual(result["accuracy"], 1)
        self.assertEqual(result["coverage"], .75)
        self.assertEqual(result["scored_coverage"], 2/3)
        self.assertEqual(result["matched_always_up_accuracy"], .5)
        failed = e.score(frame, "G1_R01", {"id": "A500", "kind": "absolute", "threshold": .5}, "FAILED")
        self.assertTrue(np.isnan(failed["accuracy"]))
        self.assertEqual(failed["available_forecast_count"], 4)

    def test_csv_round_trip_preserves_threshold_ties(self):
        p = np.array([.525, np.nextafter(.525, 1), np.nextafter(.525, 0)])
        frame = pd.DataFrame({"G1_R01__p_up": p, "G1_R01__Q70": .525})
        policy = {"id": "Q70", "kind": "calibration_quantile", "quantile": .7}
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"ledger.csv"
            e.save_csv(frame, path)
            restored = e.read_csv(path)
            np.testing.assert_array_equal(restored.to_numpy(), frame.to_numpy())
            np.testing.assert_array_equal(e.policy_mask(frame, "G1_R01", policy),
                                          e.policy_mask(restored, "G1_R01", policy))


if __name__ == "__main__":
    unittest.main()
