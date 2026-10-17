---
name: github-backtest-report
description: Archive each trading-strategy research or backtest batch to GitHub with code, settings, result CSVs, individual fills, cost assumptions, statistics, and remote SHA/hash verification. Applies to new research batches and result revisions; not ordinary dashboard or collector maintenance.
---

# GitHub backtest reporting

## Standing user instruction

The user explicitly requires GitHub publication for every trading-strategy research/backtest batch, including failed, empty, audit, and partial batches. This instruction authorizes committing and uploading the scoped, non-secret research artifacts to the configured repository. Do not ask again for that same upload. It does not authorize orders, data purchases, opening protected OOS, or changing strategy conditions. A later explicit user restriction overrides this standing instruction.

Read the applicable project AGENTS.md and existing approval records before accessing research data. Preserve source files, original environment, strategy parameters, collectors, other projects, and Final OOS locks. Do not rerun a backtest merely to create an upload sample.

## Destination and immutable batches

Use the project's explicitly configured GitHub destination first. Otherwise use [references/destination.json](references/destination.json), the user's confirmed writable research archive. Its existing BTC and other content is unrelated: add only under `research-reports/`, never modify their folders. Do not create a public repository or change repository visibility. Before publication confirm visibility and exclude secrets/personal account information. The configured archive is public.

Publish under `research-reports/<project>/<study-id>/<batch-id>_<UTC timestamp>_<unique suffix>/`. Each new batch/revision gets a new folder; never delete or replace a previous result. Source results remain untouched. Reuse a pending folder on retry only after comparing remote content and hashes; do not duplicate a commit after an unknown outcome.

## Required batch contents

Include exact strategy code and its required local modules; frozen parameters, data scope and approval classification; environment/dependency versions or lockfiles; result CSV; individual entry/add/exit/roll/funding fills; fee, slippage, funding definitions and amounts; statistics/report; provenance/source hashes and reproducible commands. For a non-trading statistics batch, retain an empty fills CSV with schema and explain `NOT_APPLICABLE`; do not invent trades. Record missing inputs/costs as unknown, never zero. Record zero/not-applicable funding only when the product supports that conclusion.

Use an explicit file allowlist. Never upload `.env`, secrets, tokens, private keys, credentials, account numbers, raw HTTP authentication, live SQLite/WAL/SHM, or protected OOS material. Inspect code and configuration for embedded values and credential-bearing URLs. Scrub artifact copies only, preserving source originals. Add appropriate ignore rules to any actual publishing checkout. Never run `git add .` over the live project. A security or licensing restriction is a blocker to report, not permission to leak or silently drop an artifact.

Create `manifest.csv` with `path,role,bytes,sha256`. Roles must include `strategy_code`, `settings`, `results_csv`, `fills`, `costs`, `statistics_report`, and `environment`; use `support` for additional dependencies/notes. The manifest inventories every payload file except itself. Preserve unrounded result values and their units.

## Upload and verification gate

1. Run `python <skill-dir>/scripts/verify_batch.py <batch-dir>` and inspect the staged/explicit payload diff and secret scan findings. The helper rejects missing roles, unexpected files, unsafe paths, common credential literals, symlinks, and normal-Git files over 45 MiB; it is not a complete secret detector. Also inspect the allowlisted files and use an available dedicated scanner.
2. Publish all files as a commit through existing authenticated Git/CLI or the GitHub connector's tree/commit/ref API. The connector route is equivalent remote publication when local Git credentials/gh are unavailable. Preserve the existing tree using its base tree; advance the known branch with a lease and without force. Do not initialize or bulk commit the live workspace. Retry a transient error at most twice with backoff; inspect remote state after an unknown result or ref conflict. For auth/permission errors stop mutations and report the needed action.
3. Freshly fetch the remote branch into an isolated checkout, identify the uploaded commit SHA, and verify it remains reachable from the fetched branch. Do not rely only on a local commit or an upload API's success message.
4. Run `python <skill-dir>/scripts/verify_batch.py <batch-dir> <remote-checkout> <commit-sha> <remote-batch-prefix>`. This re-reads every payload file and manifest from that commit and compares exact bytes and SHA-256. Save a local publication receipt (repo URL, branch, SHA, prefix, verification time, expected/verified file counts, attempts/errors and any external archive evidence). Receipts that include their own publishing commit belong outside that immutable commit to avoid self-referential hashes.
5. Only after remote verification mark this batch `PUBLISHED_VERIFIED` and report batch completion. Otherwise report `LOCAL_COMPLETE_UPLOAD_BLOCKED`/`UPLOAD_FAILED`, the cause and retry outcome; preserve local results and checkpoint. Never claim the whole research is complete while any required batch upload remains unverified.

User-facing batch/final replies must include the GitHub repository link, exact commit SHA, remote batch folder, major result/report/fills paths, and any archive retrieval limitations. Upload each batch before moving on when practical; checkpoint unresolved upload failures rather than losing them. Never silently omit failed/empty research batches.

## Large artifacts

Do not discard, truncate, downsample, or replace an original with a summary because of upload size. Check the current provider/repository limits when encountered. Use already-authorized Git LFS or release assets when available; verify a fresh download of the actual payload, not an LFS pointer. For the no-purchase fallback, create a lossless archive split into pieces below 40 MiB in the same immutable batch, include part/original sizes and SHA-256 plus restoration commands, freshly download all parts, restore them, and compare original SHA-256. The complete archive must be accessible through the reported remote links. Do not start a paid storage plan. If limits or licensing prevent a complete retrievable archive, report the exact blocker and available options; the batch remains upload-blocked. Do not alter the source dataset or OOS protection to satisfy the upload.
