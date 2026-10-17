# /// script
# requires-python = ">=3.12"
# dependencies = ["numpy"]
# ///
from __future__ import annotations

from dataclasses import asdict

import numpy as np

from unlimited_execution import Condition, Execution, Market


def summarize(case: Condition, result: Execution, market: Market):
    groups: dict[int, list[int]] = {}
    residual_groups: dict[int, list[int]] = {}
    for index, row in enumerate(result.trades):
        groups.setdefault(int(row[1]), []).append(index)
    for index, row in enumerate(result.residuals):
        residual_groups.setdefault(int(row[1]), []).append(index)
    cycles = []
    returns = []
    for cycle_id in sorted(set(groups) | set(residual_groups)):
        closed = result.trades[groups.get(cycle_id, [])]
        remaining = result.residuals[residual_groups.get(cycle_id, [])]
        complete = len(remaining) == 0 and len(closed) > 0 and bool(closed[:, 26].max())
        notional = float(closed[:, 9].sum() * 10000 + remaining[:, 7].sum() * 10000)
        closed_net = float(closed[:, 22].sum())
        open_net = float(remaining[:, 17].sum())
        net = closed_net + open_net
        entry_indices = [int(row[4]) for row in closed] + [int(row[4]) for row in remaining]
        start = min(entry_indices)
        end = int(closed[:, 13].max()) if complete else len(market.timestamps) - 1
        rate = 100 * net / notional
        row = {"candidate_id": case.candidate_id, "cycle_id": cycle_id, "complete": complete,
               "entry_notional_krw": notional, "cycle_net_pnl_krw": net,
               "closed_net_pnl_krw": closed_net, "residual_net_after_close_cost_krw": open_net,
               "cycle_return_pct": rate, "closed_sets": len(closed), "open_sets": len(remaining),
               "first_entry_kst": market.timestamps[start], "exit_or_evaluation_kst": market.timestamps[end],
               "hold_minutes": int(market.vectors[0][end] - market.vectors[0][start])}
        cycles.append(row)
        if complete:
            returns.append((end, cycle_id, rate, row["hold_minutes"]))
    running, peak, drawdown = 0.0, 0.0, 0.0
    for _, _, rate, _ in sorted(returns):
        running += rate
        peak = max(peak, running)
        drawdown = max(drawdown, peak - running)
    s = result.summary
    rates = [value[2] for value in returns]
    positives = sum(max(rate, 0) for rate in rates)
    row = asdict(case)
    row.update({"direction": "discount_long" if case.direction == 1 else "premium_short",
                "exit_mode": "individual" if case.exit_mode == 0 else "fixed_basket",
                "fee_policy": "600_PLUS_CLEARING_ASSUMED" if case.clearing else "600_TOTAL_ASSUMED",
                "entry_sets": int(s[0]), "closed_sets": len(result.trades), "completed_cycles": len(rates),
                "cumulative_simple_return_pct": sum(rates) if rates else None,
                "win_rate_cycles_pct": 100 * sum(rate > 1e-10 for rate in rates) / len(rates) if rates else None,
                "average_cycle_return_pct": sum(rates) / len(rates) if rates else None,
                "completed_cycle_mdd_pp": drawdown, "worst_single_cycle_return_pct": min(rates) if rates else None,
                "max_open_evaluation_loss_krw": float(s[45]), "mdd_krw": float(s[15]),
                "max_simultaneous_contracts": int(s[22]), "max_initial_margin_krw": float(s[18]),
                "max_maintenance_margin_krw": float(s[47]), "max_gross_spot_entry_notional_krw": float(s[46]),
                "required_spot_cash_krw": float(s[50]), "required_futures_cash_krw": float(s[48]),
                "max_futures_adverse_krw": float(s[34]), "max_adverse_gap_pp": float(s[49]),
                "longest_hold_minutes": max((item["hold_minutes"] for item in cycles), default=0),
                "residual_cycles": sum(not item["complete"] for item in cycles), "residual_sets": len(result.residuals),
                "residual_unrealized_gross_krw": float((result.residuals[:, 12] + result.residuals[:, 13]).sum()),
                "residual_net_after_close_cost_krw": float(result.residuals[:, 17].sum()),
                "incomplete_cycle_net_after_close_cost_krw": sum(item["cycle_net_pnl_krw"] for item in cycles if not item["complete"]),
                "fees_krw": float(s[9]), "slippage_krw": float(s[10]), "funding_krw": 0,
                "total_mark_net_after_close_cost_krw": float(s[13]),
                "cash_rejections": int(s[25]), "margin_rejections": int(s[26]), "cap_rejections": int(s[27]),
                "stage_capacity": result.stage_capacity, "buffer_retries": result.retries,
                "event_capacity": result.event_capacity, "trade_capacity": result.trade_capacity,
                "largest_cycle_share_of_positive_returns": max(rates) / positives if positives > 0 else None,
                "sample_warning": len(rates) < 3, "borrow_status": "NOT_APPLICABLE" if case.direction == 1 else "UNVERIFIED_THEORETICAL_ONLY",
                "execution_status": "NEXT_CONTINUOUS_MINUTE_OPEN_PROXY_NOT_ORDERBOOK_VERIFIED"})
    active: dict[int, tuple[int, int]] = {}
    for event in result.events:
        code, set_id = int(event[0]), int(event[2])
        if code == 1:
            key = (int(event[3]), int(event[4]))
            assert key not in active.values(), "Duplicate active stage entry"
            active[set_id] = key
        if code == 2:
            assert set_id in active
            del active[set_id]
    assert set(active) == {int(value[0]) for value in result.residuals}
    assert abs(sum(item["cycle_net_pnl_krw"] for item in cycles) - float(s[13])) < 0.01
    return row, cycles
