"""The shared task board: one GitHub issue with the label `akasha` for each task.

Each issue body holds a JSON block with the scope of the task, so that the Coordinator on any computer
can compare tasks. Without GitHub, the board holds only the tasks on this computer.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from akasha.core.task import Task, active, all_tasks
from akasha.repo import gh

LABEL = "akasha"
_BLOCK = re.compile(r"```akasha-scope\n(.*?)\n```", re.S)
_FIELDS = ("id", "title", "workflow", "stage", "status", "requester", "feature", "scope", "contracts", "risk")


def body(task: Task, summary: str = "") -> str:
    data = {name: getattr(task, name) for name in _FIELDS}
    text = summary or f"Requester: {task.requester or 'unknown'}\n\nStage: {task.stage} · Risk: {task.risk}"
    return f"{text}\n\n```akasha-scope\n{json.dumps(data, ensure_ascii=False, indent=2)}\n```\n"


def parse(text: str) -> Task | None:
    found = _BLOCK.search(text or "")
    if not found:
        return None
    try:
        data = json.loads(found.group(1))
        return Task(**{name: data[name] for name in _FIELDS if name in data})
    except (ValueError, TypeError):
        return None


def read(root: Path) -> tuple[list[Task], str]:
    """The tasks on the board and where Akasha read them: "github" or "local".

    An issue stays open until the pull request of its task merges, so the board also shows the tasks that wait
    for a merge. Without GitHub, the board holds the active tasks on this computer."""
    local = [task for task in all_tasks(root) if active(task)]
    listed = gh(root, "issue", "list", "--label", LABEL, "--state", "open", "--limit", "200", "--json", "body,url")
    if listed.returncode:
        return local, "local"
    remote = []
    for item in json.loads(listed.stdout or "[]"):
        task = parse(item.get("body", ""))
        if task is not None:
            task.board = item.get("url", "")
            remote.append(task)
    known = {task.id for task in remote}
    return remote + [task for task in local if task.id not in known], "github"


def comment(root: Path, address: str, text: str) -> None:
    """Write on the issue of a task. GitHub tells the people who follow the issue."""
    gh(root, "issue", "comment", address, "--body", text)


def publish(root: Path, task: Task) -> str:
    """Put the task on the shared board, or update its issue. Return the issue address, or "" without GitHub.

    The pull request closes the issue when it merges. Akasha closes the issue only when the task is cancelled."""
    title = f"[akasha] {task.title}"
    if task.board:
        gh(root, "issue", "edit", task.board, "--title", title, "--body", body(task))
        if task.status == "cancelled":
            gh(root, "issue", "close", task.board)
        return task.board
    gh(root, "label", "create", LABEL, "--color", "6d28d9", "--description", "Akasha task", "--force")
    made = gh(root, "issue", "create", "--label", LABEL, "--title", title, "--body", body(task))
    if made.returncode:
        return ""
    task.board = made.stdout.strip().splitlines()[-1]
    return task.board
