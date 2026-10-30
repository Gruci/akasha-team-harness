"""Task state. With GitHub, the issue of each task holds its state, so that each computer can continue it. Each
computer also keeps one JSON file for each task in .akasha/state/tasks/.

With GitHub, the approvals and the inspection results are not proof of a decision: Akasha makes them again from the
decision comments on the issue each time that it reads the task."""

from __future__ import annotations

import json
import os
import re
import secrets
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from akasha.config import STATE_DIR

STATUSES = ("open", "stopped", "done", "cancelled")
FORMAT = 2                  # the issue holds the whole task. Akasha 1.0.0 wrote only some fields: format 1
# The fields that stay on one computer. The issue never holds them.
LOCAL_FIELDS = ("workcopy", "synced", "setup_output")


@dataclass
class Task:
    id: str
    title: str
    workflow: str
    stage: str
    status: str = "open"
    requester: str = ""
    feature: str = ""                                          # the feature key, for the map file and overlaps
    scope: list[str] = field(default_factory=list)             # file patterns that the task can change
    contracts: list[str] = field(default_factory=list)         # public contracts that the task changes
    conditions: list[str] = field(default_factory=list)        # the completion conditions
    open_questions: list[str] = field(default_factory=list)
    risk: str = "low"
    risk_reasons: list[str] = field(default_factory=list)
    approvals: dict[str, str] = field(default_factory=dict)    # role -> the person who approved
    accepted: dict[str, bool] = field(default_factory=dict)    # condition -> result of the inspection
    checks: dict[str, str] = field(default_factory=dict)       # check -> PASS, FAIL, or SKIP
    impact: dict[str, str] = field(default_factory=dict)       # the impact analysis of the agent engine
    map_note: str = ""                                         # why the map file of the feature does not change
    briefing: str = ""                                         # the pull request briefing, without Verification
    builds_on: str = ""                                        # the earlier task that this task builds on
    failures: int = 0
    base: str = ""
    branch: str = ""
    workcopy: str = ""
    board: str = ""                                            # the issue of the task on the shared task board
    pull_request: str = ""
    notes: list[str] = field(default_factory=list)
    holder: str = ""                                           # the GitHub name of the person who holds the task
    holder_host: str = ""                                      # the mark of the copy of the repository of the holder
    revision: int = 0                                          # one more at each write; the higher revision is newer
    wip: str = ""                                              # the commit that the last handoff pushed
    spec_rev: int = 0                                          # one more at each change of the conditions or questions
    stopped_comment: int = 0                                   # the comment of Akasha when the task stopped
    resumed: int = 0                                           # the last /resume comment that opened the task again
    format: int = FORMAT
    synced: int = 0                                            # the revision of the issue that this computer saw last
    setup_output: str = ""                                     # the output of a setup command that failed here


def active(task: Task) -> bool:
    """An active task holds its scope: it is open, or it is stopped and waits for a developer."""
    return task.status in ("open", "stopped")


def _folder(root: Path) -> Path:
    return root / STATE_DIR / "tasks"


def new_id(title: str) -> str:
    """A short name from the title, with eight random characters. The name is also a branch name and a folder name,
    so it keeps only a to z, 0 to 9, and hyphens: a title without these letters, for example in Korean, gives
    `task-<random>`. flow makes sure that no other task in the repository has the name."""
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:32].strip("-") or "task"
    return f"{slug}-{secrets.token_hex(4)}"


def exists(root: Path, task_id: str) -> bool:
    """True when this computer has a task file with this id."""
    return (_folder(root) / f"{task_id}.json").is_file()


def save(root: Path, task: Task) -> None:
    if task.status not in STATUSES:
        raise ValueError(f"unknown task status {task.status}")
    folder = _folder(root)
    folder.mkdir(parents=True, exist_ok=True)
    temporary = folder / f"{task.id}.json.tmp"         # a stop during the write must not leave half a file
    temporary.write_text(json.dumps(asdict(task), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(temporary, folder / f"{task.id}.json")


def load(root: Path, task_id: str) -> Task:
    path = _folder(root) / f"{task_id}.json"
    if not path.is_file():
        raise LookupError(f"no task {task_id}")
    data = json.loads(path.read_text(encoding="utf-8"))
    known = {item.name for item in fields(Task)}
    return Task(**{key: value for key, value in data.items() if key in known})


def all_tasks(root: Path) -> list[Task]:
    """All tasks on this computer. A task file that a person damaged does not stop the other tasks."""
    found = []
    for path in sorted(_folder(root).glob("*.json")):
        try:
            found.append(load(root, path.stem))
        except (ValueError, TypeError, UnicodeDecodeError):
            continue
    return found
