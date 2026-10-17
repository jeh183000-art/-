from __future__ import annotations
from unlimited_risk import update_risk
import json
from pathlib import Path
from typing import Any
import numpy as np
import pandas as pd
from numba import njit
RUN_DIR = Path(__file__).resolve().parent
INPUT = RUN_DIR / 'matched_simulation_bars.csv'
GRID = RUN_DIR / 'candidate_grid.csv'
MARGINS = RUN_DIR / 'margin_schedule.csv'
QTY = 10000.0
SPOT_FEE_RATE = 0.0005
FUTURES_FEE_KRW = 600.0
CLEARING_RATE = 3.157e-06
INITIAL_SPOT = 0.0
INITIAL_FUTURES = 0.0
INITIAL_CAPITAL = 0.0
MAX_POSITIONS = 5
MAX_STAGES = 100
EVENT_CAPACITY = 16384
TRADE_CAPACITY = 4096
EVENT_COLUMNS = 18
TRADE_COLUMNS = 28
RESIDUAL_COLUMNS = 20
SUMMARY_NAMES = ['entry_sets', 'closed_sets', 'winning_sets', 'losing_sets', 'flat_sets', 'realized_spot_gross', 'realized_future_gross', 'unrealized_spot_gross', 'unrealized_future_gross', 'fees', 'slippage', 'net_pnl_before_estimated_close', 'estimated_close_cost', 'net_liquidation_pnl', 'return_pct_total_capital', 'mdd_krw', 'mdd_peak_equity_pct', 'max_spot_cash_used', 'max_initial_margin_required', 'minimum_maintenance_headroom', 'maintenance_breach_events', 'rows_below_maintenance', 'max_simultaneous_sets', 'residual_sets', 'rejected_entries', 'rejected_spot_cash', 'rejected_initial_margin', 'rejected_position_cap', 'average_closed_hold_minutes', 'median_closed_hold_minutes', 'max_closed_hold_minutes', 'completed_cycles', 'largest_completed_cycle_net', 'largest_cycle_share_of_positive_cycle_profit', 'max_futures_loss_from_initial_cash', 'minimum_futures_cash', 'final_spot_cash', 'final_futures_cash', 'final_equity_before_close_cost', 'open_borrowed_usdt', 'borrow_cost_included_krw', 'event_overflow', 'trade_overflow', 'input_rows']
EVENT_NAMES = ['event_code', 'row_index', 'set_id', 'cycle_id', 'stage_k', 'signal_row_index', 'gap_signal_pct', 'spot_price', 'future_price', 'old_future_price', 'new_future_price', 'spot_fee_krw', 'future_fee_krw', 'spot_slippage_krw', 'future_slippage_krw', 'gross_pnl_krw', 'contract_id', 'reason_code']
TRADE_NAMES = ['set_id', 'cycle_id', 'stage_k', 'entry_signal_row_index', 'entry_fill_row_index', 'entry_signal_gap_pct', 'entry_actual_gap_pct', 'entry_level_pct', 'target_gap_pct', 'entry_spot_krw', 'entry_future_krw', 'entry_contract_id', 'exit_signal_row_index', 'exit_fill_row_index', 'exit_signal_gap_pct', 'exit_spot_krw', 'exit_future_krw', 'spot_gross_pnl_krw', 'future_gross_pnl_krw', 'gross_pnl_krw', 'fees_krw', 'slippage_krw', 'net_pnl_krw', 'hold_minutes', 'roll_count', 'exit_reason_code', 'cycle_complete', 'exit_contract_id']
RESIDUAL_NAMES = ['set_id', 'cycle_id', 'stage_k', 'entry_signal_row_index', 'entry_fill_row_index', 'entry_level_pct', 'target_gap_pct', 'entry_spot_krw', 'entry_future_krw', 'contract_id', 'spot_mark_krw', 'future_mark_krw', 'spot_unrealized_gross_krw', 'future_unrealized_gross_krw', 'fees_paid_krw', 'slippage_paid_krw', 'estimated_close_cost_krw', 'net_unrealized_after_close_cost_krw', 'roll_count', 'entry_contract_id']

@njit(cache=True)
def _equity(direction, spot_cash, futures_cash, lots, npos, spot_mark, future_mark):
    spot_component = 0.0
    future_unrealized = 0.0
    for p in range(npos):
        spot_component += direction * QTY * spot_mark
        future_unrealized += direction * (lots[p, 8] - future_mark) * QTY
    return (spot_cash + spot_component + futures_cash + future_unrealized, future_unrealized)

@njit(cache=True)
def _log_event(events, count, code, row_i, set_id, cycle_id, stage, signal_i, gap, spot_px, future_px, old_px, new_px, spot_fee, future_fee, spot_slip, future_slip, gross, contract_id, reason):
    if count < events.shape[0]:
        events[count, 0] = code
        events[count, 1] = row_i
        events[count, 2] = set_id
        events[count, 3] = cycle_id
        events[count, 4] = stage
        events[count, 5] = signal_i
        events[count, 6] = gap
        events[count, 7] = spot_px
        events[count, 8] = future_px
        events[count, 9] = old_px
        events[count, 10] = new_px
        events[count, 11] = spot_fee
        events[count, 12] = future_fee
        events[count, 13] = spot_slip
        events[count, 14] = future_slip
        events[count, 15] = gross
        events[count, 16] = contract_id
        events[count, 17] = reason
        return (count + 1, False)
    return (count, True)

