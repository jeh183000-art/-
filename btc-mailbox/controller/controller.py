#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAILBOX = ROOT / "btc-mailbox"
INBOX = MAILBOX / "inbox"
OUTBOX = MAILBOX / "outbox"
STATE_DIR = MAILBOX / "state"
CONTROLLER_STATE = STATE_DIR / "controller_state.json"

MODEL = os.environ.get("OPENAI_MODEL", "gpt-5.6-luna")
API_KEY = os.environ.get("OPENAI_API_KEY", "").strip()

GUARDRAILS = {
    "development_only": True,
    "train": "2022-2023",
    "validation": "2024-2025",
    "final_oos_access": False,
    "retune_rejected": False,
    "max_new_hypotheses_per_batch": 5,
    "raw_market_data_to_github": False,
    "proprietary_strategy_logic_to_github": False,
}

def load_json(path: Path, default):
    try:
        return json.loads(path.read_text())
    except Exception:
        return default

def newest_inbox_file() -> Path | None:
    files = [p for p in INBOX.glob("*.json") if p.is_file()]
    if not files:
        return None

    def commit_time(p: Path) -> int:
        rel = p.relative_to(ROOT).as_posix()
        r = subprocess.run(
            ["git", "log", "-1", "--format=%ct", "--", rel],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )
        try:
            return int(r.stdout.strip())
        except Exception:
            return 0

    return max(files, key=lambda p: (commit_time(p), p.name))

def content_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def collect_context(source: Path) -> dict:
    state = load_json(MAILBOX / "state" / "research_state.json", {})
    latest = load_json(MAILBOX / "results" / "latest.json", {})
    source_data = load_json(source, {})

    recent = []
    for p in sorted(INBOX.glob("*.json"))[-8:]:
        data = load_json(p, {})
        recent.append({"file": p.name, "summary": data})

    return {
        "source_file": source.name,
        "source_summary": source_data,
        "research_state": state,
        "latest_status": latest,
        "recent_public_summaries": recent,
        "guardrails": GUARDRAILS,
    }

def highest_hypothesis_id(ctx: dict) -> int:
    text = json.dumps(ctx, sort_keys=True)
    ids = [int(x) for x in re.findall(r"\bH(\d{3})\b", text)]
    return max(ids) if ids else 85

def call_openai(ctx: dict) -> dict:
    if not API_KEY:
        raise RuntimeError("OPENAI_API_KEY secret is not configured")

    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "action": {"type": "string", "enum": ["QUEUE_TASK", "STOP_REVIEW", "NOOP"]},
            "task_type": {"type": "string", "enum": ["DIAGNOSTIC", "DESIGN_AND_TEST", "AUDIT", "STOP"]},
            "target": {"type": "string"},
            "reason": {"type": "string"},
            "local_ai_calls": {"type": "integer", "minimum": 0, "maximum": 1},
        },
        "required": ["action", "task_type", "target", "reason", "local_ai_calls"],
    }

    instructions = """You are a conservative controller for a BTCUSDT development research loop.
You are NOT the backtester and you must not invent performance numbers.

Decide only the NEXT TASK TYPE from the public-safe summaries provided.
Never authorize Final OOS.
Never recommend retuning a rejected hypothesis.
Never put detailed trading rules or proprietary strategy logic in your output.
If a near-miss or suspicious result needs decomposition, choose DIAGNOSTIC.
If a completed batch is clearly rejected and diagnostics are already sufficient, choose DESIGN_AND_TEST.
If data/state integrity is unclear, choose AUDIT.
If there is a promoted candidate or a policy problem needing a human decision, choose STOP_REVIEW.
Use at most one local AI call for a DESIGN_AND_TEST task and zero for deterministic diagnostics/audits.
Return only the structured JSON requested by the response schema."""

    body = {
        "model": MODEL,
        "reasoning": {"effort": "low"},
        "input": [
            {
                "role": "developer",
                "content": [{"type": "input_text", "text": instructions}],
            },
            {
                "role": "user",
                "content": [{"type": "input_text", "text": json.dumps(ctx, ensure_ascii=False)}],
            },
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "btc_research_controller",
                "strict": True,
                "schema": schema,
            }
        },
        "max_output_tokens": 1200,
    }

    req = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI API HTTP {e.code}: {detail[:1000]}") from e

    chunks = []
    for item in payload.get("output", []):
        if item.get("type") != "message":
            continue
        for part in item.get("content", []):
            if part.get("type") == "output_text" and isinstance(part.get("text"), str):
                chunks.append(part["text"])
    if not chunks:
        raise RuntimeError("OpenAI response contained no output_text")

    return json.loads("".join(chunks))

