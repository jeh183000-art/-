#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import urllib.request
from pathlib import Path

OWNER = "jeh183000-art"
REPO = "-"
BRANCH = "main"
API = f"https://api.github.com/repos/{OWNER}/{REPO}/contents/btc-mailbox/outbox?ref={BRANCH}"
STATE = Path("/home/openclaw/btc_research/.github_mailbox_runner_state.json")
WORKDIR = Path("/home/openclaw/btc_research")
MAX_ATTEMPTS = 2

def http_json(url: str):
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "btc-research-openclaw-runner",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))

def load_state():
    if not STATE.exists():
        return {"processed": {}, "attempts": {}}
    try:
        return json.loads(STATE.read_text())
    except Exception:
        return {"processed": {}, "attempts": {}}

def save_state(s):
    STATE.write_text(json.dumps(s, indent=2, sort_keys=True) + "\n")

def ready_tasks():
    listing = http_json(API)
    tasks = []
    for item in listing:
        if item.get("type") != "file" or not item.get("name", "").endswith(".json"):
            continue
        data = http_json(item["download_url"])
        if data.get("status") == "READY" and data.get("task_id"):
            tasks.append((item["name"], data))
    tasks.sort(key=lambda x: x[0])
    return tasks

def run_task(name: str, task: dict) -> int:
    task_id = task["task_id"]
    prompt = f"""You are executing an automatically queued BTC research task from the GitHub mailbox.

Repository: {OWNER}/{REPO}
Mailbox file: btc-mailbox/outbox/{name}
Local workspace: /home/openclaw/btc_research

Execute the task below exactly.
Do not ask the user for confirmation.
Do not access Final OOS under any circumstance.
Keep proprietary strategy logic and raw market data off the public GitHub repository.
When complete, upload only the task-requested public-safe summary to btc-mailbox/inbox and mark the outbox task COMPLETED if your GitHub tooling permits it.
Then stop.

TASK JSON:
{json.dumps(task, ensure_ascii=False, indent=2)}
"""
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", suffix=".md", prefix="btc_task_", delete=False
    ) as f:
        f.write(prompt)
        prompt_path = f.name
    try:
        p = subprocess.run(
            [
                "openclaw", "agent",
                "--agent", "main",
                "--message-file", prompt_path,
                "--thinking", "low",
                "--timeout", "3600",
                "--json",
            ],
            cwd=WORKDIR,
            text=True,
        )
        return p.returncode
    finally:
        try:
            os.unlink(prompt_path)
        except OSError:
            pass

def main():
    s = load_state()
    for name, task in ready_tasks():
        task_id = task["task_id"]
        if s["processed"].get(task_id):
            continue
        attempts = int(s["attempts"].get(task_id, 0))
        if attempts >= MAX_ATTEMPTS:
            continue

        s["attempts"][task_id] = attempts + 1
        save_state(s)

        rc = run_task(name, task)
        if rc == 0:
            s["processed"][task_id] = True
            save_state(s)
        break  # one research task per polling tick

if __name__ == "__main__":
    main()
