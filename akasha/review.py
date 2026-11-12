"""The two reviews of a task by another AI, in place of a person: of its plan before the build, and of its result
after the build.

The plan: the agent engine writes plan.md, then asks the akasha-reviewer agent to review it. The reviewer ends its
answer with a mark: `AKASHA-REVIEW: <task> <digest> PASS` or `... CHANGES`. When the reviewer stops, the hook
(SubagentStop) reads the mark and records the verdict for that version of the plan. A change of the plan after a
pass needs a new review. The review of the plan asks what is cheap to repair before any code is there: is what the
plan names real, what else does the change reach, does it use the code that exists, and can it be undone.

The result: after the checks passed, the same agent in a new context reads the preview, the plan, and the change
itself, and judges what a machine cannot see: is each rule built as the person approved it, with a test that proves
it; is the new code in the area that keeps that work; is no second code there for the same work. Its mark holds the
digest of the change, so a change of the code after a pass needs a new review. The result of a task is what merges,
so this review is the one that the server asks for (evidence.py).

A quick task has no plan: the reviewer reviews its change with impact.md, and the mark holds the digest of the change
(quick.py). That is its only review.

The reviewer judges each item of a fixed list (the akasha-reviewer agent names them, ITEMS here), one row each:
`| R1 | PASS | <evidence> |`. A PASS mark counts only when each item is PASS, or N/A where an item may be N/A. Else
Akasha records CHANGES with the reason, so that a mark alone never passes. The answer of the reviewer goes into
review.md (the plan) or result.md (the result) in the records: each change keeps why it passed.

A review after a repair of the plan need not judge each item again. Akasha keeps the rows of the last review of the
reviewer and the plan that it read; `akasha status <task> --review` gives the reviewer the items that did not pass
and the change of plan.md since then. The reviewer judges those again, and each item whose part of the plan changed,
and may answer `| R2 | KEPT | <why> |` for an item that passed and whose part did not change. Akasha replaces a KEPT
row with the row of the last review only when that row was PASS or N/A; else the PASS mark does not count. So
review.md still holds a row for each item, and the verdict still holds the digest of the current plan."""

from __future__ import annotations

import difflib
import hashlib
import json
import re
import time
from pathlib import Path

from akasha import forms, quick
from collections.abc import Callable, Iterable

from akasha.task import PLAN, PREVIEW, Task, digest, digest_of, load, own_records, record, save

MARK = re.compile(r"AKASHA-REVIEW:\s*([a-z0-9][a-z0-9-]*)\s+([0-9a-f]{12})\s+(PASS|CHANGES)\b", re.I)
REVIEWER = "akasha-reviewer"
REVIEW = "review.md"
RESULT = "result.md"
# The items of each review. A plan has R1 to R4: Real, Reach, Reuse, Undo. The result of a task has V1 to V5: Rules,
# Decisions, Place, One, Team. A quick task has a change and no plan, and has Q1 to Q3.
# agents/akasha-reviewer.md tells what each item asks
ITEMS = {"plan": ("R1", "R2", "R3", "R4"), "quick": ("Q1", "Q2", "Q3"), "result": ("V1", "V2", "V3", "V4", "V5")}
# A plan that makes no new code has nothing to reuse; a revert undoes most changes; a result without a new function
# has no second code for the same work
MAY_BE_NA = ("R3", "R4", "V4")
ROW = re.compile(r"^\s*\|\s*([RQV][0-9]+)\b[^|\n]*\|\s*(PASS|FAIL|N/A|KEPT)\s*\|([^\n]*)$", re.I | re.M)
KEEPS = ("PASS", "N/A")       # the verdicts of the last review that a KEPT row may keep
# What the review of the plan reads, by the kind of the task. One digest holds all of it: a preview that the person
# approved again needs a new review, as a plan that changed does. A quick task has its change
INPUTS = {"full": (PLAN, PREVIEW), "no-screen": (PLAN,), "agent": (PLAN, "request.md")}
# The kinds of task whose result is reviewed after the build. A quick task has the review of its change
RESULT_KINDS = ("full", "no-screen", "agent")
# The first line of review.md: the round, the verdict, the digest of what the review read, and who reviewed
FIRST = re.compile(r"^Round (\d+) · (PASS|CHANGES) · digest `([0-9a-f]{12})`(?: · ([\w-]+))?[ \t\r]*$", re.M)
ANSWER = "## The answer of the reviewer"


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
    if result_needed(task) and passed(task) and task.checks.get("commit") and result_digest(task):
        now = result_digest(task)
        if result_passed(task):
            return f"Round {task.result.get('rounds', 1)} passed this result (digest {now}): it needs no new review."
        return (f"The review of the result: the plan passed, and the checks passed on the build. Read the change "
                f"itself, and judge each item, {', '.join(ITEMS['result'])}. Result digest {now}."
                + (f" The last review of the result gave {task.result.get('verdict')}"
                   + (f" ({task.result['problem']})" if task.result.get("problem") else "")
                   + ": judge each item again." if task.result else ""))
    last = _last(task)
    if not last:
        return f"No earlier review of the akasha-reviewer agent to build on: judge each item, {', '.join(wanted)}."
    rounds, before = task.review.get("rounds", 1), task.review["plan"]
    if passed(task):
        return f"Round {rounds} passed this version of the plan: it needs no new review."
    read, now = task.review.get("inputs") or {}, inputs(task)
    moved = [name for name in now if name != PLAN and read.get(name) != now[name]]
    keep = [item for item in wanted if (last.get(item) or {}).get("verdict") in KEEPS]
    again = [item for item in wanted if item not in keep]
    change = "".join(difflib.unified_diff(before.splitlines(True), _plan_text(task).splitlines(True),
                                          f"plan.md (round {rounds})", "plan.md (now)"))
    return "\n".join([
        f"Last review: round {rounds} · {task.review.get('verdict')} · digest {task.review.get('plan_sha')}",
        f"Judge again: {', '.join(again) or 'none'}.",
        f"May keep, only when the change below does not touch its part of the plan and you have no doubt: "
        f"{', '.join(keep) or 'none'}. Write `| <item> | KEPT | <why> |` for each item that you keep.",
        *([f"Changed since round {rounds}, beside the plan: {', '.join(moved)}. Read them again: an item that "
           "they touch cannot be kept."] if moved else []),
        f"The change of plan.md since round {rounds}:", change.rstrip("\n") or "(none)"])


