# BTC Research Mailbox

GitHub mailbox between OpenClaw/Python and ChatGPT.

## Flow
1. OpenClaw/Python writes a compact result JSON to `btc-mailbox/inbox/`.
2. A research decision/spec is written to `btc-mailbox/outbox/`.
3. Human-readable cycle summaries can be written to `btc-mailbox/results/`.
4. `btc-mailbox/control/policy.json` is authoritative. Final OOS is locked unless the user explicitly changes that policy.

## Safety
- Do not upload raw market datasets.
- Do not upload credentials, API keys, cookies, tokens, or private environment files.
- This repository is PUBLIC. Keep detailed proprietary strategy logic out of the mailbox.
- Development split: TRAIN 2022-2023, VALIDATION 2024-2025.
- Final OOS access is disabled.

## Where to see results
Open `btc-mailbox/results/latest.json` for the current compact status, or inspect the newest file under `btc-mailbox/inbox/`.
