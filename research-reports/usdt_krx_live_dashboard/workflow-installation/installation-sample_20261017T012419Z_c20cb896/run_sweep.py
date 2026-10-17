from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import os
import time
from contextlib import ExitStack
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

import paper_engine as engine


RUN_DIR = Path(__file__).resolve().parent
RESULTS = RUN_DIR / "candidate_results.csv"
TRADES = RUN_DIR / "trade_ledger.csv"
EVENTS = RUN_DIR / "event_ledger.csv"
RESIDUALS = RUN_DIR / "residual_positions.csv"
ACCOUNT = RUN_DIR / "account_cash_ledger.csv"
MONTHLY = RUN_DIR / "monthly_equity.csv"
BATCHES = RUN_DIR / "batch_summaries.csv"
CHECKPOINT = RUN_DIR / "sweep_checkpoint.json"
COSTS = [(s, clear) for clear in (False, True) for s in (0.0, 1.0, 2.0, 5.0, 10.0)]
GROUPS = [("discount_long", "individual"), ("discount_long", "fixed_basket"), ("premium_short", "individual"), ("premium_short", "fixed_basket")]
BATCH_SIZE = 50


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def append_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    frame = pd.DataFrame(rows)
    frame.to_csv(path, mode="a", index=False, header=not path.exists(), encoding="utf-8-sig")


def timestamp_for(timestamps: np.ndarray, index: int) -> str:
    if index < 0 or index >= len(timestamps):
        return ""
    return str(timestamps[index])


def account_journal(candidate_id: str, direction: str, slippage: float, clear: bool,
                    event_rows: np.ndarray, timestamps: np.ndarray) -> list[dict[str, Any]]:
    sign = 1 if direction == "discount_long" else -1
    spot_cash = engine.INITIAL_SPOT
    futures_cash = engine.INITIAL_FUTURES
    positions = 0
    bases: dict[int, float] = {}
    rows: list[dict[str, Any]] = [{
        "candidate_id": candidate_id, "slippage_bps": slippage,
        "fee_policy": "600_PLUS_CLEARING_ASSUMED" if clear else "600_TOTAL_ASSUMED",
        "row_index": 0, "timestamp_kst": timestamp_for(timestamps, 0), "event_code": 0,
        "set_id": 0, "account_event": "INITIAL_CAPITAL", "spot_cash_delta_krw": 0.0,
        "futures_cash_delta_krw": 0.0, "spot_cash_krw": spot_cash,
        "futures_cash_krw": futures_cash, "open_sets": 0,
    }]
    for event in event_rows:
        code = int(event[0])
        ix = int(event[1])
        sid = int(event[2])
        spot_px = float(event[7])
        future_px = float(event[8])
        spot_fee = float(event[11])
        future_fee = float(event[12])
        spot_slip = float(event[13])
        future_slip = float(event[14])
        spot_delta = 0.0
        future_delta = 0.0
        event_name = "OTHER"
        if code == 1:
            spot_delta = -sign * spot_px * engine.QTY - spot_fee - spot_slip
            future_delta = -future_fee - future_slip
            bases[sid] = future_px
            positions += 1
            event_name = "ENTRY"
        elif code == 2:
            spot_delta = sign * spot_px * engine.QTY - spot_fee - spot_slip
            basis = bases.pop(sid, future_px)
            future_delta = sign * (basis - future_px) * engine.QTY - future_fee - future_slip
            positions -= 1
            event_name = "EXIT"
        elif code == 3:
            basis = bases.get(sid, future_px)
            future_delta = sign * (basis - future_px) * engine.QTY - future_fee - future_slip
            event_name = "ROLL_CLOSE"
        elif code == 4:
            bases[sid] = float(event[10])
            future_delta = -future_fee - future_slip
            event_name = "ROLL_OPEN"
        elif code == 5:
            basis = bases.get(sid, future_px)
            future_delta = sign * (basis - future_px) * engine.QTY
            bases[sid] = future_px
            event_name = "DAILY_SETTLEMENT"
        elif code == 6:
            event_name = "ENTRY_REJECTED"
        spot_cash += spot_delta
        futures_cash += future_delta
        rows.append({
            "candidate_id": candidate_id, "slippage_bps": slippage,
            "fee_policy": "600_PLUS_CLEARING_ASSUMED" if clear else "600_TOTAL_ASSUMED",
            "row_index": ix, "timestamp_kst": timestamp_for(timestamps, ix), "event_code": code,
            "set_id": sid, "account_event": event_name,
            "spot_cash_delta_krw": spot_delta, "futures_cash_delta_krw": future_delta,
            "spot_cash_krw": spot_cash, "futures_cash_krw": futures_cash,
            "open_sets": positions,
        })
    rows.append({
        "candidate_id": candidate_id, "slippage_bps": slippage,
        "fee_policy": "600_PLUS_CLEARING_ASSUMED" if clear else "600_TOTAL_ASSUMED",
        "row_index": len(timestamps) - 1, "timestamp_kst": timestamp_for(timestamps, len(timestamps) - 1),
        "event_code": 99, "set_id": 0, "account_event": "FINAL_CASH_CHECK",
        "spot_cash_delta_krw": 0.0, "futures_cash_delta_krw": 0.0,
        "spot_cash_krw": spot_cash, "futures_cash_krw": futures_cash,
        "open_sets": positions,
    })
    return rows


