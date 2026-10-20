# Codex research archive rules — standing user instruction

This repository is the user's **public GitHub archive** for research outputs. A Windows research run must **not** use the local C: drive as the default location for reports, CSVs, transaction ledgers, batch artifacts, caches, temporary datasets or checkpoints.

## Mandatory skill

For each Codex trading-strategy study, backtest batch, result audit or report, load and apply:

`.agents/skills/github-backtest-report/SKILL.md`

This skill is the canonical updated version of the user's already installed `github-backtest-report`. If Codex is running from a different Windows worktree, first install/sync this skill into its discoverable local skills folder and copy these standing instructions to the local user/project `AGENTS.md` (see `INSTALL_WINDOWS_KO.md`). Do not falsely claim that a GitHub-only file changed local Codex settings.

## Permanent locations and publication

- All substantial **local** work, output, logs, scratch and checkpoints: `D:\Codex_Research\<project>\...` only.
- GitHub: every reviewable Korean report, complete candidate result CSV, cycle/fill/cost/risk source, settings, reproducible code and hashes must be published as immutable research batch files under `research-reports/`.
- Large canonical raw inputs stay single-copy on D: with source hashes; store shared code/data separately instead of duplicating tens of files in every 50-condition batch. If a required input is not remotely accessible, document that independent raw-data reproduction is incomplete.
- No batch is `PUBLISHED_VERIFIED` until files are fetched from the GitHub commit and hashes match. Provide the repo URL, commit SHA and report/result/fills paths after each batch. Report missing files and upload failures.
- Before a large run, check C: free >=10 GiB and D: free >=10 GiB plus expected growth. Pause work on low disk space, write errors or WSL EIO. Do not silently fall back to C:.

## Safeguards

Do not delete/restart or migrate currently paused USDT/KRW–KRX research, archived studies, Final OOS, WSL/OpenClaw, checkpoints, historical data or D: backups as a side effect of installing this rule. No live trading or USDT borrowing. Never expose tokens, API credentials, personal account data or protected data in this **public** repository.

Later explicit user instructions override these defaults in their stated scope. Preserve unrelated repository content.