def problem(task: Task, found: dict[str, str]) -> str:
    """Why a PASS mark does not count, or "" when each item of the task passed."""
    return problem_of(items(task), found)


def problem_of(wanted: Iterable[str], found: dict[str, str]) -> str:
    """Why the verdicts `found` do not pass each item of `wanted`, or ""."""
    wanted = tuple(wanted)
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


def input_digests(kind: str, read: Callable[[str], bytes | None]) -> dict[str, str]:
    """The digest of each file that the review of a task of this kind reads, in a fixed order: name -> digest, or
    "" for a file that is not there. `read` gives the bytes of a record. No path of a computer goes in."""
    found = {}
    for name in INPUTS.get(kind, INPUTS["full"]):
        data = read(name)
        # A form that nobody filled is a file that is not there (forms.py)
        found[name] = digest_of(data) if data is not None and not forms.is_form(data) else ""
    return found


def combined(found: dict[str, str]) -> str:
    """One digest of the input of a review, or "" when a file is missing."""
    if not found or not all(found.values()):
        return ""
    return hashlib.sha256("\n".join(f"{name} {sha}" for name, sha in found.items()).encode()).hexdigest()[:12]


def inputs(task: Task) -> dict[str, str]:
    """The digest of each file that the review of the task reads, from the work copy."""
    def read(name: str) -> bytes | None:
        try:
            return record(task, name).read_bytes()
        except OSError:
            return None
    return input_digests(task.kind, read) if task.workcopy else {}


def subject_digest(task: Task) -> str:
    """The digest that a review mark names: of the input of the review (the plan, and what the plan answers), or
    of the change of a quick task. Each place uses this one: the request and the mark of a review, passed(), the
    gate, the review of the agent engine itself, and the evidence of the server."""
    return quick.digest(task) if quick.is_quick(task) else combined(inputs(task))


def change_text(tree: Path, start: str, own: Iterable[str], end: str = "") -> str:
    """The lines that a change adds and removes since `start`, file by file, without the records of the task (the
    folders `own`): of the work copy, or up to the commit `end`. Only those lines count, not where they are and not
    what is around them: a merge of the default branch that moves a line of the task, or changes another part of
    the same file, changes nothing of this text. So a result that passed its review still holds after the landing
    brings the task up to date."""
    from akasha.repo import git
    from akasha.task import each
    shown = git(tree, "-c", "core.quotePath=false", "-c", "diff.algorithm=myers", "diff", "--no-renames",
                "--no-color", "--no-ext-diff", "--no-textconv", "-U0", "--src-prefix=a/", "--dst-prefix=b/",
                start, *([end] if end else []), "--", ".",
                *(f":(exclude){folder.rstrip('/')}/**" for folder in each(own)))
    kept = [line for line in shown.stdout.replace("\r\n", "\n").splitlines()
            if line.startswith(("+", "-")) or line.startswith("Binary files ")]
    return "\n".join(kept)