def enrich_ledgers(candidate_id: str, direction: str, exit_mode: str, slippage: float,
                   clear: bool, arrays: dict[str, Any], result: tuple) -> tuple[list[dict[str, Any]], ...]:
    summary, trades, events, residuals, monthly_equity = result
    frame = arrays["frame"]
    timestamps = frame["timestamp_kst"].astype(str).to_numpy()
    cost_name = "600_PLUS_CLEARING_ASSUMED" if clear else "600_TOTAL_ASSUMED"
    trade_rows: list[dict[str, Any]] = []
    for raw in trades:
        row = dict(zip(engine.TRADE_NAMES, raw.tolist()))
        for field in ("entry_signal_row_index", "entry_fill_row_index", "exit_signal_row_index", "exit_fill_row_index"):
            row[field] = int(row[field])
        row["entry_signal_timestamp_kst"] = timestamp_for(timestamps, row["entry_signal_row_index"])
        row["entry_fill_timestamp_kst"] = timestamp_for(timestamps, row["entry_fill_row_index"])
        row["exit_signal_timestamp_kst"] = timestamp_for(timestamps, row["exit_signal_row_index"])
        row["exit_fill_timestamp_kst"] = timestamp_for(timestamps, row["exit_fill_row_index"])
        row["candidate_id"] = candidate_id
        row["direction"] = direction
        row["exit_mode"] = exit_mode
        row["slippage_bps"] = slippage
        row["fee_policy"] = cost_name
        row["result_class"] = "PAPER_NEXT_OPEN_PROXY_COST_ASSUMED" if direction == "discount_long" else "REFERENCE_ONLY_BORROW_UNVERIFIED"
        row["entry_contract_code_kis"] = arrays["contract_codes"][int(row["entry_contract_id"]) - 1] if int(row["entry_contract_id"]) else ""
        row["exit_contract_code_kis"] = arrays["contract_codes"][int(row["exit_contract_id"]) - 1] if int(row["exit_contract_id"]) else ""
        trade_rows.append(row)
    event_rows: list[dict[str, Any]] = []
    for raw in events:
        row = dict(zip(engine.EVENT_NAMES, raw.tolist()))
        row["row_index"] = int(row["row_index"])
        row["timestamp_kst"] = timestamp_for(timestamps, row["row_index"])
        row["candidate_id"] = candidate_id
        row["direction"] = direction
        row["exit_mode"] = exit_mode
        row["slippage_bps"] = slippage
        row["fee_policy"] = cost_name
        row["result_class"] = "PAPER_NEXT_OPEN_PROXY_COST_ASSUMED" if direction == "discount_long" else "REFERENCE_ONLY_BORROW_UNVERIFIED"
        row["contract_code_kis"] = arrays["contract_codes"][int(row["contract_id"]) - 1] if int(row["contract_id"]) else ""
        event_rows.append(row)
    residual_rows: list[dict[str, Any]] = []
    for raw in residuals:
        row = dict(zip(engine.RESIDUAL_NAMES, raw.tolist()))
        for field in ("entry_signal_row_index", "entry_fill_row_index"):
            row[field] = int(row[field])
        row["entry_signal_timestamp_kst"] = timestamp_for(timestamps, row["entry_signal_row_index"])
        row["entry_fill_timestamp_kst"] = timestamp_for(timestamps, row["entry_fill_row_index"])
        row["evaluation_timestamp_kst"] = timestamp_for(timestamps, len(timestamps) - 1)
        row["candidate_id"] = candidate_id
        row["direction"] = direction
        row["exit_mode"] = exit_mode
        row["slippage_bps"] = slippage
        row["fee_policy"] = cost_name
        row["contract_code_kis"] = arrays["contract_codes"][int(row["contract_id"]) - 1] if int(row["contract_id"]) else ""
        residual_rows.append(row)
    monthly_rows = []
    previous = engine.INITIAL_CAPITAL
    for ix, month_equity in enumerate(monthly_equity):
        if np.isfinite(month_equity):
            monthly_rows.append({
                "candidate_id": candidate_id, "direction": direction, "exit_mode": exit_mode,
                "slippage_bps": slippage, "fee_policy": cost_name,
                "month": arrays["month_names"][ix], "ending_equity_krw": float(month_equity),
                "change_from_previous_month_krw": float(month_equity - previous),
                "result_class": "PAPER_NEXT_OPEN_PROXY_COST_ASSUMED" if direction == "discount_long" else "REFERENCE_ONLY_BORROW_UNVERIFIED",
            })
            previous = float(month_equity)
    account_rows = account_journal(candidate_id, direction, slippage, clear, events, timestamps)
    if account_rows:
        if not np.isfinite(float(account_rows[-1]["spot_cash_krw"])) or not np.isfinite(float(summary[36])):
            raise RuntimeError(f"Non-finite spot cash ledger for {candidate_id}")
        if not np.isfinite(float(account_rows[-1]["futures_cash_krw"])) or not np.isfinite(float(summary[37])):
            raise RuntimeError(f"Non-finite futures cash ledger for {candidate_id}")
        if abs(float(account_rows[-1]["spot_cash_krw"]) - float(summary[36])) > 0.05:
            raise RuntimeError(f"Spot cash ledger mismatch for {candidate_id}")
        if abs(float(account_rows[-1]["futures_cash_krw"]) - float(summary[37])) > 0.05:
            raise RuntimeError(f"Futures cash ledger mismatch for {candidate_id}")
    return trade_rows, event_rows, residual_rows, monthly_rows, account_rows


