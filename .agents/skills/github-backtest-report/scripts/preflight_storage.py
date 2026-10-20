# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Preflight Codex research storage on Windows without touching WSL or research data."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

GIB = 1024 ** 3

def gb(n: int) -> float:
    return round(n / GIB, 3)

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=r"D:\Codex_Research")
    parser.add_argument("--c-min-free-gb", type=float, default=10)
    parser.add_argument("--d-min-free-gb", type=float, default=10)
    args = parser.parse_args()

    status: dict[str, object] = {
        "requested_root": args.root,
        "c_min_free_gb": args.c_min_free_gb,
        "d_min_free_gb": args.d_min_free_gb,
        "safe_to_start_large_job": False,
        "issues": [],
    }
    issues: list[str] = []
    if os.name != "nt":
        issues.append("WINDOWS_REQUIRED")
        status["issues"] = issues
        print(json.dumps(status, ensure_ascii=False, indent=2))
        return 2
    root = Path(args.root)
    if not root.is_absolute() or root.drive.upper() != "D:":
        issues.append("ROOT_MUST_BE_ABSOLUTE_D_DRIVE")
    if not Path("D:\\").exists():
        issues.append("D_DRIVE_MISSING")
    try:
        c_disk = shutil.disk_usage("C:\\")
        d_disk = shutil.disk_usage("D:\\")
        status.update({
            "c_free_gib": gb(c_disk.free),
            "d_free_gib": gb(d_disk.free),
            "d_total_gib": gb(d_disk.total),
        })
        if c_disk.free < args.c_min_free_gb * GIB:
            issues.append("C_DRIVE_LOW_PAUSE_LARGE_JOBS")
        if d_disk.free < args.d_min_free_gb * GIB:
            issues.append("D_DRIVE_LOW_PAUSE_LARGE_JOBS")
    except OSError as e:
        issues.append(f"DISK_USAGE_UNAVAILABLE:{type(e).__name__}")

    if not issues or not any(s in issues for s in ("D_DRIVE_MISSING", "ROOT_MUST_BE_ABSOLUTE_D_DRIVE")):
        try:
            root.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(prefix="codex_storage_probe_", suffix=".tmp", dir=root, delete=True) as f:
                f.write(b"probe")
                f.flush()
            status["d_root_write_test"] = "OK"
        except OSError as e:
            issues.append(f"D_ROOT_WRITE_FAILED:{type(e).__name__}")
    else:
        status["d_root_write_test"] = "NOT_TESTED"

    for key in ("TEMP", "TMP", "TMPDIR", "XDG_CACHE_HOME", "NUMBA_CACHE_DIR"):
        value = os.environ.get(key)
        if value:
            status[f"environment_{key}"] = value
    status["issues"] = issues
    status["safe_to_start_large_job"] = not issues
    print(json.dumps(status, ensure_ascii=False, indent=2))
    return 0 if not issues else 2

if __name__ == "__main__":
    sys.exit(main())