@njit(cache=True)
def _close_slot(lots, npos, slot, row_i, signal_i, signal_gap, spot_px, future_px, direction, times, contract_id, clear_rate, slip_bp, state, trades, events):
    set_id = lots[slot, 0]
    cycle_id = lots[slot, 1]
    stage_k = lots[slot, 2]
    spot_entry = lots[slot, 7]
    future_entry = lots[slot, 8]
    spot_gross = direction * (spot_px - spot_entry) * QTY
    future_segment = direction * (future_entry - future_px) * QTY
    future_gross = lots[slot, 10] + future_segment
    gross = spot_gross + future_gross
    spot_notional = spot_px * QTY
    future_notional = future_px * QTY
    spot_fee = spot_notional * SPOT_FEE_RATE
    future_fee = FUTURES_FEE_KRW + (future_notional * clear_rate if clear_rate > 0 else 0.0)
    spot_slip = spot_notional * slip_bp / 10000.0
    future_slip = future_notional * slip_bp / 10000.0
    lot_fees = lots[slot, 11] + spot_fee + future_fee
    lot_slip = lots[slot, 12] + spot_slip + future_slip
    net = gross - lot_fees - lot_slip
    spot_cash = state[0] + direction * spot_notional - spot_fee - spot_slip
    futures_cash = state[1] + future_segment - future_fee - future_slip
    realized_spot = state[2] + spot_gross
    realized_future = state[3] + future_segment
    total_fees = state[4] + spot_fee + future_fee
    total_slip = state[5] + spot_slip + future_slip
    hold = float(times[row_i] - times[int(lots[slot, 4])])
    closed = int(state[6]) + 1
    wins = int(state[7])
    losses = int(state[8])
    flats = int(state[9])
    hold_sum = state[10] + hold
    max_hold = state[11]
    if net > 1e-08:
        wins += 1
    elif net < -1e-08:
        losses += 1
    else:
        flats += 1
    if hold > max_hold:
        max_hold = hold
    trade_count = int(state[12])
    if trade_count < trades.shape[0]:
        trades[trade_count, 0] = set_id
        trades[trade_count, 1] = cycle_id
        trades[trade_count, 2] = stage_k
        trades[trade_count, 3] = lots[slot, 3]
        trades[trade_count, 4] = lots[slot, 4]
        trades[trade_count, 5] = lots[slot, 14]
        trades[trade_count, 6] = lots[slot, 15]
        trades[trade_count, 7] = lots[slot, 5]
        trades[trade_count, 8] = lots[slot, 6]
        trades[trade_count, 9] = spot_entry
        trades[trade_count, 10] = lots[slot, 16]
        trades[trade_count, 11] = lots[slot, 17]
        trades[trade_count, 12] = signal_i
        trades[trade_count, 13] = row_i
        trades[trade_count, 14] = signal_gap
        trades[trade_count, 15] = spot_px
        trades[trade_count, 16] = future_px
        trades[trade_count, 17] = spot_gross
        trades[trade_count, 18] = future_gross
        trades[trade_count, 19] = gross
        trades[trade_count, 20] = lot_fees
        trades[trade_count, 21] = lot_slip
        trades[trade_count, 22] = net
        trades[trade_count, 23] = hold
        trades[trade_count, 24] = lots[slot, 13]
        trades[trade_count, 25] = 1.0 if signal_i >= 0 else 0.0
        trades[trade_count, 26] = 0.0
        trades[trade_count, 27] = contract_id
        trade_count += 1
    else:
        state[15] = 1.0
    event_count, overflow = _log_event(events, int(state[13]), 2, row_i, set_id, cycle_id, stage_k, signal_i, signal_gap, spot_px, future_px, np.nan, np.nan, spot_fee, future_fee, spot_slip, future_slip, gross, contract_id, 1)
    if overflow:
        state[14] = 1.0
    if npos == 1:
        trades[trade_count - 1, 26] = 1.0
    for p in range(slot, npos - 1):
        for c in range(lots.shape[1]):
            lots[p, c] = lots[p + 1, c]
    npos -= 1
    state[0] = spot_cash
    state[1] = futures_cash
    state[2] = realized_spot
    state[3] = realized_future
    state[4] = total_fees
    state[5] = total_slip
    state[6] = closed
    state[7] = wins
    state[8] = losses
    state[9] = flats
    state[10] = hold_sum
    state[11] = max_hold
    state[12] = trade_count
    state[13] = event_count
    return npos