def make_task(decision: dict, ctx: dict) -> dict | None:
    action = decision["action"]
    if action != "QUEUE_TASK":
        return None

    hmax = highest_hypothesis_id(ctx)
    task_type = decision["task_type"]
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    if task_type == "DESIGN_AND_TEST":
        start = hmax + 1
        end = start + 4
        task_id = f"DESIGN_AND_TEST_H{start:03d}_H{end:03d}"
        objective = (
            f"Using the private local failure map and registries, design exactly five structurally new "
            f"development-only hypotheses H{start:03d}-H{end:03d}, preregister them, then test them with Python. "
            f"Keep detailed hypothesis logic local."
        )
        max_ai = min(1, int(decision.get("local_ai_calls", 1)))
    elif task_type == "DIAGNOSTIC":
        safe_target = re.sub(r"[^A-Za-z0-9_.-]+", "_", decision.get("target", "latest"))
        task_id = f"DIAGNOSTIC_{safe_target}_{ts}"
        objective = (
            f"Diagnose {decision.get('target','the latest result')} using saved local results only. "
            f"Do not retune and do not rerun unless the task is impossible without a deterministic integrity check."
        )
        max_ai = 0
    elif task_type == "AUDIT":
        task_id = f"AUDIT_RESEARCH_STATE_{ts}"
        objective = (
            "Audit local result/state/registry consistency and reconcile stale state deterministically. "
            "Do not create new hypotheses during this task."
        )
        max_ai = 0
    else:
        return None

    return {
        "schema_version": 1,
        "task_id": task_id,
        "status": "READY",
        "created_by": "github-actions-openai-controller",
        "source_result": ctx["source_file"],
        "controller_reason": decision["reason"],
        "local_workspace": "/home/openclaw/btc_research",
        "objective": objective,
        "rules": {
            "development_only": True,
            "train": "2022-2023",
            "validation": "2024-2025",
            "final_oos_access": False,
            "retune_rejected": False,
            "max_ai_calls": max_ai,
            "python_for_computation": True,
            "raw_market_data_to_github": False,
            "proprietary_strategy_logic_to_github": False,
            "public_summary_only": True,
        },
        "execution": {
            "read_private_local_failure_map": True,
            "read_private_local_registries": True,
            "freeze_thresholds_on_train": True,
            "preserve_existing_next_minute_entry_exit_rules": True,
            "preserve_existing_funding_boundary_rules": True,
            "mark_completed_after_result_upload": True,
        },
        "github_result_policy": {
            "directory": "btc-mailbox/inbox",
            "redact_strategy_logic": True,
            "include_public_safe_metrics_only": True,
        },
    }

def write_controller_state(source: Path, source_hash: str, decision: dict, task_path: str | None):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    data = {
        "schema_version": 1,
        "processed_source": source.relative_to(ROOT).as_posix(),
        "processed_source_sha256": source_hash,
        "processed_at_utc": datetime.now(timezone.utc).isoformat(),
        "model": MODEL,
        "decision": decision,
        "queued_task": task_path,
        "final_oos": "locked",
    }
    CONTROLLER_STATE.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")

def main():
    source = newest_inbox_file()
    if source is None:
        print("No inbox JSON found; nothing to do.")
        return

    sha = content_hash(source)
    old = load_json(CONTROLLER_STATE, {})
    if old.get("processed_source_sha256") == sha:
        print(f"Already processed {source.name}; nothing to do.")
        return

    ctx = collect_context(source)
    decision = call_openai(ctx)

    if decision["action"] == "STOP_REVIEW":
        decision["task_type"] = "STOP"
        task_path = None
        print("Controller requested human review; no task queued.")
    else:
        task = make_task(decision, ctx)
        task_path = None
        if task:
            OUTBOX.mkdir(parents=True, exist_ok=True)
            filename = task["task_id"].lower() + ".json"
            p = OUTBOX / filename
            p.write_text(json.dumps(task, indent=2, sort_keys=True) + "\n")
            task_path = p.relative_to(ROOT).as_posix()
            print(f"Queued {task['task_id']} -> {task_path}")
        else:
            print("No task queued.")

    write_controller_state(source, sha, decision, task_path)

if __name__ == "__main__":
    main()
