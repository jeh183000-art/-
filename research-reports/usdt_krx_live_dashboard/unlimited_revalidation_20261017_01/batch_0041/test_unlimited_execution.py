# /// script
# requires-python = ">=3.12"
# dependencies = ["numpy", "numba", "pandas"]
# ///
import os
from pathlib import Path
import unittest

import numpy as np

from build_unlimited_engine import build
from unlimited_execution import Condition, Market, run

ROOT = Path(__file__).resolve().parents[1]
STUDY = ROOT / "outputs/usdt_krx_live_dashboard/data/unlimited_revalidation_20261017_01"


def market_for(gaps, future=1400.0):
    count = len(gaps)
    times = np.arange(count, dtype=np.int64)
    gap = np.asarray(gaps, dtype=np.float64)
    spot = future * (1 + gap / 100)
    futures = np.full(count, future)
    continuous = np.ones(count, dtype=np.bool_)
    continuous[0] = False
    zeros_bool = np.zeros(count, dtype=np.bool_)
    nan = np.full(count, np.nan)
    rates = np.full(count, 0.5)
    vectors = (times, np.zeros(count, dtype=np.int64), zeros_bool.copy(), np.ones(count, dtype=np.int64), gap, spot, spot.copy(), futures, futures.copy(), zeros_bool.copy(), nan.copy(), np.zeros(count, dtype=np.int64), continuous, zeros_bool.copy(), nan.copy(), nan.copy(), rates, rates * 2 / 3)
    return Market(vectors, tuple(str(i) for i in range(count)), ("TEST_ONLY",))


class UnlimitedExecutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["NUMBA_CACHE_DIR"] = str(ROOT / "work/unlimited_revalidation_numba_cache")
        source = ROOT / "outputs/usdt_krx_live_dashboard/data/pnl_optimization_2026/approved_20261016_01/paper_engine.py"
        cls.engine = build(source, STUDY / "engine_unlimited_generated.py")

    def test_zero_cash_admits_more_than_five_and_below_minus_four(self):
        market = market_for([0, -4.3, -4.3])
        case = Condition("TEST_ZERO_CASH", 1, 1, 0.1, 0.1, 1.0)
        result = run(self.engine.simulate_one, market, case)
        self.assertEqual(result.summary[0], 43)
        self.assertEqual(result.summary[22], 43)
        self.assertTrue(all(result.summary[i] == 0 for i in (25, 26, 27)))
        self.assertLess(result.residuals[:, 5].min(), -4.0)

    def test_capital_limited_branch_rejects_but_unlimited_accepts_same_signal(self):
        market = market_for([0, -0.3, -0.3])
        limited = run(self.engine.simulate_one, market, Condition("L", 1, 1, 0.2, 0.2, 1.0, capital_limited=True))
        unlimited = run(self.engine.simulate_one, market, Condition("U", 1, 1, 0.2, 0.2, 1.0))
        self.assertEqual(limited.summary[0], 0)
        self.assertEqual(limited.summary[25], 1)
        self.assertEqual(unlimited.summary[0], 1)

    def test_required_margin_over_thirty_million_does_not_reject(self):
        market = market_for([0, -0.3, -0.3], future=100000.0)
        result = run(self.engine.simulate_one, market, Condition("LARGE_MARGIN", 1, 1, 0.2, 0.2, 1.0))
        self.assertGreater(result.summary[18], 30000000)
        self.assertEqual(result.summary[0], 1)
        self.assertEqual(result.summary[26], 0)

    def test_one_fill_sensitivity_does_not_defer_unfilled_stages(self):
        market = market_for([0, -0.8, -0.8, -0.8])
        many = run(self.engine.simulate_one, market, Condition("M", 1, 1, 0.1, 0.1, 1.0))
        one = run(self.engine.simulate_one, market, Condition("O", 1, 1, 0.1, 0.1, 1.0, one_fill_per_bar=True))
        self.assertEqual(many.summary[0], 8)
        self.assertEqual(one.summary[0], 1)

    def test_memory_capacity_from_future_extreme_does_not_change_prefix_fills(self):
        prefix = market_for([0, -0.4, -0.4, 0.5, 0.5])
        full = market_for([0, -0.4, -0.4, 0.5, 0.5, -6.2, -6.2])
        case = Condition("PREFIX", 1, 1, 0.1, 0.1, 0.2)
        short = run(self.engine.simulate_one, prefix, case)
        long = run(self.engine.simulate_one, full, case)
        a = short.events[(short.events[:, 0] == 1) & (short.events[:, 1] < 5)]
        b = long.events[(long.events[:, 0] == 1) & (long.events[:, 1] < 5)]
        np.testing.assert_array_equal(a, b)

    def test_no_continuous_next_bar_means_no_fill(self):
        market = market_for([0, -0.3, -0.3])
        market.vectors[12][2] = False
        result = run(self.engine.simulate_one, market, Condition("GAP", 1, 1, 0.2, 0.2, 1.0))
        self.assertEqual(result.summary[0], 0)

    def test_buffer_overflow_is_retried_before_accepting_any_result(self):
        engine = self.engine

        class TinyFirstBuffers:
            def __init__(self):
                self.calls = 0

            def __call__(self, *arguments):
                values = list(arguments)
                if self.calls == 0:
                    values[-2], values[-1] = 1, 1
                self.calls += 1
                return engine.simulate_one(*values)

        kernel = TinyFirstBuffers()
        market = market_for([0, -0.8, -0.8, 0.5, 0.5])
        result = run(kernel, market, Condition("OVERFLOW", 1, 1, 0.1, 0.1, 0.2))
        self.assertEqual(result.retries, 1)
        self.assertEqual(len(result.trades), 8)
        self.assertEqual(result.summary[41], 0)
        self.assertEqual(result.summary[42], 0)

    def test_individual_stage_can_reenter_on_new_crossing_in_same_cycle(self):
        market = market_for([0, -0.4, -0.4, -0.2, -0.2, -0.4, -0.4, -0.2, -0.2, 0.1, 0.1])
        result = run(self.engine.simulate_one, market, Condition("REENTER", 1, 0, 0.2, 0.2, 0.2))
        self.assertEqual(result.summary[0], 3)
        self.assertEqual(len(result.trades), 3)
        self.assertEqual(list(result.trades[:, 2]), [1, 1, 0])


if __name__ == "__main__":
    unittest.main()