@njit(cache=True)
def simulate_one(times, month_ids, month_end, contract_ids, direction, exit_mode, entry_e, recovery_r, gap, spot_open, spot_close, future_open, future_close, roll_flag, roll_old_open, roll_old_contract_id, continuous_prev, settlement_due, settlement_price, settlement_spot_mark, initial_rate, maintenance_rate, slippage_bp, add_clearing, reverse_reference, capital_limited, stage_spacing, one_fill_per_bar, stage_capacity, event_capacity, trade_capacity):
    risk = np.zeros(7, dtype=np.float64)
    lots = np.zeros((stage_capacity, 18), dtype=np.float64)
    events = np.zeros((event_capacity, EVENT_COLUMNS), dtype=np.float64)
    trades = np.zeros((trade_capacity, TRADE_COLUMNS), dtype=np.float64)
    residuals = np.zeros((stage_capacity, RESIDUAL_COLUMNS), dtype=np.float64)
    monthly_equity = np.full(10, np.nan, dtype=np.float64)
    npos = 0
    spot_cash = INITIAL_SPOT
    futures_cash = INITIAL_FUTURES
    realized_spot = 0.0
    realized_future = 0.0
    total_fees = 0.0
    total_slip = 0.0
    entry_count = 0
    closed = 0
    wins = 0
    losses = 0
    flats = 0
    hold_sum = 0.0
    max_hold = 0.0
    max_positions = 0
    max_spot_cash_used = 0.0
    max_initial_margin = 0.0
    min_maintenance_headroom = INITIAL_FUTURES
    margin_breach_events = 0
    rows_below_maintenance = 0
    rejected_entries = 0
    rejected_spot_cash = 0
    rejected_initial_margin = 0
    rejected_cap = 0
    event_count = 0
    trade_count = 0
    event_overflow = False
    trade_overflow = False
    state = np.zeros(16, dtype=np.float64)
    set_id_next = 1
    cycle_id_next = 0
    active_cycle_id = -1
    equity_peak = INITIAL_CAPITAL
    mdd = 0.0
    mdd_pct = 0.0
    max_future_loss = 0.0
    minimum_futures_cash = INITIAL_FUTURES
    previous_below_maint = False
    pending_entry_stages = np.zeros(stage_capacity, dtype=np.int64)
    pending_entry_levels = np.zeros(stage_capacity, dtype=np.float64)
    pending_entry_signal_gaps = np.zeros(stage_capacity, dtype=np.float64)
    pending_entry_count = 0
    pending_exit_stages = np.zeros(stage_capacity, dtype=np.int64)
    pending_exit_count = 0
    pending_exit_signal_idx = np.full(stage_capacity, -1, dtype=np.int64)
    pending_exit_signal_gap = np.zeros(stage_capacity, dtype=np.float64)
    pending_basket_exit = False
    basket_signal_idx = -1
    basket_signal_gap = 0.0
    first_level = -entry_e if direction == 1 else entry_e
    fixed_target = first_level + direction * recovery_r
    for i in range(len(times)):
        if roll_flag[i] and npos > 0:
            old_px = roll_old_open[i]
            old_id = roll_old_contract_id[i]
            for p in range(npos):
                old_segment = direction * (lots[p, 8] - old_px) * QTY
                close_fee = FUTURES_FEE_KRW + (old_px * QTY * CLEARING_RATE if add_clearing else 0.0)
                open_fee = FUTURES_FEE_KRW + (future_open[i] * QTY * CLEARING_RATE if add_clearing else 0.0)
                close_slip = old_px * QTY * slippage_bp / 10000.0
                open_slip = future_open[i] * QTY * slippage_bp / 10000.0
                futures_cash += old_segment - close_fee - close_slip - open_fee - open_slip
                realized_future += old_segment
                total_fees += close_fee + open_fee
                total_slip += close_slip + open_slip
                lots[p, 10] += old_segment
                lots[p, 11] += close_fee + open_fee
                lots[p, 12] += close_slip + open_slip
                lots[p, 8] = future_open[i]
                lots[p, 9] = contract_ids[i]
                lots[p, 13] += 1.0
                event_count, overflow = _log_event(events, event_count, 3, i, lots[p, 0], lots[p, 1], lots[p, 2], -1, gap[i], spot_open[i], old_px, old_px, future_open[i], 0.0, close_fee, 0.0, close_slip, old_segment, old_id, 0)
                event_overflow = event_overflow or overflow
                event_count, overflow = _log_event(events, event_count, 4, i, lots[p, 0], lots[p, 1], lots[p, 2], -1, gap[i], spot_open[i], future_open[i], old_px, future_open[i], 0.0, open_fee, 0.0, open_slip, 0.0, contract_ids[i], 0)
                event_overflow = event_overflow or overflow
        if continuous_prev[i]:
            if pending_basket_exit:
                while npos > 0:
                    state[0] = spot_cash
                    state[1] = futures_cash
                    state[2] = realized_spot
                    state[3] = realized_future
                    state[4] = total_fees
                    state[5] = total_slip
                    state[6] = closed
                    state[7] = wins
                    state[8] = losses
                    state[9] = flats
                    state[10] = hold_sum
                    state[11] = max_hold
                    state[12] = trade_count
                    state[13] = event_count
                    state[14] = 1.0 if event_overflow else 0.0
                    state[15] = 1.0 if trade_overflow else 0.0
                    npos = _close_slot(lots, npos, npos - 1, i, basket_signal_idx, basket_signal_gap, spot_open[i], future_open[i], direction, times, contract_ids[i], CLEARING_RATE if add_clearing else 0.0, slippage_bp, state, trades, events)
                    spot_cash = state[0]
                    futures_cash = state[1]
                    realized_spot = state[2]
                    realized_future = state[3]
                    total_fees = state[4]
                    total_slip = state[5]
                    closed = int(state[6])
                    wins = int(state[7])
                    losses = int(state[8])
                    flats = int(state[9])
                    hold_sum = state[10]
                    max_hold = state[11]
                    trade_count = int(state[12])
                    event_count = int(state[13])
                    event_overflow = state[14] > 0.5
                    trade_overflow = state[15] > 0.5
                pending_basket_exit = False
                pending_exit_count = 0
                pending_entry_count = 0
            else:
                for x in range(pending_exit_count):
                    slot = -1
                    for p in range(npos):
                        if int(lots[p, 2]) == pending_exit_stages[x]:
                            slot = p
                            break
                    if slot >= 0:
                        state[0] = spot_cash
                        state[1] = futures_cash
                        state[2] = realized_spot
                        state[3] = realized_future
                        state[4] = total_fees
                        state[5] = total_slip
                        state[6] = closed
                        state[7] = wins
                        state[8] = losses
                        state[9] = flats
                        state[10] = hold_sum
                        state[11] = max_hold
                        state[12] = trade_count
                        state[13] = event_count
                        state[14] = 1.0 if event_overflow else 0.0
                        state[15] = 1.0 if trade_overflow else 0.0
                        npos = _close_slot(lots, npos, slot, i, pending_exit_signal_idx[x], pending_exit_signal_gap[x], spot_open[i], future_open[i], direction, times, contract_ids[i], CLEARING_RATE if add_clearing else 0.0, slippage_bp, state, trades, events)
                        spot_cash = state[0]
                        futures_cash = state[1]
                        realized_spot = state[2]
                        realized_future = state[3]
                        total_fees = state[4]
                        total_slip = state[5]
                        closed = int(state[6])
                        wins = int(state[7])
                        losses = int(state[8])
                        flats = int(state[9])
                        hold_sum = state[10]
                        max_hold = state[11]
                        trade_count = int(state[12])
                        event_count = int(state[13])
                        event_overflow = state[14] > 0.5
                        trade_overflow = state[15] > 0.5
                pending_exit_count = 0
                for x in range(pending_entry_count):
                    stage_k = pending_entry_stages[x]
                    level = pending_entry_levels[x]
                    duplicate = False
                    for p in range(npos):
                        if int(lots[p, 2]) == stage_k:
                            duplicate = True
                            break
                    reason = 0
                    if duplicate:
                        reason = 1
                    elif capital_limited and npos >= 5:
                        reason = 2
                        rejected_cap += 1
                    spot_notional = spot_open[i] * QTY
                    future_notional = future_open[i] * QTY
                    spot_fee = spot_notional * SPOT_FEE_RATE
                    future_fee = FUTURES_FEE_KRW + (future_notional * CLEARING_RATE if add_clearing else 0.0)
                    spot_slip = spot_notional * slippage_bp / 10000.0
                    future_slip = future_notional * slippage_bp / 10000.0
                    if capital_limited and (reason == 0 and direction == 1 and (not reverse_reference) and (spot_cash < spot_notional + spot_fee + spot_slip - 1e-07)):
                        reason = 3
                        rejected_spot_cash += 1
                    unreal_f = 0.0
                    for p in range(npos):
                        unreal_f += direction * (lots[p, 8] - future_open[i]) * QTY
                    future_equity = futures_cash + unreal_f
                    required_initial = (npos + 1) * future_notional * initial_rate[i]
                    if capital_limited and (reason == 0 and future_equity - future_fee - future_slip < required_initial - 1e-07):
                        reason = 4
                        rejected_initial_margin += 1
                    if reason != 0:
                        rejected_entries += 1
                        event_count, overflow = _log_event(events, event_count, 6, i, 0, active_cycle_id, stage_k, i - 1, pending_entry_signal_gaps[x], spot_open[i], future_open[i], np.nan, np.nan, spot_fee, future_fee, spot_slip, future_slip, 0.0, contract_ids[i], reason)
                        event_overflow = event_overflow or overflow
                        continue
                    if npos == 0:
                        cycle_id_next += 1
                        active_cycle_id = cycle_id_next
                    set_id = set_id_next
                    set_id_next += 1
                    actual_gap = (spot_open[i] / future_open[i] - 1.0) * 100.0
                    lots[npos, 0] = set_id
                    lots[npos, 1] = active_cycle_id
                    lots[npos, 2] = stage_k
                    lots[npos, 3] = i - 1
                    lots[npos, 4] = i
                    lots[npos, 5] = level
                    lots[npos, 6] = level + direction * recovery_r if exit_mode == 0 else fixed_target
                    lots[npos, 7] = spot_open[i]
                    lots[npos, 8] = future_open[i]
                    lots[npos, 9] = contract_ids[i]
                    lots[npos, 10] = 0.0
                    lots[npos, 11] = spot_fee + future_fee
                    lots[npos, 12] = spot_slip + future_slip
                    lots[npos, 13] = 0.0
                    lots[npos, 14] = pending_entry_signal_gaps[x]
                    lots[npos, 15] = actual_gap
                    lots[npos, 16] = future_open[i]
                    lots[npos, 17] = contract_ids[i]
                    spot_cash -= direction * spot_notional + spot_fee + spot_slip
                    futures_cash -= future_fee + future_slip
                    total_fees += spot_fee + future_fee
                    total_slip += spot_slip + future_slip
                    npos += 1
                    entry_count += 1
                    if npos > max_positions:
                        max_positions = npos
                    if direction == 1 and INITIAL_SPOT - spot_cash > max_spot_cash_used:
                        max_spot_cash_used = INITIAL_SPOT - spot_cash
                    event_count, overflow = _log_event(events, event_count, 1, i, set_id, active_cycle_id, stage_k, i - 1, pending_entry_signal_gaps[x], spot_open[i], future_open[i], np.nan, np.nan, spot_fee, future_fee, spot_slip, future_slip, 0.0, contract_ids[i], 0)
                    event_overflow = event_overflow or overflow
                    if one_fill_per_bar:
                        break
                pending_entry_count = 0
        equity, future_unreal = _equity(direction, spot_cash, futures_cash, lots, npos, spot_open[i], future_open[i])
        update_risk(risk, direction, lots, npos, spot_open[i], future_open[i], spot_cash, futures_cash, initial_rate[i], maintenance_rate[i], equity - INITIAL_CAPITAL)
        if equity > equity_peak:
            equity_peak = equity
        if equity_peak - equity > mdd:
            mdd = equity_peak - equity
            mdd_pct = mdd / equity_peak * 100.0 if equity_peak > 0 else 0.0
        future_equity = futures_cash + future_unreal
        initial_need = npos * future_open[i] * QTY * initial_rate[i]
        maint_headroom = future_equity - npos * future_open[i] * QTY * maintenance_rate[i]
        if initial_need > max_initial_margin:
            max_initial_margin = initial_need
        if maint_headroom < min_maintenance_headroom:
            min_maintenance_headroom = maint_headroom
        below = maint_headroom < 0.0
        if below:
            rows_below_maintenance += 1
            if not previous_below_maint:
                margin_breach_events += 1
        previous_below_maint = below
        if INITIAL_FUTURES - future_equity > max_future_loss:
            max_future_loss = INITIAL_FUTURES - future_equity
        if futures_cash < minimum_futures_cash:
            minimum_futures_cash = futures_cash
        equity, future_unreal = _equity(direction, spot_cash, futures_cash, lots, npos, spot_close[i], future_close[i])
        update_risk(risk, direction, lots, npos, spot_close[i], future_close[i], spot_cash, futures_cash, initial_rate[i], maintenance_rate[i], equity - INITIAL_CAPITAL)
        if equity > equity_peak:
            equity_peak = equity
        if equity_peak - equity > mdd:
            mdd = equity_peak - equity
            mdd_pct = mdd / equity_peak * 100.0 if equity_peak > 0 else 0.0
        future_equity = futures_cash + future_unreal
        initial_need = npos * future_close[i] * QTY * initial_rate[i]
        maint_headroom = future_equity - npos * future_close[i] * QTY * maintenance_rate[i]
        if initial_need > max_initial_margin:
            max_initial_margin = initial_need
        if maint_headroom < min_maintenance_headroom:
            min_maintenance_headroom = maint_headroom
        below = maint_headroom < 0.0
        if below:
            rows_below_maintenance += 1
            if not previous_below_maint:
                margin_breach_events += 1
        previous_below_maint = below
        if INITIAL_FUTURES - future_equity > max_future_loss:
            max_future_loss = INITIAL_FUTURES - future_equity
        if futures_cash < minimum_futures_cash:
            minimum_futures_cash = futures_cash
        if settlement_due[i]:
            settle_px = settlement_price[i]
            settle_spot = settlement_spot_mark[i]
            for p in range(npos):
                variation = direction * (lots[p, 8] - settle_px) * QTY
                futures_cash += variation
                realized_future += variation
                lots[p, 10] += variation
                lots[p, 8] = settle_px
                event_count, overflow = _log_event(events, event_count, 5, i, lots[p, 0], lots[p, 1], lots[p, 2], -1, gap[i], settle_spot, settle_px, np.nan, np.nan, 0.0, 0.0, 0.0, 0.0, variation, contract_ids[i], 0)
                event_overflow = event_overflow or overflow
            equity, future_unreal = _equity(direction, spot_cash, futures_cash, lots, npos, settle_spot, settle_px)
            update_risk(risk, direction, lots, npos, settle_spot, settle_px, spot_cash, futures_cash, initial_rate[i], maintenance_rate[i], equity - INITIAL_CAPITAL)
            if equity > equity_peak:
                equity_peak = equity
            if equity_peak - equity > mdd:
                mdd = equity_peak - equity
                mdd_pct = mdd / equity_peak * 100.0 if equity_peak > 0 else 0.0
            future_equity = futures_cash + future_unreal
            initial_need = npos * settle_px * QTY * initial_rate[i]
            maint_headroom = future_equity - npos * settle_px * QTY * maintenance_rate[i]
            if initial_need > max_initial_margin:
                max_initial_margin = initial_need
            if maint_headroom < min_maintenance_headroom:
                min_maintenance_headroom = maint_headroom
            below = maint_headroom < 0.0
            if below:
                rows_below_maintenance += 1
                if not previous_below_maint:
                    margin_breach_events += 1
            previous_below_maint = below
            if INITIAL_FUTURES - future_equity > max_future_loss:
                max_future_loss = INITIAL_FUTURES - future_equity
            if futures_cash < minimum_futures_cash:
                minimum_futures_cash = futures_cash
        can_fill_next = i + 1 < len(times) and continuous_prev[i + 1]
        if can_fill_next and npos > 0 and (not roll_flag[i]):
            if exit_mode == 1:
                reached = direction == 1 and gap[i] >= fixed_target - 1e-12 or (direction == -1 and gap[i] <= fixed_target + 1e-12)
                if reached:
                    pending_basket_exit = True
                    basket_signal_idx = i
                    basket_signal_gap = gap[i]
            else:
                pending_exit_count = 0
                for p in range(npos):
                    target = lots[p, 6]
                    reached = direction == 1 and gap[i] >= target - 1e-12 or (direction == -1 and gap[i] <= target + 1e-12)
                    if reached and pending_exit_count < stage_capacity:
                        pending_exit_stages[pending_exit_count] = int(lots[p, 2])
                        pending_exit_signal_idx[pending_exit_count] = i
                        pending_exit_signal_gap[pending_exit_count] = gap[i]
                        pending_exit_count += 1
        if can_fill_next and (not roll_flag[i]) and (not pending_basket_exit) and continuous_prev[i] and (i > 0):
            prev_gap = gap[i - 1]
            curr_gap = gap[i]
            if direction == 1:
                k_min = int(np.floor(-(prev_gap + entry_e) / stage_spacing + 1e-10)) + 1
                k_max = int(np.floor((-entry_e - curr_gap) / stage_spacing + 1e-10))
            else:
                k_min = int(np.floor((prev_gap - entry_e) / stage_spacing + 1e-10)) + 1
                k_max = int(np.floor((curr_gap - entry_e) / stage_spacing + 1e-10))
            if k_min < 0:
                k_min = 0
            if k_max >= stage_capacity:
                raise RuntimeError('STAGE_STORAGE_OVERFLOW')
            if k_max >= k_min:
                for k in range(k_min, k_max + 1):
                    active = False
                    for p in range(npos):
                        if int(lots[p, 2]) == k:
                            active = True
                            break
                    if not active and pending_entry_count < stage_capacity:
                        pending_entry_stages[pending_entry_count] = k
                        pending_entry_levels[pending_entry_count] = -entry_e - stage_spacing * k if direction == 1 else entry_e + stage_spacing * k
                        pending_entry_signal_gaps[pending_entry_count] = curr_gap
                        pending_entry_count += 1
        if month_end[i]:
            if settlement_due[i]:
                eq_month, _ = _equity(direction, spot_cash, futures_cash, lots, npos, settlement_spot_mark[i], settlement_price[i])
            else:
                eq_month, _ = _equity(direction, spot_cash, futures_cash, lots, npos, spot_close[i], future_close[i])
            if month_ids[i] >= 0 and month_ids[i] < monthly_equity.shape[0]:
                monthly_equity[month_ids[i]] = eq_month
    last = len(times) - 1
    if settlement_due[last]:
        final_spot = settlement_spot_mark[last]
        final_future = settlement_price[last]
    else:
        final_spot = spot_close[last]
        final_future = future_close[last]
    final_equity, future_unreal = _equity(direction, spot_cash, futures_cash, lots, npos, final_spot, final_future)
    unreal_spot = direction * npos * QTY * final_spot
    unreal_future = future_unreal
    liquidation_cost = 0.0
    open_borrowed = 0.0
    for p in range(npos):
        spot_notional = final_spot * QTY
        future_notional = final_future * QTY
        spot_fee = spot_notional * SPOT_FEE_RATE
        future_fee = FUTURES_FEE_KRW + (future_notional * CLEARING_RATE if add_clearing else 0.0)
        spot_slip = spot_notional * slippage_bp / 10000.0
        future_slip = future_notional * slippage_bp / 10000.0
        liquidation_cost += spot_fee + future_fee + spot_slip + future_slip
        if direction == -1:
            open_borrowed += QTY
        residuals[p, 0] = lots[p, 0]
        residuals[p, 1] = lots[p, 1]
        residuals[p, 2] = lots[p, 2]
        residuals[p, 3] = lots[p, 3]
        residuals[p, 4] = lots[p, 4]
        residuals[p, 5] = lots[p, 5]
        residuals[p, 6] = lots[p, 6]
        residuals[p, 7] = lots[p, 7]
        residuals[p, 8] = lots[p, 8]
        residuals[p, 9] = lots[p, 9]
        residuals[p, 10] = final_spot
        residuals[p, 11] = final_future
        residuals[p, 12] = direction * (final_spot - lots[p, 7]) * QTY
        residuals[p, 13] = lots[p, 10] + direction * (lots[p, 8] - final_future) * QTY
        residuals[p, 14] = lots[p, 11]
        residuals[p, 15] = lots[p, 12]
        residuals[p, 16] = spot_fee + future_fee + spot_slip + future_slip
        residuals[p, 17] = residuals[p, 12] + residuals[p, 13] - residuals[p, 14] - residuals[p, 15] - residuals[p, 16]
        residuals[p, 18] = lots[p, 13]
        residuals[p, 19] = lots[p, 17]
    net_pnl = final_equity - INITIAL_CAPITAL
    net_liq = net_pnl - liquidation_cost
    summary = np.zeros(52, dtype=np.float64)
    summary[0] = entry_count
    summary[1] = closed
    summary[2] = wins
    summary[3] = losses
    summary[4] = flats
    summary[5] = realized_spot
    summary[6] = realized_future
    summary[7] = unreal_spot
    summary[8] = unreal_future
    summary[9] = total_fees
    summary[10] = total_slip
    summary[11] = net_pnl
    summary[12] = liquidation_cost
    summary[13] = net_liq
    summary[14] = net_liq / INITIAL_CAPITAL * 100.0 if INITIAL_CAPITAL > 0 else np.nan
    summary[15] = mdd
    summary[16] = mdd_pct
    summary[17] = max_spot_cash_used
    summary[18] = max_initial_margin
    summary[19] = min_maintenance_headroom
    summary[20] = margin_breach_events
    summary[21] = rows_below_maintenance
    summary[22] = max_positions
    summary[23] = npos
    summary[24] = rejected_entries
    summary[25] = rejected_spot_cash
    summary[26] = rejected_initial_margin
    summary[27] = rejected_cap
    summary[28] = hold_sum / closed if closed > 0 else np.nan
    summary[29] = np.nan
    summary[30] = max_hold
    summary[31] = cycle_id_next
    summary[32] = np.nan
    summary[33] = np.nan
    summary[34] = max_future_loss
    summary[35] = minimum_futures_cash
    summary[36] = spot_cash
    summary[37] = futures_cash
    summary[38] = final_equity
    summary[39] = open_borrowed
    summary[40] = 0.0
    summary[41] = 1.0 if event_overflow else 0.0
    summary[42] = 1.0 if trade_overflow else 0.0
    summary[43] = len(times)
    summary[44] = net_liq
    summary[45:52] = risk
    return (summary, trades[:trade_count].copy(), events[:event_count].copy(), residuals[:npos].copy(), monthly_equity)

