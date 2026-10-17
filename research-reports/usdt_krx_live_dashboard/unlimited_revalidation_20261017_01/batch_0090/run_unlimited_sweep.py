# /// script
# requires-python = ">=3.12"
# dependencies = ["numpy", "pandas", "numba"]
# ///
# Run: python -B work/run_unlimited_sweep.py
from __future__ import annotations

import csv
import gzip
import hashlib
import importlib.util
import itertools
import json
import math
import os
import subprocess
import sys
import time
from contextlib import ExitStack, contextmanager
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from build_unlimited_engine import build
from unlimited_batch_io import finalize_batch, save_raw, write_table
from unlimited_execution import Condition, Market, VECTOR_NAMES, run
from unlimited_metrics import summarize

ROOT = Path(__file__).resolve().parents[1]
STUDY = ROOT / "outputs/usdt_krx_live_dashboard/data/unlimited_revalidation_20261017_01"
SOURCE = ROOT / "outputs/usdt_krx_live_dashboard/data/pnl_optimization_2026/approved_20261016_01"


@contextmanager
def claim_study():
    lock = STUDY / "worker.lock.json"
    if lock.exists():
        owner = json.loads(lock.read_text())
        pid, script = int(owner["pid"]), owner["script"]
        assert script in {"run_unlimited_sweep.py", "run_unlimited_sensitivity.py"} and pid > 0
        query = f"$p=Get-CimInstance Win32_Process -Filter 'ProcessId = {pid}'; if ($p -and $p.CommandLine -like '*{script}*') {{exit 0}}; exit 1"
        running = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", query], capture_output=True, timeout=30)
        if running.returncode == 0:
            raise RuntimeError("Study worker is already active; do not start a duplicate")
        archived = STUDY / ("worker.lock.stale_" + uuid4().hex[:8] + ".json")
        assert lock.resolve().parent == STUDY.resolve() and archived.resolve().parent == STUDY.resolve()
        lock.rename(archived)
    with lock.open("x", encoding="utf-8") as stream:
        json.dump({"pid": os.getpid(), "script": Path(sys.argv[0]).name}, stream)
    try:
        yield
    finally:
        assert lock.resolve().parent == STUDY.resolve()
        lock.unlink()


