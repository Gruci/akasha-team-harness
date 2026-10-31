"""The review of the plan of a task by another AI, in place of a person.

The agent engine writes research.md and plan.md, then asks the akasha-reviewer agent to review them. The reviewer
ends its answer with a mark: `AKASHA-REVIEW: <task> <plan digest> PASS` or `... CHANGES`. When the reviewer stops,
the hook (SubagentStop) reads the mark and records the verdict for that version of the plan. A change of the plan
after a pass needs a new review."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

from akasha.task import PLAN, Task, digest, load, record, save

MARK = re.compile(r"AKASHA-REVIEW:\s*([a-z0-9][a-z0-9-]*)\s+([0-9a-f]{12})\s+(PASS|CHANGES)\b", re.I)


def plan_digest(task: Task) -> str:
    return digest(record(task, PLAN))


def passed(task: Task) -> bool:
    """True when the reviewer passed the plan as it is now."""
    current = plan_digest(task)
    return bool(current) and task.review.get("verdict") == "PASS" and task.review.get("plan_sha") == current


def note(root: Path, task: Task, verdict: str, sha: str, source: str) -> None:
    rounds = int(task.review.get("rounds", 0)) + 1
    task.review = {"verdict": verdict.upper(), "plan_sha": sha, "at": time.strftime("%Y-%m-%d %H:%M"),
                   "source": source, "rounds": rounds}
    task.stats["review_rounds"] = rounds
    save(root, task)


def _last_text(path: str) -> str:
    """The text of the last answer of the agent in a transcript file (JSON lines)."""
    try:
        lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    for line in reversed(lines):
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        message = entry.get("message") if isinstance(entry, dict) else None
        if not isinstance(message, dict) or message.get("role") != "assistant":
            continue
        content = message.get("content")
        if isinstance(content, str):
            return content
        return "\n".join(block.get("text", "") for block in content or [] if isinstance(block, dict))
    return ""


def on_subagent_stop(root: Path, payload: dict) -> str:
    """Record each review mark in the last answer of a subagent. The mark counts only for the plan as it is now."""
    text = str(payload.get("last_assistant_message") or "") or _last_text(
        str(payload.get("agent_transcript_path") or payload.get("transcript_path") or ""))
    told = []
    for task_id, sha, verdict in MARK.findall(text):
        try:
            task = load(root, task_id.lower())
        except LookupError:
            continue
        if sha.lower() != plan_digest(task):
            told.append(f"the review mark of {task_id} is for another version of the plan")
            continue
        note(root, task, verdict, sha.lower(), "reviewer")
        told.append(f"the reviewer gave {verdict.upper()} to the plan of {task_id}")
    return "; ".join(told)