def _month_indices(business_dates: pd.Series) -> tuple[np.ndarray, np.ndarray, list[str]]:
    months = business_dates.astype(str).str.slice(0, 6)
    unique = sorted(months.unique())
    mapper = {m: i for i, m in enumerate(unique)}
    ids = months.map(mapper).to_numpy(dtype=np.int64)
    month_end = np.zeros(len(ids), dtype=np.bool_)
    for month in unique:
        ix = np.flatnonzero(months.to_numpy() == month)
        if len(ix):
            month_end[ix[-1]] = True
    return (ids, month_end, unique)

def load_arrays() -> dict[str, Any]:
    frame = pd.read_csv(INPUT, dtype={'business_date': str, 'contract_code_kis': str, 'contract_code_krx': str, 'roll_old_kis': str, 'roll_old_krx': str}).fillna('')
    margin = pd.read_csv(MARGINS, dtype=str).fillna('')
    margin['effective_from'] = pd.to_datetime(margin['effective_from'])
    margin['effective_to'] = pd.to_datetime(margin['effective_to'])
    dates = pd.to_datetime(frame['business_date'], format='%Y%m%d')
    initial_pct = np.full(len(frame), np.nan, dtype=np.float64)
    maintenance_pct = np.full(len(frame), np.nan, dtype=np.float64)
    inferred_margin_dates: set[str] = set()
    for row in margin.to_dict('records'):
        mask = (dates >= row['effective_from']) & (dates <= row['effective_to'])
        initial_pct[mask.to_numpy()] = float(row['customer_initial_margin_pct'])
        maintenance_pct[mask.to_numpy()] = float(row['maintenance_margin_pct'])
        if row['source_status'] == 'INFERRED_ADJACENT_OFFICIAL_SCHEDULES':
            inferred_margin_dates.update(frame.loc[mask, 'business_date'].astype(str).unique())
    if np.isnan(initial_pct).any() or np.isnan(maintenance_pct).any():
        missing_dates = frame.loc[np.isnan(initial_pct), 'business_date'].drop_duplicates().tolist()
        raise RuntimeError(f'Historical margin schedule does not cover all simulated dates: {missing_dates[:5]}')
    codes = sorted({c for c in frame['contract_code_kis'].tolist() + frame['roll_old_kis'].tolist() if c})
    code_to_id = {code: i + 1 for i, code in enumerate(codes)}
    ids = frame['contract_code_kis'].map(code_to_id).fillna(0).to_numpy(dtype=np.int64)
    old_ids = frame['roll_old_kis'].map(code_to_id).fillna(0).to_numpy(dtype=np.int64)
    month_ids, month_end, month_names = _month_indices(frame['business_date'])
    arrays = {'frame': frame, 'contract_codes': codes, 'contract_code_to_id': code_to_id, 'month_names': month_names, 'inferred_margin_dates': sorted(inferred_margin_dates), 'times': frame['epoch_minute'].to_numpy(dtype=np.int64), 'month_ids': month_ids, 'month_end': month_end, 'contract_ids': ids, 'old_contract_ids': old_ids, 'continuous_prev': frame['continuous_prev'].astype(bool).to_numpy(dtype=np.bool_), 'roll_flag': frame['contract_roll'].astype(bool).to_numpy(dtype=np.bool_), 'settlement_due': frame['settlement_due'].astype(bool).to_numpy(dtype=np.bool_), 'gap': frame['raw_gap_close_pct'].to_numpy(dtype=np.float64), 'spot_open': frame['spot_open'].to_numpy(dtype=np.float64), 'spot_close': frame['spot_close'].to_numpy(dtype=np.float64), 'future_open': frame['future_open'].to_numpy(dtype=np.float64), 'future_close': frame['future_close'].to_numpy(dtype=np.float64), 'roll_old_open': pd.to_numeric(frame['roll_old_open'], errors='coerce').fillna(np.nan).to_numpy(dtype=np.float64), 'settlement_price': pd.to_numeric(frame['official_daily_settlement'], errors='coerce').to_numpy(dtype=np.float64), 'settlement_spot_mark': pd.to_numeric(frame['settlement_spot_mark'], errors='coerce').to_numpy(dtype=np.float64), 'initial_rate': initial_pct / 100.0, 'maintenance_rate': maintenance_pct / 100.0}
    for name in ('gap', 'spot_open', 'spot_close', 'future_open', 'future_close'):
        if not np.isfinite(arrays[name]).all():
            raise RuntimeError(f'Non-finite observed market price in simulation input: {name}')
    settlement_invalid = arrays['settlement_due'] & (~np.isfinite(arrays['settlement_price']) | ~np.isfinite(arrays['settlement_spot_mark']))
    if settlement_invalid.any():
        raise RuntimeError(f'Official settlement mark is incomplete on {int(settlement_invalid.sum())} rows')
    if arrays['settlement_due'].sum() < 1:
        raise RuntimeError('No valid official settlement marks are available in the simulation input')
    return arrays