def change_digest(tree: Path, start: str, own: Iterable[str], end: str = "") -> str:
    """The digest of the result of a task: of the lines that its change adds and removes. "" for no change."""
    text = change_text(tree, start, own, end)
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:12] if text else ""


def result_needed(task: Task) -> bool:
    """True for a task whose result the reviewer judges after the build."""
    return task.kind in RESULT_KINDS


def result_digest(task: Task) -> str:
    """The digest of the result of the task as the work copy has it now, or "" before any change."""
    if not task.workcopy or not result_needed(task):
        return ""
    tree = Path(task.workcopy)
    return change_digest(tree, quick.base(tree), own_records(task))


def result_passed(task: Task) -> bool:
    """True when the reviewer passed the result as it is now."""
    current = result_digest(task)
    return bool(current) and task.result.get("verdict") == "PASS" and task.result.get("sha") == current


def result_told(task: Task) -> str:
    found = task.result.get("problem")
    return (f" The last PASS mark did not count ({found}): ask the reviewer again, with one row for each item."
            if found else "")


def note_result(root: Path, task: Task, verdict: str, sha: str, source: str, rows: dict[str, dict] | None = None,
                why: str = "") -> None:
    """Record the verdict of a review of the result."""
    rounds = int(task.result.get("rounds", 0)) + 1
    task.result = {"verdict": verdict.upper(), "sha": sha, "at": time.strftime("%Y-%m-%d %H:%M"), "source": source,
                   "rounds": rounds, **({"problem": why} if why else {}), **({"rows": rows} if rows else {})}
    task.stats["result_rounds"] = rounds
    save(root, task)


def keep_result(task: Task, text: str) -> None:
    """Write the answer of the review of the result into result.md in the records: it merges with the change, and
    the server reads the verdict from it (evidence.py)."""
    if not task.workcopy:
        return
    path = record(task, RESULT)
    path.parent.mkdir(parents=True, exist_ok=True)
    said, rows = task.result, task.result.get("rows") or {}
    table = ["| Item | Verdict | Evidence |", "|:--|:--|:--|"]
    for item in ITEMS["result"]:
        row = rows.get(item) or {"verdict": "—", "evidence": "no row"}
        table.append(f"| {item} | {row['verdict']} | {row['evidence']} |")
    source = str(said.get("source") or "reviewer")
    path.write_text(f"# Review of the result of {task.id}\n\nRound {said.get('rounds', 1)} · {said.get('verdict')} · "
                    f"digest `{said.get('sha')}` · {source}\n\n"
                    + ("## The items\n\n" + "\n".join(table) + "\n\n" if rows or source != "self" else "")
                    + f"{ANSWER}\n\n{text.strip()}\n", encoding="utf-8")


def take_result(root: Path, task: Task, verdict: str, sha: str, source: str, text: str) -> str:
    """Record the answer of a reviewer about the result, and give the line that tells it. A PASS mark without a
    passed row for each item counts as CHANGES."""
    answered = answer_rows(text)
    rows = {item: {"verdict": said, "evidence": evidence} for item, (said, evidence) in answered.items()
            if item in ITEMS["result"]}
    found = {item: row["verdict"] for item, row in rows.items()}
    why = problem_of(ITEMS["result"], found) if verdict == "PASS" else ""
    note_result(root, task, "CHANGES" if why else verdict, sha, source, rows, why)
    keep_result(task, text)
    return (f"the reviewer gave {task.result['verdict']} to the result of {task.id}"
            + (f" (the PASS mark did not count: {why})" if why else ""))


def parse(text: str) -> dict:
    """What review.md tells: the round, the verdict, the digest, who reviewed, and the verdict of each item. {}
    when the file has no first line of a review. The answer of the reviewer below the table does not count: its
    KEPT rows are in the table as the rows that they keep."""
    found = FIRST.search(text or "")
    if not found:
        return {}
    return {"round": int(found.group(1)), "verdict": found.group(2), "digest": found.group(3),
            "source": found.group(4) or "reviewer", "rows": verdicts((text or "").split(ANSWER)[0])}


def passed(task: Task) -> bool:
    """True when the review passed its input as it is now: the plan, and the files that the plan answers."""
    current = combined(inputs(task))
    return bool(current) and task.review.get("verdict") == "PASS" and task.review.get("plan_sha") == current


