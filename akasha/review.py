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
goes into review.md in the records: each change keeps why its plan passed.

A review after a repair of the plan need not judge each item again. Akasha keeps the rows of the last review of the
reviewer and the plan that it read; `akasha status <task> --review` gives the reviewer the items that did not pass
and the change of plan.md since then. The reviewer judges those again, and each item whose part of the plan changed,
and may answer `| R2 | KEPT | <why> |` for an item that passed and whose part did not change. Akasha replaces a KEPT
row with the row of the last review only when that row was PASS or N/A; else the PASS mark does not count. So
review.md still holds a row for each item, and the verdict still holds the digest of the current plan."""

from __future__ import annotations

import difflib
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
ROW = re.compile(r"^\s*\|\s*([RQ][0-9])\b[^|\n]*\|\s*(PASS|FAIL|N/A|KEPT)\s*\|([^\n]*)$", re.I | re.M)
KEEPS = ("PASS", "N/A")       # the verdicts of the last review that a KEPT row may keep


def items(task: Task) -> tuple[str, ...]:
    return ITEMS["quick" if quick.is_quick(task) else "plan"]


def answer_rows(text: str) -> dict[str, tuple[str, str]]:
    """The row of each item in the answer of the reviewer: item -> (verdict, evidence). A later row wins."""
    return {item.upper(): (verdict.upper(), evidence.strip().rstrip("|").strip())
            for item, verdict, evidence in ROW.findall(text or "")}


def verdicts(text: str) -> dict[str, str]:
    """The verdict of each item in the answer of the reviewer: item -> PASS, FAIL, N/A, or KEPT. A later row wins."""
    return {item: verdict for item, (verdict, _evidence) in answer_rows(text).items()}


def _plan_text(task: Task) -> str:
    try:
        return record(task, PLAN).read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n")
    except OSError:
        return ""


def _last(task: Task) -> dict:
    """The rows of the last review that a KEPT row may keep: only of the reviewer agent, of a plan, with the plan
    that it read. Else {}."""
    if quick.is_quick(task) or task.review.get("source") != "reviewer" or "plan" not in task.review:
        return {}
    return task.review.get("rows") or {}


def carry(task: Task, found: dict[str, tuple[str, str]]) -> dict[str, dict]:
    """The rows of this answer, each KEPT row replaced by the row of the last review when that row was PASS or N/A.
    A KEPT row without such a row stays KEPT, and problem() refuses it."""
    last, rounds = _last(task), int(task.review.get("rounds", 0)) + 1
    rows = {}
    for item, (verdict, evidence) in found.items():
        before = last.get(item) or {}
        rows[item] = (dict(before) if verdict == "KEPT" and before.get("verdict") in KEEPS else
                      {"verdict": verdict, "evidence": evidence, "round": rounds})
    return rows


def brief(task: Task) -> str:
    """What the reviewer judges again, for `akasha status <task> --review`: the items that did not pass the last
    review, the items that it may keep, and the change of plan.md since that review."""
    wanted = items(task)
    if quick.is_quick(task):
        return f"A quick task: judge each item, {', '.join(wanted)}."
    last = _last(task)
    if not last:
        return f"No earlier review of the akasha-reviewer agent to build on: judge each item, {', '.join(wanted)}."
    rounds, before = task.review.get("rounds", 1), task.review["plan"]
    if passed(task):
        return f"Round {rounds} passed this version of the plan: it needs no new review."
    keep = [item for item in wanted if (last.get(item) or {}).get("verdict") in KEEPS]
    again = [item for item in wanted if item not in keep]
    change = "".join(difflib.unified_diff(before.splitlines(True), _plan_text(task).splitlines(True),
                                          f"plan.md (round {rounds})", "plan.md (now)"))
    return "\n".join([
        f"Last review: round {rounds} · {task.review.get('verdict')} · plan digest {task.review.get('plan_sha')}",
        f"Judge again: {', '.join(again) or 'none'}.",
        f"May keep, only when the change below does not touch its part of the plan and you have no doubt: "
        f"{', '.join(keep) or 'none'}. Write `| <item> | KEPT | <why> |` for each item that you keep.",
        f"The change of plan.md since round {rounds}:", change.rstrip("\n") or "(none)"])


def problem(task: Task, found: dict[str, str]) -> str:
    """Why a PASS mark does not count, or "" when each item of the task passed."""
    wanted = items(task)
    missing = [item for item in wanted if item not in found]
    failed = [item for item in wanted if found.get(item) == "FAIL"]
    absent = [item for item in wanted if found.get(item) == "N/A" and item not in MAY_BE_NA]
    kept = [item for item in wanted if found.get(item) == "KEPT"]
    reasons = ([f"no verdict for {', '.join(missing)}"] if missing else []) + \
        ([f"{', '.join(failed)} failed"] if failed else []) + \
        ([f"{', '.join(absent)} cannot be N/A"] if absent else []) + \
        ([f"{', '.join(kept)} cannot be kept: not PASS in the last review of the reviewer"] if kept else [])
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
         why: str = "", rows: dict[str, dict] | None = None, plan: str | None = None) -> None:
    """Record a verdict. `rows` and `plan` (the rows of the reviewer and the plan that it read) let the next review
    keep the rows that passed."""
    rounds = int(task.review.get("rounds", 0)) + 1
    task.review = {"verdict": verdict.upper(), "plan_sha": sha, "at": time.strftime("%Y-%m-%d %H:%M"),
                   "source": source, "rounds": rounds, **({"items": found} if found else {}),
                   **({"problem": why} if why else {}), **({"rows": rows} if rows else {}),
                   **({"plan": plan} if plan is not None else {})}
    task.stats["review_rounds"] = rounds
    save(root, task)


def _keep(task: Task, verdict: str, sha: str, text: str) -> None:
    """Write the answer of the reviewer into review.md in the records: it merges with the change."""
    if not task.workcopy:
        return
    path = record(task, REVIEW)
    path.parent.mkdir(parents=True, exist_ok=True)
    rounds, rows = task.review.get("rounds", 1), task.review.get("rows") or {}
    table = ["| Item | Verdict | Evidence |", "|:--|:--|:--|"]
    for item in items(task):
        row = rows.get(item) or {"verdict": "—", "evidence": "no row", "round": rounds}
        kept = f" (kept from round {row['round']})" if row.get("round", rounds) != rounds else ""
        table.append(f"| {item} | {row['verdict']} | {row['evidence']}{kept} |")
    path.write_text(f"# Review of {task.id}\n\nRound {rounds} · {verdict} · digest `{sha}`\n\n## The items\n\n"
                    + "\n".join(table) + f"\n\n## The answer of the reviewer\n\n{text.strip()}\n", encoding="utf-8")


def _answers(path: str) -> tuple[str, str]:
    """The text of the last answer of the agent in a transcript file (JSON lines), and the last report that it
    handed back with the SubagentHandback tool (in auto mode the report goes there). Both come from the last round
    only: an agent that was asked again keeps its earlier rounds in the file, and an earlier report is not this
    answer."""
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
        if isinstance(message, dict) and message.get("role") == "user" and not entry.get("isMeta"):
            content = message.get("content")
            if isinstance(content, str) or any(isinstance(block, dict) and block.get("type") == "text"
                                               for block in content or []):
                break                      # the request of this round: an earlier round is not this answer
            continue                       # a tool result inside this round
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
    its rules ask for a separate reviewer. A PASS mark without a passed row for each item counts as CHANGES. A KEPT row
counts as the row of the last review only when that row passed."""
    if agent == "claude" and str(payload.get("agent_type") or "").split(":")[-1] != REVIEWER:
        return ""
    last, handback = _answers(str(payload.get("agent_transcript_path") or ""))
    text = f"{payload.get('last_assistant_message') or last}\n{handback}"
    answered = answer_rows(text)
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
        rows = carry(task, answered)
        found = {item: row["verdict"] for item, row in rows.items()}
        why = problem(task, found) if verdict == "PASS" else ""
        note(root, task, "CHANGES" if why else verdict, sha, "reviewer", found, why, rows,
             None if quick.is_quick(task) else _plan_text(task))
        _keep(task, task.review["verdict"], sha, text)
        lines.append(f"the reviewer gave {task.review['verdict']} to the {what} of {task_id}"
                     + (f" (the PASS mark did not count: {why})" if why else ""))
    return "; ".join(lines)
