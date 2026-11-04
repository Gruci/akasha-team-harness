"""The review of the plan of a task by another AI, in place of a person.

The agent engine writes research.md and plan.md, then asks the akasha-reviewer agent to review them. The reviewer
ends its answer with a mark: `AKASHA-REVIEW: <task> <plan digest> PASS` or `... CHANGES`. When the reviewer stops,
the hook (SubagentStop) reads the mark and records the verdict for that version of the plan. A change of the plan
after a pass needs a new review.

A quick task has no plan: the reviewer reviews its change with impact.md, and the mark holds the digest of the change
(quick.py).

The reviewer judges each item of a fixed list (the akasha-reviewer agent names them, ITEMS here), one row each:
`| R1 | PASS | <evidence> |`. A PASS mark counts only when each item of the task is PASS, or N/A where an item may be
N/A. Else Akasha records CHANGES with the reason, so that a mark alone never passes a plan. The answer of the reviewer
goes into review.md in the records: each change keeps why its plan passed."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

from akasha import quick
from akasha.task import PLAN, Task, digest, load, record, save

MARK = re.compile(r"AKASHA-REVIEW:\s*([a-z0-9][a-z0-9-]*)\s+([0-9a-f]{12})\s+(PASS|CHANGES)\b", re.I)
REVIEWER = "akasha-reviewer"
REVIEW = "review.md"
# The items of the review. A plan (of a task with a preview, or of an agent task) has R1 to R9; a quick task has a
# change and no plan, and has Q1 to Q3. agents/akasha-reviewer.md tells what each item asks
ITEMS = {"plan": tuple(f"R{number}" for number in range(1, 10)), "quick": ("Q1", "Q2", "Q3")}
MAY_BE_NA = ("R5", "R9")      # a change without a behavior needs no test; a change of no shared code no core rule
ROW = re.compile(r"^\s*\|\s*([RQ][0-9])\b[^|\n]*\|\s*(PASS|FAIL|N/A)\s*\|", re.I | re.M)


def items(task: Task) -> tuple[str, ...]:
    return ITEMS["quick" if quick.is_quick(task) else "plan"]


def verdicts(text: str) -> dict[str, str]:
    """The verdict of each item in the answer of the reviewer: item -> PASS, FAIL, or N/A. A later row wins."""
    return {item.upper(): verdict.upper() for item, verdict in ROW.findall(text or "")}


def problem(task: Task, found: dict[str, str]) -> str:
    """Why a PASS mark does not count, or "" when each item of the task passed."""
    wanted = items(task)
    missing = [item for item in wanted if item not in found]
    failed = [item for item in wanted if found.get(item) == "FAIL"]
    absent = [item for item in wanted if found.get(item) == "N/A" and item not in MAY_BE_NA]
    reasons = ([f"no verdict for {', '.join(missing)}"] if missing else []) + \
        ([f"{', '.join(failed)} failed"] if failed else []) + \
        ([f"{', '.join(absent)} cannot be N/A"] if absent else [])
    return "; ".join(reasons)


def told(task: Task) -> str:
    """The reason that the last PASS mark did not count, for the next step, or ""."""
    found = task.review.get("problem")
    return (f" The last PASS mark did not count ({found}): ask the reviewer again, with one row for each item."
            if found else "")


def plan_digest(task: Task) -> str:
    return digest(record(task, PLAN))


def subject_digest(task: Task) -> str:
    """The digest that a review mark names: of the plan, or of the change of a quick task."""
    return quick.digest(task) if quick.is_quick(task) else plan_digest(task)


def passed(task: Task) -> bool:
    """True when the reviewer passed the plan as it is now."""
    current = plan_digest(task)
    return bool(current) and task.review.get("verdict") == "PASS" and task.review.get("plan_sha") == current


def note(root: Path, task: Task, verdict: str, sha: str, source: str, found: dict[str, str] | None = None,
         why: str = "") -> None:
    rounds = int(task.review.get("rounds", 0)) + 1
    task.review = {"verdict": verdict.upper(), "plan_sha": sha, "at": time.strftime("%Y-%m-%d %H:%M"),
                   "source": source, "rounds": rounds, **({"items": found} if found else {}),
                   **({"problem": why} if why else {})}
    task.stats["review_rounds"] = rounds
    save(root, task)


def _keep(task: Task, verdict: str, sha: str, text: str) -> None:
    """Write the answer of the reviewer into review.md in the records: it merges with the change."""
    if not task.workcopy:
        return
    path = record(task, REVIEW)
    path.parent.mkdir(parents=True, exist_ok=True)
    rounds = task.review.get("rounds", 1)
    path.write_text(f"# Review of {task.id}\n\nRound {rounds} · {verdict} · digest `{sha}`\n\n{text.strip()}\n",
                    encoding="utf-8")


def _answers(path: str) -> tuple[str, str]:
    """The text of the last answer of the agent in a transcript file (JSON lines), and the last report that it
    handed back with the SubagentHandback tool (in auto mode the report goes there)."""
    try:
        lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines() if path else []
    except OSError:
        lines = []
    text, handback = "", ""
    for line in reversed(lines):
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        message = entry.get("message") if isinstance(entry, dict) else None
        if not isinstance(message, dict) or message.get("role") != "assistant":
            continue
        content = message.get("content")
        blocks = [{"type": "text", "text": content}] if isinstance(content, str) else content or []
        for block in (item for item in blocks if isinstance(item, dict)):
            if not text and block.get("type") == "text":
                text = str(block.get("text") or "")
            if not handback and block.get("type") == "tool_use" and block.get("name") == "SubagentHandback":
                handback = str((block.get("input") or {}).get("message") or "")
        if text and handback:
            break
    return text, handback


def on_subagent_stop(root: Path, payload: dict, agent: str = "claude") -> str:
    """Record each review mark of the reviewer agent. The mark counts only for the plan as it is now. In Claude Code
    only the akasha-reviewer agent reviews: a mark of another subagent does not count. Codex has no such agent, and
    its rules ask for a separate reviewer. A PASS mark without a passed row for each item counts as CHANGES."""
    if agent == "claude" and str(payload.get("agent_type") or "").split(":")[-1] != REVIEWER:
        return ""
    last, handback = _answers(str(payload.get("agent_transcript_path") or ""))
    text = f"{payload.get('last_assistant_message') or last}\n{handback}"
    found = verdicts(text)
    lines = []
    marks = dict.fromkeys((name.lower(), sha.lower(), verdict.upper()) for name, sha, verdict in MARK.findall(text))
    for task_id, sha, verdict in marks:
        try:
            task = load(root, task_id)
        except LookupError:
            continue
        what = "change" if quick.is_quick(task) else "plan"
        if sha != subject_digest(task):
            lines.append(f"the review mark of {task_id} is for another version of the {what}")
            continue
        why = problem(task, found) if verdict == "PASS" else ""
        note(root, task, "CHANGES" if why else verdict, sha, "reviewer", found, why)
        _keep(task, task.review["verdict"], sha, text)
        lines.append(f"the reviewer gave {task.review['verdict']} to the {what} of {task_id}"
                     + (f" (the PASS mark did not count: {why})" if why else ""))
    return "; ".join(lines)
