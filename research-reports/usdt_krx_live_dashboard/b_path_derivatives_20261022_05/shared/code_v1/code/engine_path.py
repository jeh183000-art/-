# /// script
# requires-python = "==3.12.0"
# dependencies = ["numpy==2.2.6", "numba==0.61.2"]
# ///
# Run via runner.py; fixed atomic 17-contract bundles and observed price proxies.
from __future__ import annotations

import numpy as np
from numba import njit


@njit(cache=True)
def simulate(v, entry_sign, exit_long, exit_short, target_long, target_short, mode,
             confirm, max_hold, gap_stop, pnl_profit, pnl_stop, stall, options, slippage):
    n = len(v[0])
    trades = np.zeros((n // 2 + 2, 19))
    events = np.zeros((5 * n + 10, 14))
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
    qty = 170000.0
    spot_cash = 0.0
    future_cash = 30000000.0
    orders = np.zeros((n + 1, 12))
    ledger = np.full((n, 3, 11), np.nan)
    no = bad_rolls = 0
    first_bad_roll = -1
    pending_reason = 0
    last_exit_time = -1e100
    armed_row = 0
    for i in range(n):
        time, so, sc, fo, fc = v[0][i], v[5][i], v[6][i], v[7][i], v[8][i]
        if direction != 0 and v[9][i]:
            old = v[10][i]
            assert np.isfinite(old) and old > 0
            gain = direction * (basis - old) * qty
            close_fee = 10200.0 + old * qty * 0.000003157
            open_fee = 10200.0 + fo * qty * 0.000003157
            close_slip, open_slip = old * qty * (slippage / 10000.0), fo * qty * (slippage / 10000.0)
            events[ne] = np.array((3, i, cycle, direction, so, old, 0, gain, 0, close_fee, 0, close_slip, v[11][i], -1), dtype=np.float64)
            ne += 1
            events[ne] = np.array((4, i, cycle, direction, so, fo, 0, 0, 0, open_fee, 0, open_slip, v[3][i], -1), dtype=np.float64)
            ne += 1
            future_cash += gain - close_fee - open_fee - close_slip - open_slip
            if future_cash < fo * qty * v[16][i] - 1e-7:
                bad_rolls += 1
                if first_bad_roll < 0:
                    first_bad_roll = i
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
                sf, ff = so * qty * 0.0005, 10200.0 + fo * qty * 0.000003157
                ss, fs = so * qty * (slippage / 10000.0), fo * qty * (slippage / 10000.0)
                events[ne] = np.array((2, i, cycle, direction, so, fo, sg, fg, sf, ff, ss, fs, v[3][i], signal_i), dtype=np.float64)
                ne += 1
                spot_cash += direction * so * qty - sf - ss
                future_cash += fg - ff - fs
                net = sg + accumulated + fg - fees - sf - ff - slips - ss - fs
                trades[nt] = np.array((entry_i - 1, entry_i, signal_i, i, direction, spot_entry, future_entry,
                              so, fo, sg, accumulated + fg, fees + sf + ff, slips + ss + fs,
                              net, time - v[0][entry_i], rolls, target, cycle, pending_reason), dtype=np.float64)
                nt += 1
                realized += net
                direction = 0
                last_exit_time = time
            else:
                assert direction == 0 and (pending == 1 or pending == -1)
                ff_quote = 10200.0 + fo * qty * 0.000003157
                fs_quote = fo * qty * slippage / 10000.0
                reason = 0
                if future_cash - ff_quote - fs_quote < -1e-7:
                    reason = 1
                elif future_cash - ff_quote - fs_quote < fo * qty * v[16][i] - 1e-7:
                    reason = 2
                orders[no] = np.array((i, signal_i, pending, 17, 17 if reason == 0 else 0, reason, future_cash, fo * qty * v[16][i], ff_quote, fs_quote, so, fo), dtype=np.float64)
                no += 1
                if reason == 0:
                    direction = pending
                    cycle += 1
                    entry_i = i
                    spot_entry, future_entry, basis = so, fo, fo
                    accumulated = 0.0
                    fees = so * qty * 0.0005 + 10200.0 + fo * qty * 0.000003157
                    slips = (so + fo) * qty * (slippage / 10000.0)
                    spot_cash -= direction * so * qty + so * qty * (0.0005 + slippage / 10000.0)
                    future_cash -= ff_quote + fs_quote
                    rolls = 0
                    entry_gap = v[4][signal_i]
                    target = target_long[signal_i] if direction == 1 else target_short[signal_i]
                    best_gap = direction * v[4][i]
                    last_progress = time
                    events[ne] = np.array((1, i, cycle, direction, so, fo, 0, 0, so * qty * 0.0005,
                                  10200.0 + fo * qty * 0.000003157, so * qty * (slippage / 10000.0),
                                  fo * qty * (slippage / 10000.0), v[3][i], signal_i), dtype=np.float64)
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
                    future_cash += gain
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
            fu = direction * (basis - fm) * qty if direction != 0 else 0.0
            initial_need = fm * qty * v[16][i] if direction != 0 else 0.0
            maintenance = fm * qty * v[17][i] if direction != 0 else 0.0
            spot_value = direction * sm * qty if direction != 0 else 0.0
            value = spot_cash + spot_value + future_cash + fu - 30000000.0
            new_extreme = value > peak or peak - value > mdd or max_loss > previous_max_loss
            peak = max(peak, value)
            mdd = max(mdd, peak - value)
            if new_extreme:
                marks[nm] = np.array((i, phase, cycle, direction, sm, fm, value, open_net, mdd), dtype=np.float64)
                nm += 1
            finance = -spot_cash
            if direction == -1:
                finance = -spot_cash + spot_entry * qty + sm * qty
            ledger[i, phase] = np.array((spot_cash, future_cash, fu, initial_need, future_cash + fu - maintenance, value + 30000000.0, open_net, direction, mdd, future_cash + fu - initial_need, max(0.0, finance)), dtype=np.float64)
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
            if mode == 4:
                reached = bool(exit_long[i]) if direction == 1 else bool(exit_short[i])
            else:
                reached = direction * (v[4][i] - target) >= -1e-12
            stop_gap = gap_stop > 0 and direction * (v[4][i] - entry_gap) <= -gap_stop
            close_cost = sc * qty * 0.0005 + 10200.0 + fc * qty * 0.000003157 + (sc + fc) * qty * (slippage / 10000.0)
            close_net = direction * (sc - spot_entry) * qty + accumulated + direction * (basis - fc) * qty - fees - slips - close_cost
            ret = 100.0 * close_net / (spot_entry * qty)
            profit_limit = options[0] if direction == 1 else options[1]
            if profit_limit < 0:
                profit_limit = pnl_profit
            reached = reached and bool(options[5])
            stop_pnl = (profit_limit > 0 and ret >= profit_limit) or (pnl_stop > 0 and ret <= -pnl_stop)
            stop_time = max_hold > 0 and time - v[0][entry_i] >= max_hold
            stop_stall = stall > 0 and time - last_progress >= stall
            if can_next and (reached or stop_gap or stop_pnl or stop_time or stop_stall):
                pending = 2
                pending_reason = int(reached) + 2 * int(stop_gap) + 4 * int(stop_pnl) + 8 * int(stop_time) + 16 * int(stop_stall)
                signal_i = i
        elif can_next and time - last_exit_time >= options[2]:
            sign = int(entry_sign[i])
            if confirm > 0 or options[4] > 0:
                if not v[12][i] or v[9][i] or (armed != 0 and time - armed_at > options[3]):
                    armed = 0
                if sign != 0:
                    armed, trough, armed_at = sign, sign * v[4][i], time
                    armed_row = i
                sign = 0
                if armed != 0:
                    oriented = armed * v[4][i]
                    trough = min(trough, oriented)
                    if oriented >= 0:
                        armed = 0
                    elif oriented >= trough + confirm and i - armed_row >= options[4]:
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
        cost = v[6][-1] * qty * 0.0005 + 10200.0 + v[8][-1] * qty * 0.000003157 + (v[6][-1] + v[8][-1]) * qty * (slippage / 10000.0)
        residual[:] = np.array((cycle, direction, entry_i, spot_entry, future_entry, sg, fg, fees, slips, cost,
                       sg + fg - fees - slips - cost, v[0][-1] - v[0][entry_i]), dtype=np.float64)
    risk = np.array((mdd, max_loss, max_margin, max_futures_loss, max_spot_need, ignored, bad_rolls, first_bad_roll))
    return trades[:nt], events[:ne], residual, risk, equity, marks[:nm], ledger, orders[:no]
