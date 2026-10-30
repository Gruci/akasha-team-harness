"""The shared task board: one GitHub issue with the label `akasha` for each task.

Each issue body holds a JSON block with the scope of the task, so that the Coordinator on any computer
can compare tasks. Without GitHub, the board holds only the tasks on this computer.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from akasha.core.task import Task, all_tasks

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


def _gh(root: Path, *args: str) -> subprocess.CompletedProcess | None:
    try:
        return subprocess.run(["gh", *args], cwd=root, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return None


def open_tasks(root: Path) -> tuple[list[Task], str]:
    """The open tasks of all requesters and where Akasha read them: "github" or "local"."""
    listed = _gh(root, "issue", "list", "--label", LABEL, "--state", "open", "--limit", "200", "--json", "body")
    if listed is not None and listed.returncode == 0:
        tasks = [parse(item.get("body", "")) for item in json.loads(listed.stdout or "[]")]
        remote = [task for task in tasks if task is not None]
        local = [task for task in all_tasks(root) if task.status == "open"]
        known = {task.id for task in remote}
        return remote + [task for task in local if task.id not in known], "github"
    return [task for task in all_tasks(root) if task.status == "open"], "local"


def publish(root: Path, task: Task) -> str:
    """Put the task on the shared board, or update its issue. Return the issue address, or "" without GitHub."""
    title = f"[akasha] {task.title}"
    if task.board:
        _gh(root, "issue", "edit", task.board, "--title", title, "--body", body(task))
        if task.status != "open":
            _gh(root, "issue", "close", task.board)
        return task.board
    _gh(root, "label", "create", LABEL, "--color", "6d28d9", "--description", "Akasha task", "--force")
    made = _gh(root, "issue", "create", "--label", LABEL, "--title", title, "--body", body(task))
    if made is None or made.returncode:
        return ""
    task.board = made.stdout.strip().splitlines()[-1]
    return task.board
