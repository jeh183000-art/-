from __future__ import annotations

import numpy as np
from numba import njit


@njit(cache=True)
def replay(v, trades, events, ledger, orders, slip_bp):
    cash_s, cash_f = 0., 30000000.
    held = 0
    entry_s = basis = 0.
    cycle_gross = cycle_cost = peak = mdd = 0.
    e = t = o = 0
    maximum_difference = 0.
    quantity = 170000.
    minimum_initial = minimum_maintenance = 1e100
    bad_marks = 0
    for i in range(len(v[0])):
        for phase in range(3):
            if phase == 2 and not v[13][i]:
                assert np.all(np.isnan(ledger[i, phase]))
                continue
            if phase == 0:
                while o < len(orders) and int(orders[o, 0]) == i:
                    order = orders[o]
                    assert order[3] == 17 and order[4] in (0, 17)
                    assert held == 0 and order[1] == i - 1 and v[12][i]
                    assert abs(order[6] - cash_f) < .001
                    fee = 17 * 600 + v[7][i] * quantity * .000003157
                    slip = v[7][i] * quantity * slip_bp / 10000
                    need = v[7][i] * quantity * v[16][i]
                    accepted = cash_f - fee - slip >= max(0., need) - 1e-7
                    assert accepted == (order[4] == 17)
                    assert abs(order[7] - need) < .001
                    assert abs(order[8] - fee) < .001 and abs(order[9] - slip) < .001
                    o += 1
            while e < len(events) and int(events[e, 1]) == i:
                event = events[e]
                kind = int(event[0])
                if (kind == 5) != (phase == 2):
                    break
                assert phase in (0, 2)
                sign = int(event[3]); s, f = event[4], event[5]
                assert sign in (-1, 1)
                if kind == 5:
                    assert held == sign and v[13][i]
                    assert abs(s - v[15][i]) < 1e-9 and abs(f - v[14][i]) < 1e-9
                else:
                    assert abs(s - v[5][i]) < 1e-9
                    expected_f = v[10][i] if kind == 3 else v[7][i]
                    assert abs(f - expected_f) < 1e-9
                    if kind in (1, 2):
                        assert event[13] == i - 1 and v[12][i]
                    if kind in (3, 4):
                        assert v[9][i]
                sf = s * quantity * .0005 if kind in (1, 2) else 0.
                ff = 17 * 600 + f * quantity * .000003157 if kind != 5 else 0.
                ss = s * quantity * slip_bp / 10000 if kind in (1, 2) else 0.
                fs = f * quantity * slip_bp / 10000 if kind != 5 else 0.
                for actual, expected in ((event[8], sf), (event[9], ff), (event[10], ss), (event[11], fs)):
                    assert abs(actual - expected) < .001
                sg = fg = 0.
                if kind == 1:
                    assert held == 0
                    held = sign; entry_s = s; basis = f
                    cycle_gross = cycle_cost = 0.
                    cash_s -= sign * s * quantity
                elif kind == 2:
                    assert held == sign
                    sg = sign * (s - entry_s) * quantity
                    fg = sign * (basis - f) * quantity
                    cash_s += sign * s * quantity
                    assert t < len(trades) and trades[t, 1] < i and trades[t, 3] == i
                    expected_net = sg + cycle_gross + fg - cycle_cost - sf - ff - ss - fs
                    assert abs(trades[t, 13] - expected_net) < .001
                    assert abs(trades[t, 9] - sg) < .001
                    assert abs(trades[t, 10] - cycle_gross - fg) < .001
                    t += 1; held = 0
                else:
                    assert held == sign
                    if kind in (3, 5):
                        fg = sign * (basis - f) * quantity
                        cycle_gross += fg
                    if kind in (4, 5):
                        basis = f
                assert abs(event[6] - sg) < .001 and abs(event[7] - fg) < .001
                cash_s -= sf + ss
                cash_f += fg - ff - fs
                cycle_cost += sf + ff + ss + fs
                e += 1
            sm, fm = v[5][i], v[7][i]
            if phase == 1:
                sm, fm = v[6][i], v[8][i]
            elif phase == 2:
                sm, fm = v[15][i], v[14][i]
            fu = held * (basis - fm) * quantity
            initial = fm * quantity * v[16][i] if held else 0.
            maintenance = fm * quantity * v[17][i] if held else 0.
            total = cash_s + held * sm * quantity + cash_f + fu
            opennet = held * (sm - entry_s) * quantity + cycle_gross + fu - cycle_cost if held else 0.
            peak = max(peak, total - 30000000.)
            mdd = max(mdd, peak - total + 30000000.)
            finance = -cash_s
            if held == -1:
                finance += (entry_s + sm) * quantity
            expected = np.array((cash_s, cash_f, fu, initial, cash_f + fu - maintenance, total,
                                 opennet, held, mdd, cash_f + fu - initial, max(0., finance)))
            maximum_difference = max(maximum_difference, np.max(np.abs(expected - ledger[i, phase])))
            if held:
                minimum_initial = min(minimum_initial, cash_f + fu - initial)
                minimum_maintenance = min(minimum_maintenance, cash_f + fu - maintenance)
                bad_marks += cash_f + fu < maintenance - 1e-7
    assert e == len(events) and t == len(trades) and o == len(orders)
    assert maximum_difference < .01
    return np.array((maximum_difference, minimum_initial, minimum_maintenance, bad_marks, mdd))
