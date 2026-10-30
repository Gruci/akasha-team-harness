"""The shared task board: one GitHub issue with the label `akasha` for each task.

Each issue body holds a JSON block with the scope of the task, so that the Coordinator on any computer
can compare tasks. Without GitHub, the board holds only the tasks on this computer.

When origin is a GitHub repository, the board must work. A failed read or write of the board stops the command,
so that a person who is not logged in to gh does not work where the other people cannot see the task.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from akasha import repo
from akasha.core.task import Task, active, all_tasks, load
from akasha.repo import gh

LABEL = "akasha"
_BLOCK = re.compile(r"```akasha-scope\n(.*?)\n```", re.S)
_COMMENT_NUMBER = re.compile(r"#issuecomment-(\d+)$")
_FIELDS = ("id", "title", "workflow", "stage", "status", "requester", "feature", "scope", "contracts", "risk",
           "conditions", "accepted", "builds_on", "pull_request")


class BoardError(RuntimeError):
    """The shared task board is on GitHub, but gh cannot read or write it."""


@dataclass(frozen=True)
class Comment:
    """One comment on the issue of a task."""
    number: int             # the number in the comment address: #issuecomment-<number>
    author: str             # the GitHub name of the account that wrote the comment
    association: str        # the authorAssociation of GitHub, for example OWNER, MEMBER, COLLABORATOR, or NONE
    created: str
    edited: bool            # a person with write access can edit the comment of another person
    hidden: bool            # a person minimized the comment
    body: str


def available(root: Path) -> bool:
    """True when origin is a GitHub repository. Then the board must work."""
    return bool(repo.origin(root))


def _answered(root: Path, done: subprocess.CompletedProcess, action: str) -> bool:
    """True when gh did the action. When the board must work, a failure stops the command."""
    if done.returncode == 0:
        return True
    if available(root):
        detail = (done.stderr or done.stdout).strip().splitlines()
        raise BoardError(f"Akasha cannot {action} the shared task board"
                         + (f" ({detail[0][:200]})" if detail else "")
                         + ". Make sure that gh is installed and logged in: gh auth status")
    return False


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


def _issue_task(item: dict) -> Task | None:
    """The task in one issue that gh gave as JSON, with the issue address."""
    task = parse(item.get("body", ""))
    if task is not None:
        task.board = item.get("url", "")
    return task


def _listed(root: Path, *search: str, state: str = "open") -> list[Task] | None:
    """The tasks in the issues with the label akasha, or None without GitHub."""
    listed = gh(root, "issue", "list", "--label", LABEL, "--state", state, "--limit", "500", *search,
                "--json", "body,url")
    if not _answered(root, listed, "read"):
        return None
    return [task for item in json.loads(listed.stdout or "[]") if (task := _issue_task(item)) is not None]


def read(root: Path) -> tuple[list[Task], str]:
    """The tasks on the board and where Akasha read them: "github" or "local".

    An issue stays open until the pull request of its task merges, so the board also shows the tasks that wait
    for a merge. Without GitHub, the board holds the active tasks on this computer."""
    local = [task for task in all_tasks(root) if active(task)]
    remote = _listed(root)
    if remote is None:
        return local, "local"
    known = {task.id for task in remote}
    return remote + [task for task in local if task.id not in known], "github"


def _known_address(root: Path, task_id: str) -> str:
    """The issue address in the task file on this computer, or ""."""
    try:
        return load(root, task_id).board
    except (LookupError, ValueError, TypeError, UnicodeDecodeError):
        return ""


def find(root: Path, task_id: str) -> Task | None:
    """The task with this id on the board, also when its issue is closed.

    When the task file on this computer knows the issue, Akasha reads that issue. Else Akasha searches the issue
    bodies for the id and takes only the issue with exactly this id."""
    address = _known_address(root, task_id)
    if address:
        viewed = gh(root, "issue", "view", address, "--json", "body,url")
        if viewed.returncode == 0:
            task = _issue_task(json.loads(viewed.stdout or "{}"))
            if task is not None and task.id == task_id:
                return task
    found = _listed(root, "--search", f"{task_id} in:body", state="all")
    return next((task for task in found or [] if task.id == task_id), None)


def comments(root: Path, address: str) -> list[Comment]:
    """The comments on the issue of a task, the oldest first."""
    viewed = gh(root, "issue", "view", address, "--json", "comments")
    if not _answered(root, viewed, "read"):
        return []
    found = []
    for item in json.loads(viewed.stdout or "{}").get("comments") or []:
        number = _COMMENT_NUMBER.search(item.get("url") or "")
        found.append(Comment(int(number.group(1)) if number else 0, (item.get("author") or {}).get("login") or "",
                             item.get("authorAssociation") or "", item.get("createdAt") or "",
                             bool(item.get("includesCreatedEdit")), bool(item.get("isMinimized")),
                             item.get("body") or ""))
    return found


def comment(root: Path, address: str, text: str) -> bool:
    """Write on the issue of a task. GitHub tells the people who follow the issue. True when the comment is on it."""
    return _answered(root, gh(root, "issue", "comment", address, "--body", text), "write")


def publish(root: Path, task: Task) -> str:
    """Put the task on the shared board, or update its issue. Return the issue address, or "" without GitHub.

    The issue stays open until the pull request merges. Akasha closes it when the task is done or cancelled."""
    title = f"[akasha] {task.title}"
    if task.board:
        _answered(root, gh(root, "issue", "edit", task.board, "--title", title, "--body", body(task)), "write")
        if task.status in ("done", "cancelled"):
            _answered(root, gh(root, "issue", "close", task.board), "write")
        return task.board
    gh(root, "label", "create", LABEL, "--color", "6d28d9", "--description", "Akasha task", "--force")
    made = gh(root, "issue", "create", "--label", LABEL, "--title", title, "--body", body(task))
    if not _answered(root, made, "write") or not made.stdout.strip():
        return ""
    task.board = made.stdout.strip().splitlines()[-1]
    return task.board
