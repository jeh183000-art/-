# /// script
# requires-python = "==3.12.0"
# dependencies = ["numpy==2.2.6", "numba==0.61.2", "pandas==3.0.1"]
# ///
# Run: existing Python312/python.exe -B bootstrap.py register|run
from __future__ import annotations

import csv
import gzip
import hashlib
import importlib.util
import json
import os
import platform
import subprocess
import sys
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

import numpy as np

from signals import Rule, grid, prepare, trailing
from single_core import simulate

ROOT: Final = Path(__file__).resolve().parents[1]
SOURCE: Final = ROOT.parents[1] / "shared/approved_20261016_01"
BATCH: Final = ROOT / "batch_0001"
TRADE_NAMES: Final = "entry_signal_index entry_index exit_signal_index exit_index direction entry_spot entry_future exit_spot exit_future spot_gross future_gross fees slippage net hold_minutes roll_count frozen_target_gap cycle_id".split()
EVENT_NAMES: Final = "event_code row_index cycle_id direction spot_price future_price spot_gross_delta future_gross_delta spot_fee future_fee spot_slippage future_slippage contract_id signal_row_index".split()


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_csv(path: Path, rows: list, fields: list[str] | None = None) -> None:
    names = fields if fields is not None else list(rows[0])
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "xt", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=names)
        writer.writeheader()
        writer.writerows(rows)


def register() -> None:
    assert not (ROOT / "preregistration.json").exists()
    specs = [asdict(r) for r in grid()]
    settings = {
        "study_id": ROOT.name, "registered_utc": datetime.now(UTC).isoformat(),
        "data_scope": "Existing approved EXPLORATORY KRX business dates 2026-01-01..2026-10-15; protected Final OOS excluded",
        "conditions": specs, "batch_size": 50, "stop_after_batch": 1,
        "position": "One global slot per candidate; fixed 10000 USDT and opposite 1 KRX USD futures contract; no add/reentry while held; candidates never combined as concurrent orders",
        "score": "Unrounded arithmetic sum of completed cycle net / absolute original spot entry notional *100; incomplete excluded",
        "costs": {"spot_fee_per_side": 0.0005, "future_fee_per_side_krw": 600, "clearing_rate": 0.000003157, "slippage_bp_per_side_per_leg": 2, "perpetual_funding": "NOT_APPLICABLE", "reverse_borrow": "UNVERIFIED_AND_NOT_INCLUDED"},
        "execution": "Signal at completed close; next contiguous observed minute open only. Gap-end signals cancelled, no interpolation. No signal on contract-roll row. Live fills unverified.",
        "roll": "Hold one economic set; close old and open new futures at observed same-time contract prices; both fees/slippage included. Raw absolute targets unchanged. Trailing windows reset at roll; no back-adjusted execution price.",
        "causality": "Trailing mean/median/population std/quantiles use the preceding 60 or 240 observed bars, excluding current; restart warmup at roll. Threshold entry requires a fresh crossing, not an initial already-extreme bar.",
        "mean_median_exit": "Entry-signal baseline frozen; target=entry-signal gap + fraction*(lagged center-entry-signal gap)",
        "distribution_exit": "Lagged rolling median for q10/q90 entries; lagged zscore>=0 in oriented direction for z=-1.5 entries; current baseline uses only past bars",
        "reversal": "Arm only while flat on fresh threshold crossing; confirm recovery from subsequently observed trough; expire at 240 calendar minutes, gaps, rollover, or return through zero",
        "risk_exits": "Separate variants from E=.8/R=.5 baseline: 240 calendar-minute limit; .5pp further gap loss; .2% net liquidation profit / -.5% net liquidation stop; 120 minutes without .01pp favorable progress",
        "combined": "Both directions share one slot; simultaneous tie uses long first. No separate independent signal portfolio is summed.",
        "residual": "Mark open set separately; hypothetical final-bar close cost and return only as auxiliary score, never primary completed score",
        "price_source_sha256": digest(SOURCE / "matched_simulation_bars.csv"),
        "loader_sha256": digest(SOURCE / "paper_engine.py"),
        "margin_schedule_sha256": digest(SOURCE / "margin_schedule.csv"),
        "code_sha256": {p.name: digest(p) for p in sorted((ROOT / "code").glob("*.py"))},
        "exploration_plan": "First broad 50 across A10/B8/C8/D8/E6/F8/G2. No result-driven refinement in this run. Future separate preregistered batches may vary one dimension near promising rules. All failures and prior best retained.",
    }
    ROOT.joinpath("preregistration.json").write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
    write_csv(ROOT / "condition_grid.csv", specs)
    print("PREREGISTERED_50_NO_SIMULATION", flush=True)