def main() -> None:
    assert json.loads((STUDY / "batch_000_original_control/validation.json").read_text())["status"] == "PASS"
    os.environ["NUMBA_CACHE_DIR"] = str(ROOT / "work/unlimited_revalidation_numba_cache")
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location("unlimited_input_loader_original", SOURCE / "paper_engine.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("Original approved input loader unavailable")
    loader = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = loader
    spec.loader.exec_module(loader)
    arrays = loader.load_arrays()
    market = Market(tuple(arrays[name] for name in VECTOR_NAMES), tuple(arrays["frame"]["timestamp_kst"].astype(str)), tuple(arrays["contract_codes"]))
    engine = build(SOURCE / "paper_engine.py", STUDY / "engine_unlimited_generated.py")
    gap = market.vectors[4]
    ranges = {1: max(4.2, math.ceil(-float(gap.min()) * 10) / 10), -1: max(3.0, math.ceil(float(gap.max()) * 10) / 10)}
    recovery_max = max(7.2, math.ceil((float(gap.max()) - float(gap.min())) * 10) / 10)
    recoveries = [round(index / 10, 1) for index in range(1, round(recovery_max * 10) + 1)]
    spacings = [0.1, 0.2, 0.3, 0.4, 0.5, 0.75, 1.0]
    grid = []
    for direction in (1, -1):
        entries = sorted({round(index / 10, 1) for index in range(1, round(ranges[direction] * 10) + 1)} | {5.0, 6.0})
        for entry, spacing, recovery, mode in itertools.product(entries, spacings, recoveries, (0, 1)):
            grid.append(Condition("U-" + str(len(grid) + 1).zfill(6), direction, mode, entry, spacing, recovery))
    anchors = {(1, 1, 1.4, 0.2, 3.0), (1, 1, 0.8, 0.2, 0.3), (-1, 1, 1.4, 0.2, 3.0), (1, 1, 5.0, 0.1, 0.2), (1, 1, 6.0, 0.1, 0.2), (-1, 1, 5.0, 0.1, 0.2), (-1, 1, 6.0, 0.1, 0.2)}
    grid.sort(key=lambda case: ((case.direction, case.exit_mode, case.entry, case.spacing, case.recovery) not in anchors, hashlib.sha256(json.dumps(asdict(case), sort_keys=True).encode()).hexdigest()))
    eligible = market.vectors[12].copy()
    eligible[-1] = False
    eligible[:-1] &= market.vectors[12][1:]
    eligible &= ~market.vectors[9]
    settings = {"study_id": STUDY.name, "single_authority": "bb972563-6ff1-4cdd-97a8-76dc0b3c054e attached full revalidation instruction", "approved_range": "KRX business dates 2026-01-01 through 2026-10-15 including only required night calendar boundaries", "classification": "EXPLORATORY; not independent Final OOS", "base_conditions": len(grid), "batch_size": 50, "spacing_grid_pp": spacings, "entry_step_pp": 0.1, "entry_range_abs_pp": ranges, "extra_no_signal_tests_abs_pp": [5, 6], "recovery_grid_pp": recoveries, "base_slippage_bp_per_side_per_leg": 2, "base_fee_policy": "600_PLUS_CLEARING_ASSUMED", "source_close_gap_min_pct": float(gap.min()), "source_close_gap_max_pct": float(gap.max()), "eligible_signal_gap_min_pct": float(gap[eligible].min()), "eligible_signal_gap_max_pct": float(gap[eligible].max()), "stage_reentry": "same stage may reenter after its individual close and a genuinely new threshold crossing", "sensitivity_plan": "After all base results: preregister the union of top20 per direction for all / no residual / >=3 / >=5 / >=10 completed cycles. Test one-fill-per-bar and each of 0/1/2/5/10bp times both original fee policies; reuse the identical base 2bp-plus-policy case.", "funding": "No spot, futures initial/maintenance margin, or position-count admission limits. Required external funding and loss remain recorded.", "memory_capacity": "Derived from full data solely for storage; prefix-causality regression passes. Overflow reruns with larger buffers and never accepts truncated output.", "reverse": "THEORETICAL_ONLY_BORROW_UNVERIFIED", "source_engine_sha256": hashlib.sha256((SOURCE / "paper_engine.py").read_bytes()).hexdigest(), "source_input_sha256": hashlib.sha256((SOURCE / "matched_simulation_bars.csv").read_bytes()).hexdigest()}
    registry = STUDY / "preregistration.json"
    if registry.exists():
        assert json.loads(registry.read_text()) == settings, "Registered settings differ; create a new study ID"
    else:
        registry.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
        write_table(STUDY / "condition_grid.csv", [asdict(case) for case in grid])
        write_table(STUDY / "source_timestamp_index.csv", [{"row_index": i, "timestamp_kst": value, "contract_code_kis": market.codes[int(market.vectors[3][i]) - 1]} for i, value in enumerate(market.timestamps)])
        with (STUDY / "source_timestamp_index.csv").open("rb") as raw, gzip.open(STUDY / "source_timestamp_index.csv.gz", "wb", compresslevel=3) as compressed:
            import shutil
            shutil.copyfileobj(raw, compressed)
    print(json.dumps({"phase": "PREREGISTERED", "conditions": len(grid), "batches": math.ceil(len(grid) / 50), "raw_gap_range": [float(gap.min()), float(gap.max())]}), flush=True)
    for start in range(0, len(grid), 50):
        batch_id = start // 50 + 1
        batch = STUDY / ("batch_" + str(batch_id).zfill(4))
        receipt = batch / "publication_receipt.json"
        if receipt.exists() and json.loads(receipt.read_text())["status"] == "PUBLISHED_VERIFIED":
            continue
        ready = batch / "READY.json"
        if not ready.exists():
            if batch.exists():
                abandoned = STUDY / "incomplete_attempts" / (batch.name + "_" + datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid4().hex[:8])
                abandoned.parent.mkdir(exist_ok=True)
                assert batch.resolve().parent == STUDY.resolve() and abandoned.resolve().is_relative_to(STUDY.resolve())
                batch.rename(abandoned)
            batch.mkdir(exist_ok=False)
            conditions = grid[start:start + 50]
            rows, cycles = [], []
            began = time.monotonic()
            with ExitStack() as stack:
                streams = {kind: stack.enter_context(gzip.open(batch / (kind + ".csv.gz"), "wt", encoding="utf-8", newline="", compresslevel=3)) for kind in ("trades", "events", "residuals")}
                for kind, names in (("trades", engine.TRADE_NAMES), ("events", engine.EVENT_NAMES), ("residuals", engine.RESIDUAL_NAMES)):
                    csv.writer(streams[kind]).writerow(["candidate_id", *names])
                for case in conditions:
                    execution = run(engine.simulate_one, market, case)
                    row, cycle_rows = summarize(case, execution, market)
                    rows.append(row)
                    cycles.extend(cycle_rows)
                    for kind in streams:
                        save_raw(streams[kind], (), getattr(execution, kind), case, market)
            packet = finalize_batch(batch, rows, cycles, conditions)
            ready.write_text(json.dumps({"status": "READY_FOR_PUBLICATION", "batch": batch_id, "completed_conditions": start + len(conditions), "total_conditions": len(grid), "seconds": time.monotonic() - began, "payload": str(packet)}, indent=2) + "\n", encoding="utf-8")
            print(ready.read_text(), flush=True)
        while not receipt.exists():
            time.sleep(2)
        assert json.loads(receipt.read_text())["status"] == "PUBLISHED_VERIFIED"
    print("BASE_SWEEP_FINISHED", flush=True)


if __name__ == "__main__":
    with claim_study():
        main()
