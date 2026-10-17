# /// script
# requires-python = ">=3.12"
# dependencies = ["numpy", "pandas", "numba"]
# ///
# Run with the existing research Python: python -B work/reproduce_unlimited_baseline.py
"""Freeze a new study and reproduce its mandatory original-engine control first."""
from __future__ import annotations

import csv
import hashlib
import importlib.metadata
import importlib.util
import json
import os
import platform
import shutil
import sys
import time
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    source = root / "outputs/usdt_krx_live_dashboard/data/pnl_optimization_2026/approved_20261016_01"
    out = root / "outputs/usdt_krx_live_dashboard/data/unlimited_revalidation_20261017_01"
    out.mkdir(parents=True, exist_ok=False)
    baseline = out / "batch_000_original_control"
    baseline.mkdir()
    cache = root / "work/unlimited_revalidation_numba_cache"
    cache.mkdir(exist_ok=True)
    os.environ["NUMBA_CACHE_DIR"] = str(cache)
    sys.dont_write_bytecode = True
    script = source / "paper_engine.py"
    original_hash = hashlib.sha256(script.read_bytes()).hexdigest()
    spec = importlib.util.spec_from_file_location("control_paper_engine", script)
    if spec is None or spec.loader is None:
        raise RuntimeError("Original engine cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    began = time.monotonic()
    arrays = module.load_arrays()
    summary, trades, events, residuals, _ = module.run_candidate(arrays, "discount_long", "fixed_basket", 1.4, 3.0, 2.0, True)
    groups: dict[int, list[int]] = {}
    for index, row in enumerate(trades):
        groups.setdefault(int(row[1]), []).append(index)
    cycle_rows: list[dict[str, str | int | float]] = []
    for cycle_id, indices in sorted(groups.items()):
        selected = trades[indices]
        amount = float(selected[:, 9].sum() * 10000)
        net = float(selected[:, 22].sum())
        cycle_rows.append({"cycle_id": cycle_id, "entry_notional_krw": amount, "net_pnl_krw": net, "cycle_return_pct": net / amount * 100, "closed_sets": len(indices), "complete": int(selected[:, 26].max())})
    cycles_return = sum(float(row["cycle_return_pct"]) for row in cycle_rows)
    validation = {"strategy": "DB-0249", "mode": "ORIGINAL_LIMITED_ENGINE", "closed_sets": len(trades), "completed_cycles": len(cycle_rows), "residual_sets": len(residuals), "net_pnl_krw": float(summary[13]), "ledger_net_krw": float(trades[:, 22].sum()), "cycle_simple_return_pct": cycles_return, "sum_of_rounded_cycle_returns_pct": sum(round(float(row["cycle_return_pct"]), 4) for row in cycle_rows), "cash_rejections": int(summary[25]), "margin_rejections": int(summary[26]), "cap_rejections": int(summary[27]), "input_rows": len(arrays["times"]), "seconds": time.monotonic() - began, "engine_sha256_before": original_hash, "engine_sha256_after": hashlib.sha256(script.read_bytes()).hexdigest()}
    passed = len(trades) == 12 and len(cycle_rows) == 3 and len(residuals) == 0 and abs(float(summary[13]) - 4890138.803278029) < 0.01 and abs(cycles_return - 8.554937368493867) < 1e-7 and validation["engine_sha256_before"] == validation["engine_sha256_after"]
    validation["status"] = "PASS" if passed else "FAILED"
    for filename, names, rows in [("trades.csv", module.TRADE_NAMES, trades), ("events.csv", module.EVENT_NAMES, events), ("residuals.csv", module.RESIDUAL_NAMES, residuals)]:
        with (baseline / filename).open("x", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(names)
            writer.writerows(rows.tolist())
    with (baseline / "cycles.csv").open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(cycle_rows[0]))
        writer.writeheader()
        writer.writerows(cycle_rows)
    (baseline / "validation.json").write_text(json.dumps(validation, indent=2) + "\n", encoding="utf-8")
    environment = {"python": platform.python_version(), "packages": {name: importlib.metadata.version(name) for name in ("numpy", "pandas", "numba")}, "original_runtime_modified": False}
    (baseline / "environment.json").write_text(json.dumps(environment, indent=2) + "\n", encoding="utf-8")
    for name in ("paper_engine.py", "preregistration.json", "analysis_scope.json", "margin_schedule.csv"):
        shutil.copyfile(source / name, baseline / name)
    shutil.copyfile(__file__, baseline / Path(__file__).name)
    print(json.dumps(validation))
    assert passed, "Original DB-0249 reproduction failed; new result publication is blocked"


if __name__ == "__main__":
    main()