def note(root: Path, task: Task, verdict: str, sha: str, source: str, found: dict[str, str] | None = None,
         why: str = "", rows: dict[str, dict] | None = None, plan: str | None = None,
         read: dict[str, str] | None = None) -> None:
    """Record a verdict. `rows` and `plan` (the rows of the reviewer and the plan that it read) let the next review
    keep the rows that passed."""
    rounds = int(task.review.get("rounds", 0)) + 1
    task.review = {"verdict": verdict.upper(), "plan_sha": sha, "at": time.strftime("%Y-%m-%d %H:%M"),
                   "source": source, "rounds": rounds, **({"items": found} if found else {}),
                   **({"problem": why} if why else {}), **({"rows": rows} if rows else {}),
                   **({"plan": plan} if plan is not None else {}), **({"inputs": read} if read else {})}
    task.stats["review_rounds"] = rounds
    save(root, task)


def keep(task: Task, verdict: str, sha: str, text: str) -> None:
    """Write the answer of the review into review.md in the records: it merges with the change, and the server
    reads the verdict from it (evidence.py). The first line tells who reviewed; the next one, the digest of each
    file that the review read. review.md itself is no input of a review."""
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
    source = str(task.review.get("source") or "reviewer")
    read = "".join(f"- `{name}` `{digest}`\n" for name, digest in (task.review.get("inputs") or {}).items())
    path.write_text(f"# Review of {task.id}\n\nRound {rounds} · {verdict} · digest `{sha}` · {source}\n\n"
                    + (f"What the review read:\n\n{read}\n" if read else "")
                    + ("## The items\n\n" + "\n".join(table) + "\n\n" if rows or source != "self" else "")
                    + f"{ANSWER}\n\n{text.strip()}\n", encoding="utf-8")


def _answers(path: str) -> tuple[str, str]:
    """Each text of the agent in the last round of a transcript file (JSON lines), in its order, and the last
    report that it handed back with the SubagentHandback tool (in auto mode the report goes there). The reviewer
    can write its table before its last tool call and end with a short report: the table is in an earlier text of
    the same round. Both come from the last round only: an agent that was asked again keeps its earlier rounds
    in the file, and an earlier report is not this answer."""
    try:
        lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines() if path else []
    except OSError:
        lines = []
    texts: list[str] = []
    handback = ""
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
        said = []
        for block in (item for item in blocks if isinstance(item, dict)):
            if block.get("type") == "text":
                said.append(str(block.get("text") or ""))
            if not handback and block.get("type") == "tool_use" and block.get("name") == "SubagentHandback":
                handback = str((block.get("input") or {}).get("message") or "")
        texts[:0] = said                              # the lines come last first: keep the order of the round
    return "\n".join(text for text in texts if text), handback


def on_subagent_stop(root: Path, payload: dict, agent: str = "claude") -> str:
    """Record each review mark of the reviewer agent. The mark counts only for the plan as it is now. In Claude Code
    only the akasha-reviewer agent reviews: a mark of another subagent does not count. Codex has no such agent, and
    its rules ask for a separate reviewer. A PASS mark without a passed row for each item counts as CHANGES. A KEPT row
counts as the row of the last review only when that row passed."""
    if agent == "claude" and str(payload.get("agent_type") or "").split(":")[-1] != REVIEWER:
        return ""
    said, handback = _answers(str(payload.get("agent_transcript_path") or ""))
    # Each text of the round counts, also when the last message is only a short report: the table of the items can
    # be in an earlier text. Without the table, a PASS mark does not count (problem)
    last = str(payload.get("last_assistant_message") or "")
    text = "\n".join(part for part in (said, handback, last if last not in said else "") if part)
    answered = answer_rows(text)
    lines = []
    marks = dict.fromkeys((name.lower(), sha.lower(), verdict.upper()) for name, sha, verdict in MARK.findall(text))
    for task_id, sha, verdict in marks:
        try:
            task = load(root, task_id)
        except LookupError:
            continue
        what = "change" if quick.is_quick(task) else "plan"
        if sha != subject_digest(task) and sha == result_digest(task):
            lines.append(take_result(root, task, verdict, sha, "reviewer", text))
            continue
        if sha != subject_digest(task):
            lines.append(f"the review mark of {task_id} is for another version of the {what}")
            continue
        rows = carry(task, answered)
        found = {item: row["verdict"] for item, row in rows.items()}
        why = problem(task, found) if verdict == "PASS" else ""
        note(root, task, "CHANGES" if why else verdict, sha, "reviewer", found, why, rows,
             None if quick.is_quick(task) else _plan_text(task), None if quick.is_quick(task) else inputs(task))
        keep(task, task.review["verdict"], sha, text)
        lines.append(f"the reviewer gave {task.review['verdict']} to the {what} of {task_id}"
                     + (f" (the PASS mark did not count: {why})" if why else ""))
    return "; ".join(lines)