def run_candidate(arrays: dict[str, Any], direction: str, exit_mode: str, entry_e: float, recovery_r: float, slippage_bp: float, add_clearing: bool):
    dir_sign = 1 if direction == 'discount_long' else -1
    mode_id = 0 if exit_mode == 'individual' else 1
    return simulate_one(arrays['times'], arrays['month_ids'], arrays['month_end'], arrays['contract_ids'], dir_sign, mode_id, entry_e, recovery_r, arrays['gap'], arrays['spot_open'], arrays['spot_close'], arrays['future_open'], arrays['future_close'], arrays['roll_flag'], arrays['roll_old_open'], arrays['old_contract_ids'], arrays['continuous_prev'], arrays['settlement_due'], arrays['settlement_price'], arrays['settlement_spot_mark'], arrays['initial_rate'], arrays['maintenance_rate'], slippage_bp, add_clearing, direction == 'premium_short')

def metric_record(summary: np.ndarray, trades: np.ndarray, direction: str, exit_mode: str, entry_e: float, recovery_r: float, slippage_bp: float, add_clearing: bool, candidate_id: str) -> dict[str, Any]:
    row = {name: float(summary[i]) if np.isfinite(summary[i]) else '' for i, name in enumerate(SUMMARY_NAMES)}
    if len(trades):
        holds = np.sort(trades[:, 23])
        pnl = trades[:, 22]
        pos = pnl[pnl > 1e-08]
        neg = pnl[pnl < -1e-08]
        pf = float(pos.sum() / -neg.sum()) if len(neg) else 'INF' if len(pos) else ''
        cycle_complete = trades[:, 26] > 0.5
        cycle_rows = trades[cycle_complete]
        if len(cycle_rows):
            by_cycle: dict[int, float] = {}
            for trade in trades:
                cycle_id = int(trade[1])
                by_cycle[cycle_id] = by_cycle.get(cycle_id, 0.0) + float(trade[22])
            completed_ids = {int(trade[1]) for trade in cycle_rows}
            cycle_pnls = np.array([by_cycle[cycle_id] for cycle_id in completed_ids], dtype=float)
            positive_cycle_sum = float(cycle_pnls[cycle_pnls > 0].sum())
            largest_cycle = float(cycle_pnls.max())
            row['completed_cycles'] = len(completed_ids)
            row['largest_completed_cycle_net'] = largest_cycle
            row['largest_cycle_share_of_positive_cycle_profit'] = largest_cycle / positive_cycle_sum if positive_cycle_sum > 0 else ''
            row['completed_cycle_net_ex_largest'] = float(cycle_pnls.sum() - largest_cycle)
        row['median_closed_hold_minutes'] = float(np.median(holds))
        row['profit_factor_closed_sets'] = pf
        row['win_rate_closed_sets_pct'] = float((pnl > 1e-08).sum() / len(pnl) * 100.0)
        row['average_net_per_closed_set_krw'] = float(pnl.mean())
    else:
        row['profit_factor_closed_sets'] = ''
        row['win_rate_closed_sets_pct'] = ''
        row['average_net_per_closed_set_krw'] = ''
        row['median_closed_hold_minutes'] = ''
        row['completed_cycle_net_ex_largest'] = ''
    row.update({'candidate_id': candidate_id, 'direction': direction, 'exit_mode': exit_mode, 'entry_e_pp': entry_e, 'recovery_r_pp': recovery_r, 'add_spacing_pp': 0.2, 'slippage_bps_per_side_per_leg': slippage_bp, 'fee_policy': '600_PLUS_CLEARING_ASSUMED' if add_clearing else '600_TOTAL_ASSUMED', 'position_unit': '10000 USDT + 1 KRX USD futures contract per set', 'result_class': 'PAPER_NEXT_OPEN_PROXY_COST_ASSUMED' if direction == 'discount_long' else 'REFERENCE_ONLY_BORROW_UNVERIFIED'})
    return row
