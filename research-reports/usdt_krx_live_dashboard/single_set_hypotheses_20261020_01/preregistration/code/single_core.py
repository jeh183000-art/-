# /// script
# requires-python = "==3.12.0"
# dependencies = ["numpy==2.2.6", "numba==0.61.2"]
# ///
# Run through study.py after preregistration; prices are observed execution proxies.
from __future__ import annotations

import numpy as np
from numba import njit


@njit(cache=True)
def simulate(v, entry_sign, exit_long, exit_short, center, mode, recovery, fraction,
             confirm, max_hold, gap_stop, pnl_profit, pnl_stop, stall):
    n = len(v[0])
    trades = np.zeros((n // 2 + 2, 18))
    events = np.zeros((4 * n + 10, 14))
    marks = np.zeros((3 * n + 10, 9))
    equity = np.zeros(n)
    nt = ne = nm = 0
    direction = pending = 0
    signal_i = entry_i = cycle = 0
    entry_gap = target = spot_entry = future_entry = basis = 0.0
    accumulated = fees = slips = realized = 0.0
    rolls = ignored = 0
    peak = mdd = max_loss = max_margin = 0.0
    max_futures_loss = max_spot_need = 0.0
    best_gap = last_progress = 0.0
    armed = 0
    trough = armed_at = 0.0
    qty = 10000.0
    for i in range(n):
        time, so, sc, fo, fc = v[0][i], v[5][i], v[6][i], v[7][i], v[8][i]
        if direction != 0 and v[9][i]:
            old = v[10][i]
            assert np.isfinite(old) and old > 0
            gain = direction * (basis - old) * qty
            close_fee = 600.0 + old * qty * 0.000003157
            open_fee = 600.0 + fo * qty * 0.000003157
            close_slip, open_slip = old * qty * 0.0002, fo * qty * 0.0002
            events[ne] = np.array((3, i, cycle, direction, so, old, 0, gain, 0, close_fee, 0, close_slip, v[11][i], -1), dtype=np.float64)
            ne += 1
            events[ne] = np.array((4, i, cycle, direction, so, fo, 0, 0, 0, open_fee, 0, open_slip, v[3][i], -1), dtype=np.float64)
            ne += 1
            accumulated += gain
            fees += close_fee + open_fee
            slips += close_slip + open_slip
            basis = fo
            rolls += 1
        if pending != 0:
            assert v[12][i] and i > signal_i
            if pending == 2:
                assert direction != 0
                sg = direction * (so - spot_entry) * qty
                fg = direction * (basis - fo) * qty
                sf, ff = so * qty * 0.0005, 600.0 + fo * qty * 0.000003157
                ss, fs = so * qty * 0.0002, fo * qty * 0.0002
                events[ne] = np.array((2, i, cycle, direction, so, fo, sg, fg, sf, ff, ss, fs, v[3][i], signal_i), dtype=np.float64)
                ne += 1
                net = sg + accumulated + fg - fees - sf - ff - slips - ss - fs
                trades[nt] = np.array((entry_i - 1, entry_i, signal_i, i, direction, spot_entry, future_entry,
                              so, fo, sg, accumulated + fg, fees + sf + ff, slips + ss + fs,
                              net, time - v[0][entry_i], rolls, target, cycle), dtype=np.float64)
                nt += 1
                realized += net
                direction = 0
            else:
                assert direction == 0 and (pending == 1 or pending == -1)
                direction = pending
                cycle += 1
                entry_i = i
                spot_entry, future_entry, basis = so, fo, fo
                accumulated = 0.0
                fees = so * qty * 0.0005 + 600.0 + fo * qty * 0.000003157
                slips = (so + fo) * qty * 0.0002
                rolls = 0
                entry_gap = v[4][signal_i]
                target = entry_gap + direction * recovery
                if mode == 2:
                    target = entry_gap + fraction * (center[signal_i] - entry_gap)
                if mode == 0:
                    target = direction * center[signal_i]
                if mode == 3:
                    target = np.nan
                best_gap = direction * v[4][i]
                last_progress = time
                events[ne] = np.array((1, i, cycle, direction, so, fo, 0, 0, so * qty * 0.0005,
                              600.0 + fo * qty * 0.000003157, so * qty * 0.0002,
                              fo * qty * 0.0002, v[3][i], signal_i), dtype=np.float64)
                ne += 1
            pending = 0
        for phase in range(3):
            if phase == 2 and not v[13][i]:
                continue
            sm, fm = so, fo
            if phase == 1:
                sm, fm = sc, fc
            if phase == 2:
                sm, fm = v[15][i], v[14][i]
                if direction != 0:
                    gain = direction * (basis - fm) * qty
                    accumulated += gain
                    basis = fm
                    events[ne] = np.array((5, i, cycle, direction, sm, fm, 0, gain, 0, 0, 0, 0, v[3][i], -1), dtype=np.float64)
                    ne += 1
            open_net = 0.0
            previous_max_loss = max_loss
            if direction != 0:
                gross = direction * (sm - spot_entry) * qty + accumulated + direction * (basis - fm) * qty
                open_net = gross - fees - slips
                max_loss = max(max_loss, -open_net)
                max_margin = max(max_margin, fm * qty * v[16][i])
                max_futures_loss = max(max_futures_loss, -(accumulated + direction * (basis - fm) * qty))
                if direction == 1:
                    max_spot_need = max(max_spot_need, spot_entry * qty)
            value = realized + open_net
            new_extreme = value > peak or peak - value > mdd or max_loss > previous_max_loss
            peak = max(peak, value)
            mdd = max(mdd, peak - value)
            if new_extreme:
                marks[nm] = np.array((i, phase, cycle, direction, sm, fm, value, open_net, mdd), dtype=np.float64)
                nm += 1
            if phase == 1:
                equity[i] = value
        can_next = i + 1 < n and bool(v[12][i + 1]) and not bool(v[9][i])
        if direction != 0:
            armed = 0
            ignored += entry_sign[i] != 0
            progress = direction * v[4][i]
            if progress > best_gap + 0.01:
                best_gap, last_progress = progress, time
            reached = False
            if mode == 0 or mode == 3:
                reached = bool(exit_long[i]) if direction == 1 else bool(exit_short[i])
            else:
                reached = direction * (v[4][i] - target) >= -1e-12
            stop_gap = gap_stop > 0 and direction * (v[4][i] - entry_gap) <= -gap_stop
            close_cost = sc * qty * 0.0005 + 600.0 + fc * qty * 0.000003157 + (sc + fc) * qty * 0.0002
            close_net = direction * (sc - spot_entry) * qty + accumulated + direction * (basis - fc) * qty - fees - slips - close_cost
            ret = 100.0 * close_net / (spot_entry * qty)
            stop_pnl = (pnl_profit > 0 and ret >= pnl_profit) or (pnl_stop > 0 and ret <= -pnl_stop)
            stop_time = max_hold > 0 and time - v[0][entry_i] >= max_hold
            stop_stall = stall > 0 and time - last_progress >= stall
            if can_next and (reached or stop_gap or stop_pnl or stop_time or stop_stall):
                pending = 2
                signal_i = i
        elif can_next:
            sign = int(entry_sign[i])
            if confirm > 0:
                if not v[12][i] or v[9][i] or (armed != 0 and time - armed_at > 240):
                    armed = 0
                if sign != 0:
                    armed, trough, armed_at = sign, sign * v[4][i], time
                sign = 0
                if armed != 0:
                    oriented = armed * v[4][i]
                    trough = min(trough, oriented)
                    if oriented >= 0:
                        armed = 0
                    elif oriented >= trough + confirm:
                        sign, armed = armed, 0
            if sign != 0:
                pending = sign
                signal_i = i
        else:
            armed = 0
    residual = np.zeros(12)
    if direction != 0:
        sg = direction * (v[6][-1] - spot_entry) * qty
        fg = accumulated + direction * (basis - v[8][-1]) * qty
        cost = v[6][-1] * qty * 0.0005 + 600.0 + v[8][-1] * qty * 0.000003157 + (v[6][-1] + v[8][-1]) * qty * 0.0002
        residual[:] = np.array((cycle, direction, entry_i, spot_entry, future_entry, sg, fg, fees, slips, cost,
                       sg + fg - fees - slips - cost, v[0][-1] - v[0][entry_i]), dtype=np.float64)
    risk = np.array((mdd, max_loss, max_margin, max_futures_loss, max_spot_need, ignored))
    return trades[:nt], events[:ne], residual, risk, equity, marks[:nm]
