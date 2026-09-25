# OpenClaw mailbox runner

This runner uses no model while idle.

Every minute, OpenClaw's built-in automation scheduler runs `poll_and_run.py`. The script reads the public GitHub outbox. Only when it finds a new `status=READY` task does it start one OpenClaw agent turn.

Recommended one-time installation on the WSL/OpenClaw host:

```bash
mkdir -p /home/openclaw/btc_research/src
curl -fsSL "https://raw.githubusercontent.com/jeh183000-art/-/main/btc-mailbox/openclaw/poll_and_run.py" \
  -o /home/openclaw/btc_research/src/github_mailbox_poll_and_run.py
chmod +x /home/openclaw/btc_research/src/github_mailbox_poll_and_run.py

openclaw automations create "* * * * *" \
  --name "BTC GitHub Mailbox Runner" \
  --command-argv '["/usr/bin/python3","/home/openclaw/btc_research/src/github_mailbox_poll_and_run.py"]' \
  --command-cwd "/home/openclaw/btc_research" \
  --timeout-seconds 3700 \
  --no-deliver
```

Then verify with:

```bash
openclaw automations list
```

The runner keeps a local processed/attempt registry at:
`/home/openclaw/btc_research/.github_mailbox_runner_state.json`
