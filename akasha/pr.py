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
    if task.approval:
        lines.append(f"- Preview approved by @{task.approval.get('by', '?')} at {task.approval.get('at', '?')} "
                     f"(preview `{task.approval.get('preview_sha', '')}`)")
    else:
        lines.append("- Preview: not approved yet")
    if task.review:
        who = "the akasha-reviewer agent" if task.review.get("source") == "reviewer" else "the agent engine itself"
        lines.append(f"- Plan review: {task.review.get('verdict')} by {who} (round {task.review.get('rounds', 1)})")
    if task.checks:
        status = ", ".join(f"{name} {value}" for name, value in task.checks.get("status", {}).items())
        lines.append(f"- Checks on this computer: {status}")
    if task.scope:
        lines.append(f"- Planned files: {', '.join(f'`{item}`' for item in task.scope)}")
    lines.append(f"- Records: `{records(task.id)}/` (preview, research, plan, summary)")
    return lines


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
                   "state,isDraft,mergeStateStatus,statusCheckRollup,reviewDecision,headRefOid,baseRefName,url")