def load_market():
    reg = json.loads((ROOT / "preregistration.json").read_text())
    assert digest(SOURCE / "matched_simulation_bars.csv") == reg["price_source_sha256"]
    assert digest(SOURCE / "paper_engine.py") == reg["loader_sha256"]
    assert all(digest(ROOT / "code" / n) == h for n, h in reg["code_sha256"].items())
    spec = importlib.util.spec_from_file_location("approved_single_set_loader", SOURCE / "paper_engine.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    a = module.load_arrays()
    names = ("times month_ids month_end contract_ids gap spot_open spot_close future_open future_close roll_flag roll_old_open old_contract_ids continuous_prev settlement_due settlement_price settlement_spot_mark initial_rate maintenance_rate").split()
    return tuple(a[k] for k in names), a["frame"], a["contract_codes"]


def run_batch() -> None:
    assert not BATCH.exists(), "Never recalculate or overwrite an existing batch"
    lock = ROOT / "worker.lock"
    with lock.open("x", encoding="utf8") as stream:
        stream.write(str(os.getpid()))
    try:
        v, frame, codes = load_market()
        BATCH.mkdir()
        (BATCH / "raw").mkdir()
        stats = {w: trailing(v[4], v[9], w) for w in (60, 240)}
        results, cycles, event_rows, residuals, monthly, risk_rows, audits = [], [], [], [], [], [], []
        rules = [Rule(**r) for r in json.loads((ROOT / "preregistration.json").read_text())["conditions"]]
        for rule in rules:
            es, el, er, center, mode = prepare(rule, v, stats)
            tr, ev, residual, risk, equity, marks = simulate(v, es, el, er, center, mode, rule.recovery, rule.fraction, rule.confirm, rule.max_hold, rule.gap_stop, rule.pnl_profit, rule.pnl_stop, rule.stall)
            np.savez_compressed(BATCH / "raw" / (rule.candidate_id + ".npz"), trades=tr, events=ev, residual=residual, risk=risk, equity=equity, marks=marks)
            returns = []
            for row in tr:
                record = dict(zip(TRADE_NAMES, row.tolist()))
                record.update(candidate_id=rule.candidate_id, entry_kst=str(frame.iloc[int(row[1])]["timestamp_kst"]), exit_kst=str(frame.iloc[int(row[3])]["timestamp_kst"]), cycle_return_pct=100 * row[13] / abs(row[5] * 10000))
                cycles.append(record)
                returns.append(record["cycle_return_pct"])
            position = future_position = 0
            cycle_events = {}
            for row in ev:
                record = dict(zip(EVENT_NAMES, row.tolist()))
                code, cid, d = int(row[0]), int(row[2]), int(row[3])
                ds = d if code == 1 else -d if code == 2 else 0
                df = -d if code in (1, 4) else d if code in (2, 3) else 0
                position += ds
                future_position += df
                assert abs(position) <= 1 and abs(future_position) <= 1
                if code == 1:
                    assert abs(position) == 1 and position == -future_position
                    assert int(row[1]) > int(row[13])
                if code == 2:
                    assert position == future_position == 0 and int(row[1]) > int(row[13])
                record.update(candidate_id=rule.candidate_id, timestamp_kst=str(frame.iloc[int(row[1])]["timestamp_kst"]), contract_code_kis=codes[int(row[12]) - 1], spot_quantity_change_usdt=ds * 10000, future_quantity_change_contracts=df)
                event_rows.append(record)
                cycle_events.setdefault(cid, []).append(row)
            for row in tr:
                ee = np.asarray(cycle_events[int(row[17])])
                fee, slip = ee[:, 8:10].sum(), ee[:, 10:12].sum()
                gross = ee[:, 6:8].sum()
                assert np.isclose(gross - fee - slip, row[13], atol=1e-5, rtol=1e-10)
                assert np.isclose(fee, row[11]) and np.isclose(slip, row[12])
                assert (ee[:, 0] == 1).sum() == (ee[:, 0] == 2).sum() == 1
            has_open = bool(residual[1])
            assert abs(position) == int(has_open) and position == -future_position
            residual_return = 100 * residual[10] / (residual[3] * 10000) if has_open else 0.0
            if has_open:
                ee = np.asarray(cycle_events[int(residual[0])])
                direction = int(residual[1])
                basis_events = ee[np.isin(ee[:, 0], (1, 4, 5))]
                future_gross = ee[:, 7].sum() + direction * (basis_events[-1, 5] - v[8][-1]) * 10000
                spot_gross = direction * (v[6][-1] - residual[3]) * 10000
                assert np.isclose(future_gross, residual[6], atol=1e-5)
                assert np.isclose(spot_gross + future_gross - ee[:, 8:12].sum() - residual[9], residual[10], atol=1e-5)
                residuals.append(dict(candidate_id=rule.candidate_id, cycle_id=int(residual[0]), direction=int(residual[1]), entry_index=int(residual[2]), entry_spot=residual[3], entry_future=residual[4], spot_gross=residual[5], future_gross=residual[6], fees_paid=residual[7], slippage_paid=residual[8], estimated_close_cost=residual[9], net_after_close_cost=residual[10], hold_minutes=residual[11], entry_kst=str(frame.iloc[int(residual[2])]["timestamp_kst"])))
            for mark in marks:
                risk_rows.append(dict(candidate_id=rule.candidate_id, row_index=int(mark[0]), phase=int(mark[1]), cycle_id=int(mark[2]), direction=int(mark[3]), spot_mark=mark[4], future_mark=mark[5], equity_net=mark[6], open_net_paid_cost=mark[7], mdd_krw=mark[8]))
            score = float(sum(returns)) if returns else None
            result = asdict(rule)
            result.update(completed_cycles=len(tr), win_rate_pct=100 * np.mean(tr[:, 13] > 0) if len(tr) else None, score_pct=score, average_cycle_return_pct=float(np.mean(returns)) if returns else None, average_hold_minutes=float(np.mean(tr[:, 14])) if len(tr) else None, longest_hold_minutes=max(float(tr[:, 14].max()) if len(tr) else 0, residual[11] if has_open else 0), max_evaluation_loss_krw=risk[1], mdd_krw=risk[0], max_initial_margin_krw=risk[2], max_futures_gross_loss_krw=risk[3], max_spot_notional_krw=risk[4], ignored_signals_while_held=int(risk[5]), max_simultaneous_sets=1 if len(ev) else 0, residual_sets=int(has_open), residual_net_after_close_cost_krw=float(residual[10]), auxiliary_final_close_return_pct=residual_return, score_with_hypothetical_final_close_pct=float(sum(returns)) + residual_return, fees_krw=float(ev[:, 8:10].sum()), slippage_krw=float(ev[:, 10:12].sum()), funding_krw=0, net_mark_with_final_close_krw=float(tr[:, 13].sum()) + float(residual[10]), borrow_status="UNVERIFIED_THEORETICAL_ONLY" if rule.direction in (-1, 0) else "NOT_APPLICABLE", status="PASS")
            results.append(result)
            previous = 0.0
            for month in np.unique(v[1]):
                idx = np.flatnonzero(v[1] == month)[-1]
                end = float(equity[idx])
                monthly.append(dict(candidate_id=rule.candidate_id, business_month=str(frame.iloc[idx]["business_date"])[:6], marked_pnl_change_krw=end - previous, completed_cycle_score_pct=sum(100 * r[13] / (r[5] * 10000) for r in tr if v[1][int(r[3])] == month), cycles=sum(v[1][int(r[3])] == month for r in tr)))
                previous = end
            audits.append(dict(candidate_id=rule.candidate_id, completed_cycles=len(tr), global_one_set_pass=True, fees_reconciled=True, pnl_reconciled=True, status="PASS"))
            BATCH.joinpath("progress.json").write_text(json.dumps({"last_candidate": rule.candidate_id, "completed_conditions": len(results), "total_conditions": 50}), encoding="utf8")
            print(json.dumps({"candidate": rule.candidate_id, "completed": len(results), "cycles": len(tr), "score_pct": score}), flush=True)
        write_csv(BATCH / "results.csv", results)
        cycle_fields = ["candidate_id", *TRADE_NAMES, "entry_kst", "exit_kst", "cycle_return_pct"]
        write_csv(BATCH / "cycles.csv", cycles, cycle_fields)
        write_csv(BATCH / "trades.csv.gz", event_rows, [*EVENT_NAMES, "candidate_id", "timestamp_kst", "contract_code_kis", "spot_quantity_change_usdt", "future_quantity_change_contracts"])
        write_csv(BATCH / "residuals.csv", residuals, ["candidate_id", "cycle_id", "direction", "entry_index", "entry_spot", "entry_future", "spot_gross", "future_gross", "fees_paid", "slippage_paid", "estimated_close_cost", "net_after_close_cost", "hold_minutes", "entry_kst"])
        write_csv(BATCH / "monthly.csv", monthly)
        write_csv(BATCH / "risk_extremes.csv.gz", risk_rows)
        write_csv(BATCH / "costs.csv", [{k: r[k] for k in ("candidate_id", "fees_krw", "slippage_krw", "funding_krw", "borrow_status")} for r in results])
        BATCH.joinpath("validation.json").write_text(json.dumps({"status": "PASS", "conditions": audits, "max_global_sets": 1, "inputs": len(v[0]), "no_additions": True}, indent=2), encoding="utf8")
        BATCH.joinpath("READY.json").write_text(json.dumps({"status": "READY_FOR_PUBLICATION", "completed_conditions": 50, "stop_after_batch": 1, "worker_stopped": True}, indent=2), encoding="utf8")
    finally:
        lock.unlink()


if __name__ == "__main__":
    action = {"register": register, "run": run_batch}[sys.argv[1]]
    action()
