"""The pull request of a task: its body, and the calls of gh that change it."""

from __future__ import annotations

import re
from pathlib import Path

from akasha.config import LABEL
from akasha.repo import gh, gh_json
from akasha.task import SUMMARY, Task, block, record, records

DRAFT_TEXT = ("This task is in progress with Akasha. The person who holds it approves its preview first; the AI then "
              "plans, builds, checks, and lands it.")


def meta(task: Task) -> list[str]:
    """The lines that tell how the task was approved, reviewed, and checked."""
    lines = []
    if task.kind == "quick":
        checked = ("the reviewer examined the change with impact.md" if task.review else
                   "it changes only text for people, so it needs no review")
        lines.append("- Kind: quick change — no preview of the result and no plan. It changes only existing files "
                     f"that no other area uses; {checked}, and the person approved the change itself")
    if task.kind == "agent":
        lines.append("- Kind: agent task — an agent account worked from the request of a person (request.md), "
                     "without a preview. The person approves the result before the merge")
        lines.append(_result_line(task))
    elif task.kind == "no-screen":
        lines.append("- Kind: task without a screen — an administrator's change that touches no screen file "
                     "(`[preview] screens`). The person approves the plan after its review, in place of a preview")
        lines.append(f"- Plan approved by @{task.approval.get('by', '?')} at {task.approval.get('at', '?')} with "
                     f"\"{task.approval.get('words', '')}\" (plan `{task.approval.get('plan_sha', '')}`)"
                     if task.approval else "- Plan: not approved yet")
    elif task.approval:
        lines.append(f"- Preview approved by @{task.approval.get('by', '?')} at {task.approval.get('at', '?')} "
                     f"with \"{task.approval.get('words', '')}\" (preview `{task.approval.get('preview_sha', '')}`)")
    else:
        lines.append("- Preview: not approved yet")
    if task.review:
        who = "the akasha-reviewer agent" if task.review.get("source") == "reviewer" else "the agent engine itself"
        what = "Change review" if task.kind == "quick" else "Plan review"
        lines.append(f"- {what}: {task.review.get('verdict')} by {who} (round {task.review.get('rounds', 1)})"
                     + _items(task.review))
    if task.checks:
        status = ", ".join(f"{name} {value}" for name, value in task.checks.get("status", {}).items())
        lines.append(f"- Checks on this computer: {status}")
    found = task.checks.get("core") or {}
    if found:
        state = f"approved by @{task.checks['core_approved_by']}" if task.checks.get("core_approved_by") else \
            "waits for an approval of an administrator"
        lines.append(f"- Core changes: {', '.join(f'`{name}`' for name in found)} — {state}")
    if task.scope:
        lines.append(f"- Planned files: {', '.join(f'`{item}`' for item in task.scope)}")
    kept = {"quick": "impact, preview, review, summary", "agent": "request, research, plan, review, summary",
            "no-screen": "research, plan, review, summary"}.get(task.kind, "preview, research, plan, review, summary")
    lines.append(f"- Records: `{records(task)}/` ({kept})")
    return lines


def _items(review: dict) -> str:
    """The verdict of each item of the review, in short: 'R1–R9 PASS (N/A R9)', or why a PASS mark did not count."""
    found = review.get("items") or {}
    if review.get("problem"):
        return f" — the PASS mark did not count: {review['problem']}"
    if not found:
        return ""
    if review.get("verdict") != "PASS":
        failed = sorted(name for name, verdict in found.items() if verdict == "FAIL")
        return f" — failed: {', '.join(failed)}, see review.md" if failed else ""
    names = sorted(found)
    span = f"{names[0]}–{names[-1]}" if len(names) > 1 else names[0]
    unused = [name for name, verdict in found.items() if verdict == "N/A"]
    return f" — {span} PASS" + (f" (N/A {', '.join(unused)})" if unused else "") + ", see review.md"


def _result_line(task: Task) -> str:
    """Who approved the result of an agent task. The relay names the person; else it is the agent account."""
    found = task.approval
    if found.get("source") != "result":
        return "- Result: not approved yet"
    through = str(found.get("through") or "?")
    who = f"@{through}" if found.get("by") == through else f"{found.get('by')} through @{through}"
    return (f"- Result approved by {who} at {found.get('at', '?')} with \"{found.get('words', '')}\" (change "
            f"`{found.get('change_sha', '')}`)")


def summary(task: Task) -> str:
    path = record(task, SUMMARY)
    return path.read_text(encoding="utf-8").strip() if path.is_file() else DRAFT_TEXT


def body(task: Task) -> str:
    return (f"{summary(task)}\n\n---\n<details><summary>Akasha</summary>\n\n" + "\n".join(meta(task))
            + f"\n\n</details>\n\n{block(task)}\n")


def commit_body(task: Task) -> str:
    """The body of the squash commit: the summary and the record lines, without the hidden block."""
    return summary(task) + "\n\n" + "\n".join(meta(task)) + "\n"


def number(address: str) -> int:
    found = re.search(r"/pull/(\d+)", address or "")
    return int(found.group(1)) if found else 0


def ensure_label(root: Path) -> None:
    """Make the label of the board when nobody made it yet. A failure is no problem: gh pr create tells it."""
    gh(root, "label", "create", LABEL, "--color", "6d28d9", "--description", "A task of Akasha")


def create(root: Path, task: Task, base: str) -> str:
    ensure_label(root)
    done = gh(root, "pr", "create", "--draft", "--base", base, "--head", task.branch, "--title", task.title,
              "--body", body(task), "--label", LABEL, "--assignee", "@me")
    if done.returncode:
        raise RuntimeError(f"gh pr create failed: {done.stderr.strip()[:300]}")
    return done.stdout.strip().splitlines()[-1]


def update(root: Path, task: Task) -> bool:
    """Write the state of the task into its pull request. False when gh fails: the next step writes it again."""
    if not task.number:
        return False
    return gh(root, "pr", "edit", str(task.number), "--title", task.title, "--body", body(task)).returncode == 0


def view(root: Path, task: Task) -> dict | None:
    return gh_json(root, "pr", "view", str(task.number), "--json",
                   "state,isDraft,mergeStateStatus,statusCheckRollup,reviewDecision,headRefOid,baseRefName,url,author,"
                   "autoMergeRequest,mergeCommit")
