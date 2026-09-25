# BTC Research Autopilot Controller

This controller is triggered whenever a public-safe result JSON is pushed to `btc-mailbox/inbox/`.

It calls the OpenAI Responses API with a low-cost controller model and decides only the next task category:
- diagnostic,
- audit,
- design-and-test,
- stop for review.

Detailed strategy design remains local to OpenClaw so it is not exposed in this PUBLIC repository.

## One-time setup

Add a GitHub Actions repository secret named:

`OPENAI_API_KEY`

Repository path:
Settings → Secrets and variables → Actions → New repository secret.

The workflow uses `gpt-5.6-luna` for low-cost routing. The secret is provided only to the workflow environment and must never be committed to the repository.

The workflow requires `contents: write` so it can commit the next READY task into `btc-mailbox/outbox/`.

## Safety invariants

- Final OOS is never authorized by this controller.
- Rejected hypotheses are not retuned.
- Raw market data is not uploaded.
- Detailed proprietary strategy logic is not written to GitHub.
- New batches are capped at 5 hypotheses.