def load_checkpoint() -> dict[str, Any]:
    if CHECKPOINT.exists():
        return json.loads(CHECKPOINT.read_text(encoding="utf-8"))
    return {"completed_batches": [], "status": "IN_PROGRESS"}


def save_checkpoint(checkpoint: dict[str, Any]) -> None:
    CHECKPOINT.write_text(json.dumps(checkpoint, ensure_ascii=False, indent=2), encoding="utf-8")


def commit_batch_metadata(key: str, result_frame: pd.DataFrame, candidate_count: int,
                          elapsed: float, checkpoint: dict[str, Any]) -> dict[str, Any]:
    batch_summary: dict[str, Any] = {
        "batch": key,
        "candidate_conditions": candidate_count,
        "cost_runs": len(result_frame),
        "elapsed_seconds": round(elapsed, 3),
        "highest_net_candidates_by_cost": {},
        "completed_at_local": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    for (slip, clear), values in result_frame.groupby(["slippage_bps_per_side_per_leg", "fee_policy"]):
        values = values.copy()
        values["net_sort"] = pd.to_numeric(values["net_liquidation_pnl"], errors="coerce")
        top = values.sort_values("net_sort", ascending=False).head(3)
        batch_summary["highest_net_candidates_by_cost"][f"{float(slip):g}bp|{clear}"] = [{
            "candidate_id": str(r["candidate_id"]),
            "E_pp": float(r["entry_e_pp"]), "R_pp": float(r["recovery_r_pp"]),
            "net_liquidation_pnl_krw": float(r["net_liquidation_pnl"]),
            "closed_sets": int(float(r["closed_sets"] or 0)), "completed_cycles": int(float(r["completed_cycles"] or 0)),
            "residual_sets": int(float(r["residual_sets"] or 0)), "mdd_krw": float(r["mdd_krw"]),
            "max_spot_cash_used_krw": float(r["max_spot_cash_used"]),
            "max_initial_margin_required_krw": float(r["max_initial_margin_required"]),
            "margin_breach_events": int(float(r["maintenance_breach_events"] or 0)),
        } for _, r in top.iterrows()]
    checkpoint["completed_batches"] = sorted(set(checkpoint["completed_batches"] + [key]))
    checkpoint["last_completed_batch"] = key
    checkpoint["status"] = "IN_PROGRESS"
    save_checkpoint(checkpoint)
    batch_number = int(key.rsplit("|", 1)[1]) + 1
    parts = key.split("|")
    batch_summary_path = RUN_DIR / f"batch_{parts[0]}_{parts[1]}_{batch_number:02d}.json"
    batch_summary_path.write_text(json.dumps(batch_summary, ensure_ascii=False, indent=2), encoding="utf-8")
    if not BATCHES.exists() or key not in set(pd.read_csv(BATCHES, dtype=str)["batch"].tolist()):
        append_rows(BATCHES, [{
            "batch": key, "candidate_conditions": candidate_count, "cost_runs": len(result_frame),
            "elapsed_seconds": batch_summary["elapsed_seconds"], "report_json": batch_summary_path.name,
        }])
    print(json.dumps(batch_summary, ensure_ascii=False), flush=True)
    return batch_summary


def run_batch(direction: str, exit_mode: str, batch_index: int, force: bool = False) -> dict[str, Any]:
    checkpoint = load_checkpoint()
    key = f"{direction}|{exit_mode}|{batch_index}"
    if key in checkpoint["completed_batches"] and not force:
        return {"status": "ALREADY_COMPLETE", "batch": key}
    grid = pd.read_csv(engine.GRID, dtype=str).fillna("")
    group = grid[grid["direction"].eq(direction) & grid["exit_mode"].eq(exit_mode)].copy().reset_index(drop=True)
    start = batch_index * BATCH_SIZE
    subset = group.iloc[start:start + BATCH_SIZE]
    if subset.empty:
        return {"status": "NO_CANDIDATES", "batch": key}
    expected_runs = len(subset) * len(COSTS)
    if RESULTS.exists():
        saved = pd.read_csv(RESULTS, dtype=str).fillna("")
        saved = saved[saved["batch"].eq(key)]
        if len(saved) == expected_runs:
            return commit_batch_metadata(key, saved, len(subset), 0.0, checkpoint)
        if len(saved):
            raise RuntimeError(f"Found {len(saved)} saved result rows for incomplete batch {key}; refusing duplicate execution")
    arrays = engine.load_arrays()
    result_rows: list[dict[str, Any]] = []
    ledger_dir = RUN_DIR / "ledger_batches"
    ledger_dir.mkdir(exist_ok=True)
    suffix = f"{direction}_{exit_mode}_{batch_index + 1:02d}"
    ledger_kinds = ("trades", "events", "residuals", "monthly_equity", "account_cash")
    partial_paths = {name: ledger_dir / f"{suffix}.{name}.csv.gz.partial" for name in ledger_kinds}
    final_paths = {name: ledger_dir / f"{suffix}.{name}.csv.gz" for name in ledger_kinds}
    for path in partial_paths.values():
        if path.exists():
            path.unlink()
    start_time = time.monotonic()
    with ExitStack() as stack:
        writers: dict[str, csv.DictWriter] = {}
        def write_stream(name: str, rows: list[dict[str, Any]]) -> None:
            if not rows:
                return
            if name not in writers:
                stream = stack.enter_context(gzip.open(partial_paths[name], "wt", encoding="utf-8", newline=""))
                writers[name] = csv.DictWriter(stream, fieldnames=list(rows[0]))
                writers[name].writeheader()
            writers[name].writerows(rows)

        for offset, candidate in enumerate(subset.to_dict("records")):
            for slippage, clear in COSTS:
                simulation = engine.run_candidate(
                    arrays, direction, exit_mode, float(candidate["entry_e_pp"]),
                    float(candidate["recovery_r_pp"]), slippage, clear,
                )
                summary, trades, events, residuals, monthly_equity = simulation
                if int(summary[41]) or int(summary[42]):
                    raise RuntimeError(f"Ledger buffer overflow for {candidate['candidate_id']}")
                if not np.isfinite(summary[[11, 12, 13, 14, 36, 37, 38]]).all():
                    raise RuntimeError(f"Non-finite net liquidation or account value for {candidate['candidate_id']}")
                row = engine.metric_record(
                    summary, trades, direction, exit_mode,
                    float(candidate["entry_e_pp"]), float(candidate["recovery_r_pp"]),
                    slippage, clear, candidate["candidate_id"],
                )
                row["candidate_id"] = candidate["candidate_id"]
                row["batch"] = key
                row["candidate_position"] = int(start + offset + 1)
                row["unverified_margin_schedule_days"] = len(arrays["inferred_margin_dates"])
                row["maintenance_breach_disposition"] = "RISK_FLAG_ONLY; NO LIQUIDATION PRICE MODEL"
                row["market_fill_status"] = "NEXT_OPEN_PROXY; HISTORICAL_QUOTES_UNAVAILABLE"
                result_rows.append(row)
                trades_add, events_add, residuals_add, monthly_add, accounts_add = enrich_ledgers(
                    candidate["candidate_id"], direction, exit_mode, slippage, clear, arrays, simulation,
                )
                write_stream("trades", trades_add)
                write_stream("events", events_add)
                write_stream("residuals", residuals_add)
                write_stream("monthly_equity", monthly_add)
                write_stream("account_cash", accounts_add)
    for name, partial in partial_paths.items():
        if partial.exists():
            os.replace(partial, final_paths[name])
    append_rows(RESULTS, result_rows)
    checkpoint["ledger_files"] = checkpoint.get("ledger_files", {})
    checkpoint["ledger_files"][key] = {name: str(path.relative_to(RUN_DIR)) for name, path in final_paths.items() if path.exists()}
    result_frame = pd.DataFrame(result_rows)
    return commit_batch_metadata(key, result_frame, len(subset), time.monotonic() - start_time, checkpoint)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--direction", choices=["discount_long", "premium_short"])
    parser.add_argument("--exit-mode", choices=["individual", "fixed_basket"])
    parser.add_argument("--batch", type=int)
    parser.add_argument("--run-all", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    input_audit = json.loads((RUN_DIR / "input_audit.json").read_text(encoding="utf-8"))
    if input_audit.get("status") != "READY_FOR_PAPER_ENGINE":
        raise RuntimeError("Input audit is not ready")
    if args.run_all:
        grid = pd.read_csv(engine.GRID, dtype=str).fillna("")
        for direction, exit_mode in GROUPS:
            n = int(grid[grid["direction"].eq(direction) & grid["exit_mode"].eq(exit_mode)].shape[0])
            batches = (n + BATCH_SIZE - 1) // BATCH_SIZE
            for batch_index in range(batches):
                run_batch(direction, exit_mode, batch_index)
        checkpoint = load_checkpoint()
        checkpoint["status"] = "COMPLETE"
        checkpoint["completed_condition_groups"] = {f"{d}|{m}": int(pd.read_csv(engine.GRID).query("direction == @d and exit_mode == @m").shape[0]) for d, m in GROUPS}
        save_checkpoint(checkpoint)
    elif args.direction and args.exit_mode and args.batch is not None:
        run_batch(args.direction, args.exit_mode, args.batch, args.force)
    else:
        parser.error("Provide --run-all or --direction, --exit-mode, and --batch")


if __name__ == "__main__":
    main()
