# /// script
# requires-python = "==3.12.0"
# dependencies = ["numpy==2.2.6", "numba==0.61.2"]
# ///
# Run: Python312/python.exe -B bootstrap.py test
import numpy as np

from signals import Rule, prepare, trailing
from single_core import simulate


def market(gaps):
    gap = np.asarray(gaps, dtype=float)
    n = len(gap)
    zero = np.zeros(n, dtype=bool)
    cont = np.ones(n, dtype=bool)
    cont[0] = False
    future = np.full(n, 1400.0)
    spot = future * (1 + gap / 100)
    return (np.arange(n, dtype=np.int64), np.zeros(n, dtype=np.int64), zero.copy(), np.ones(n, dtype=np.int64), gap, spot.copy(), spot.copy(), future.copy(), future.copy(), zero.copy(), np.full(n, np.nan), np.zeros(n, dtype=np.int64), cont, zero.copy(), np.full(n, np.nan), np.full(n, np.nan), np.full(n, .1), np.full(n, .06))


def execute(v, entries, exits=None, mode=1, recovery=.2):
    n = len(v[0])
    e = np.asarray(entries, dtype=np.int64)
    out = np.zeros(n, dtype=bool) if exits is None else np.asarray(exits, dtype=bool)
    return simulate(v, e, out, out, np.zeros(n), mode, recovery, 1., 0., 0., 0., 0., 0., 0.)


def test_opposing_signals_cannot_add_while_held():
    v = market([0, -.5, -.6, -.7, -.8, -.9])
    trades, events, residual, risk, _, _ = execute(v, [0, 1, -1, 1, -1, 0], recovery=10.)
    assert len(trades) == 0
    assert (events[:, 0] == 1).sum() == 1
    assert residual[1] == 1 and risk[5] == 3


def test_close_is_next_bar_and_costs_reduce_score():
    v = market([0, -.5, -.6, -.2, 0, .1])
    tr, ev, res, _, _, _ = execute(v, [0, 1, 0, 0, 0, 0])
    assert len(tr) == 1 and res[1] == 0
    assert tuple(tr[0, :4]) == (1, 2, 3, 4)
    assert tr[0, 11] > 0 and tr[0, 12] > 0
    assert np.isclose(tr[0, 13], tr[0, 9] + tr[0, 10] - tr[0, 11] - tr[0, 12])
    assert ev[0, 1] > ev[0, 13]


def test_roll_and_settlement_telescope_without_extra_exposure():
    v = list(market([0, 0, 0, 0, 0, 0]))
    v[9][3] = True
    v[10][3] = 1400.
    v[7][3:] = [1410., 1407., 1405.]
    v[8][3:] = v[7][3:]
    v[5][5] = v[6][5] = 1402.
    v[13][4] = True
    v[14][4], v[15][4] = 1407., 1400.
    tr, ev, _, _, _, _ = execute(tuple(v), [0, 1, 0, 0, 0, 0], [0, 0, 0, 0, 1, 0], mode=0)
    assert len(tr) == 1 and tr[0, 15] == 1
    assert np.isclose(tr[0, 9], 20000.) and np.isclose(tr[0, 10], 50000.)
    assert np.isclose(ev[:, 6:8].sum() - ev[:, 8:12].sum(), tr[0, 13])
    assert (ev[:, 0] == 3).sum() == (ev[:, 0] == 4).sum() == 1


def test_features_are_prefix_causal_and_reset_on_roll():
    g = np.sin(np.arange(200) / 10)
    rolls = np.zeros(200, dtype=bool)
    rolls[130] = True
    full = trailing(g, rolls, 60)
    short = trailing(g[:110], rolls[:110], 60)
    assert np.allclose(full[:110], short, equal_nan=True)
    assert np.isnan(full[130:190]).all()
    expected = g[40:100].mean()
    assert np.isclose(full[100, 0], expected)


def test_no_initial_retroactive_entry_or_gap_crossing():
    v = list(market([-.9, -.8, -.7, 0, -.8, -.2]))
    v[12][4] = False
    e, _, _, _, _ = prepare(Rule("TEST", "relative", 1, entry=.5), tuple(v), {})
    assert e[0] == 0 and e[4] == 0 and not e.any()


def test_residual_is_separate_and_liquidation_includes_exit_cost():
    v = market([0, -.5, -.6, -.8])
    tr, ev, res, _, _, _ = execute(v, [0, 1, 0, 0], recovery=10.)
    assert len(tr) == 0 and res[1] != 0
    assert res[9] > 0
    assert np.isclose(res[10], res[5] + res[6] - res[7] - res[8] - res[9])


def test_reentry_only_after_prior_exit():
    v = market([0, -.5, -.6, 0, 0, -.5, -.6, 0, 0])
    tr, ev, _, _, _, _ = execute(v, [0, 1, -1, 0, 0, -1, 1, 0, 0], recovery=.2)
    assert len(tr) >= 1
    held = 0
    for row in ev:
        if row[0] == 1:
            assert held == 0
            held = int(row[3])
        if row[0] == 2:
            assert held != 0
            held = 0


def test_reverse_hedge_pnl_and_one_set_exit():
    v = market([0, .5, .6, .2, 0, -.1])
    tr, _, res, _, _, _ = execute(v, [0, -1, 0, 0, 0, 0])
    assert len(tr) == 1 and tr[0, 4] == -1 and res[1] == 0
    assert tr[0, 9] > 0 and tr[0, 10] == 0
    assert tr[0, 13] < tr[0, 9]


def test_reversal_confirmation_does_not_backdate_entry():
    v = market([0, -.6, -.8, -.7, -.6, 0, .1])
    r = Rule("TEST", "reversal", 1, entry=.5, confirm=.1, recovery=.3)
    es, el, er, center, mode = prepare(r, v, {})
    tr, ev, _, _, _, _ = simulate(v, es, el, er, center, mode, r.recovery, 1., r.confirm, 0., 0., 0., 0., 0.)
    assert ev[0, 13] == 3 and ev[0, 1] == 4
    assert len(tr) == 1 and tr[0, 1] > 2


def test_risk_extremes_preserve_drawdown_and_open_loss():
    v = market([0, -.5, -.6, -2., -.5, 0])
    _, _, _, risk, _, marks = execute(v, [0, 1, 0, 0, 0, 0], recovery=10.)
    assert np.isclose(marks[:, 8].max(), risk[0])
    assert np.isclose(-marks[:, 7].min(), risk[1])
