---
name: github-backtest-report
description: "Mandatory persistent workflow for Codex trading research, backtesting, result reports and verification. Work, cache and checkpoints on Windows D: drive; publish ChatGPT-reviewable reports, source and transaction CSVs to GitHub; verify remote SHA. Prevent Windows C: drive exhaustion."
---

# D-drive work + GitHub verified results (Codex)

## User's standing, explicit authorization

For all Codex research/backtests and result reviews, keep **all heavy working files on D:** and publish user reports, complete result tables and the transaction/cycle evidence needed for ChatGPT review to the user's existing GitHub research archive. This skill updates the prior `github-backtest-report` publication workflow; it does not authorize trading, purchases, deleting datasets, modifying other projects, lifting Final OOS protections, or restarting WSL/OpenClaw.

**Canonical Windows workspace**: `D:\Codex_Research` (only if D: is writable and has room; do not silently substitute C:).

**Remote archive**: existing repository `jeh183000-art/-`, under `research-reports/<project>/<study_id>/`; repository is public. Never change repository visibility, history, or unrelated files.

The user is currently preserving the USDT/KRW spot-long + KRX USD-futures-short study. Do not restart paused collectors/backtests or resume stopped studies merely because this skill was installed.

## Required before every run

1. Load current user and project `AGENTS.md`; honor later explicit instructions.
2. Run `python <skill_dir>/scripts/preflight_storage.py --root D:\Codex_Research` or equivalent verified read-only checks before creating any substantial output. Confirm D: exists, is writable and has at least 10 GiB free for the proposed job; otherwise stop and report. When C: free is <10 GiB, pause large jobs and report; when C: is <5 GiB, **do not start** new research jobs. Preflight cannot guarantee future disk availability; check during long-running batches.
3. Verify the full disk paths of all output, tmp, cache, checkpoint and staging directories. Never use `C:\Users\...\Documents\Codex\...\outputs`, system TEMP or the WSL ext4 virtual disk as a default for heavyweight outputs.
4. If prior Windows/WSL EIO failures persist, leave WSL and OpenClaw stopped; do not retry a failing virtual disk or repair it without separate approval.

## Local storage layout and outputs

For each project use:

- `D:\Codex_Research\<project>\data\` for the canonical raw data and read-only copies when required.
- `D:\Codex_Research\<project>\studies\<study_id>\batches\<batch_id>\` for result tables, audits, reports and immutable per-batch checkpoints.
- `D:\Codex_Research\<project>\shared\` for deduplicated frozen engine and dependency snapshots.
- `D:\Codex_Research\<project>\tmp\`, `logs\`, and `cache\` for transient scratch.

Explicitly set the research subprocess working directory and applicable process-scoped `TEMP`, `TMP`, `TMPDIR`, `XDG_CACHE_HOME`, `NUMBA_CACHE_DIR`, `PIP_CACHE_DIR`, `UV_CACHE_DIR`, and similar cache paths to D: directories where supported. Do not globally rewrite OS/user environment variables. Direct CLI stdout/stderr and reports to D:. In code, locate outputs from an explicit D: configuration rather than `Path(__file__).parent` when the script lives under C:.

Never copy the same 1-minute raw dataset, source engine or dependency tree into every batch. Keep a single versioned, hash-checked shared copy; batch reports cite version, SHA-256 and source path. Rotate logs; reduce cache and scratch growth. Do not automatically delete canonical data, final reports, individual fills, checkpoints, protected OOS or backups. Only clear provably disposable temporary copies after validation, publication and a recoverable checkpoint. Do not delete unrelated studies.

## GitHub artifact contract (ChatGPT must be able to read it)

Use the existing `github-backtest-report` flow to publish a **new immutable folder for every completed, failed, empty or partial batch**:

`research-reports/<project>/<study_id>/batches/<batch_id>_<UTC-time>_<unique>/`

Preserve previously used archive paths; do not rewrite old commits. Publish at least:

1. `REPORT_KO.md`: Korean findings, actual conditions, trade/cycle counts, cumulative net return definition, risk, comparison to previous batches, known limitations, missing data.
2. `results.csv` (all tested candidates, not only winning rows), `cycles.csv`, `trades.csv` or `trades.csv.gz` (complete individual entries/adds/exits and rollovers, where applicable), `costs.csv`, `risks.csv`; include residual positions and rejected/failed tests.
3. `settings.json`, `environment.json`, `provenance.json` with input time range, original source SHA-256, effective engine/code SHA, execution mode and the exact formula for cumulative simple cycle returns.
4. `checkpoint.json` (redacted research progress only, **no tokens/account data**), `manifest.csv` with `path,role,bytes,sha256` for every payload.

For shared code/datasets publish a versioned `shared/<sha-or-version>/` **once**, and include explicit links + exact commit SHA/blob SHA/hash in each batch's provenance and report. Batch package must contain a small `strategy_code_ref.json` role `strategy_code` referring to independently retrievable shared code (or include source directly when not already archived). **Do not store only a report if ChatGPT needs the numbers and fills to verify it.**

Avoid raw market input duplication in every GitHub batch. Publish non-secret, allowed compact/needed data and immutable source hashes. If raw data is D:-only, state `INPUT_NOT_REMOTELY_REPRODUCIBLE` transparently and do not claim complete independent raw-data reproduction. Large artifact limitations must be reported, not silently replaced by a summary. Use lossless compression/splitting and actual remotely downloadable verification when appropriate; no paid cloud storage or LFS quota changes without approval.

## Publication gate and safety

- Use an explicit whitelist; never `git add .` or upload entire D: trees.
- Never publish private keys, API tokens, personal/account information, unredacted private fills, `.env` files, protected Final OOS, SQLite/WAL/SHM, or Windows/WSL filesystem images. This repository is public.
- Use `scripts/verify_batch.py` for manifest role checks, hash checks, secret scanning and remote byte comparison; inspect for additional secrets not captured by the script.
- Publish via the configured GitHub remote, then freshly read the remote commit. Verify the exact commit SHA, every required file path, bytes and SHA-256, including decompressible/retrievable CSVs. Only then report `PUBLISHED_VERIFIED`.
- If upload fails, retain the D: checkpoint and outputs and report `LOCAL_COMPLETE_UPLOAD_BLOCKED`; do not claim completion, silently omit results, force-push, or restart finished computations to compensate.
- Report at every batch: local D: path, repo link, exact commit SHA, remote report/results/fills paths, validation status, progress, best tested candidate (with costs, cycle count, residual positions and MDD), C:/D: remaining space.
- Do not rely on git commit alone: a reproducible remote-read check is required.

## Recovery / prevention

- Never start a new long sweep while C: disk is near full. Reserve minimum 10 GiB of C: free; ensure D: has enough space (>=10 GiB and estimated job growth margin), and recheck at batch boundaries.
- Pause safely on capacity alerts, failed writes, EIO, overflow or remote upload failures. Persist a D: checkpoint first; do not delete output to force forward progress.
- Existing protected KRX regular/night 1-minute bars, USDT/KRW bars, strategy conditions, prior verified batches, Final OOS and D: backups remain intact.
- This skill alone does **not** relocate an already-running process, modify the Windows Codex installation, connect ChatGPT to D:, fix WSL EIO, or alter older reports. A one-time local install/migration and smoke test are required; use `INSTALL_WINDOWS_KO.md` in this repository.
