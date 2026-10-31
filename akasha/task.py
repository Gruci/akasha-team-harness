"""A task: one change of one person, from the request to the merge.

The task lives in three places. Its branch and its draft pull request are on GitHub: the open pull requests with
the label akasha are the shared board. A block in the body of the pull request holds the state of the task for the
other computers. A file in .akasha/state/tasks/ holds the state on this computer, with the work copy."""

from __future__ import annotations

import hashlib
import json
import re
import secrets
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from akasha.config import RECORDS_DIR, STATE_DIR
from akasha.repo import write_whole

STATUSES = ("preview", "approved", "landing", "merged", "closed")
TASK_ID = re.compile(r"[a-z0-9][a-z0-9-]{0,59}")
LOCAL_ONLY = ("workcopy", "shown_in")           # this computer and this session only. They never go on GitHub
BLOCK = re.compile(r"<!-- akasha:task (\{.*?\}) -->", re.S)
PREVIEW, PLAN, RESEARCH, SUMMARY = "preview.html", "plan.md", "research.md", "summary.md"


@dataclass
class Task:
    id: str
    title: str
    branch: str = ""
    base: str = ""                  # the commit of the default branch where the work copy started
    scope: list[str] = field(default_factory=list)          # file patterns that the task plans to change
    owner: str = ""                 # the GitHub name of the person who holds the task now
    status: str = "preview"
    pr: str = ""                    # the address of the pull request
    number: int = 0
    preview_sha: str = ""           # the preview as `akasha preview` showed it
    shown_at: float = 0.0
    shown_in: str = ""              # the session of the agent engine that showed it: only that session approves
    approval: dict = field(default_factory=dict)            # by, at, preview_sha, words, source
    review: dict = field(default_factory=dict)              # verdict, plan_sha, at, source, rounds
    checks: dict = field(default_factory=dict)              # status, tree, at
    failures: int = 0               # failed checks in a row
    stats: dict = field(default_factory=dict)               # for the retro: failed checks by name, review rounds
    records_dir: str = RECORDS_DIR  # the folder of the records of the tasks, as [work] records was at the start
    workcopy: str = ""


def new_id(title: str, name: str = "") -> str:
    """The name of a task: the name that the person gave, or a short name from the title with a random end."""
    if name:
        name = name.strip().lower()
        if not TASK_ID.fullmatch(name):
            raise ValueError(f"the task name {name!r} can have only a to z, 0 to 9, and -, up to 60 characters")
        return name
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:40].strip("-")
    return f"{slug}-{secrets.token_hex(2)}" if slug else f"task-{secrets.token_hex(4)}"


def records(task: Task) -> str:
    """The folder of the records of the task in the repository: preview, research, plan, and summary."""
    return f"{task.records_dir}/{task.id}"


def record(task: Task, name: str) -> Path:
    """A record file of the task in its work copy."""
    return Path(task.workcopy) / records(task) / name


def digest(path: Path) -> str:
    """The first 12 characters of the SHA-256 of a file, or "" when the file is not there. The line ends do not
    count: git can check out the same file with CRLF on one computer and LF on another (core.autocrlf), and an
    approval on one computer must stay valid on the next."""
    try:
        return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()[:12]
    except OSError:
        return ""


def _folder(root: Path) -> Path:
    return root / STATE_DIR / "tasks"


def save(root: Path, task: Task) -> None:
    if task.status not in STATUSES:
        raise ValueError(f"unknown task status {task.status}")
    folder = _folder(root)
    folder.mkdir(parents=True, exist_ok=True)
    write_whole(folder / f"{task.id}.json", json.dumps(asdict(task), indent=2, ensure_ascii=False) + "\n")


def _from(data: dict) -> Task:
    known = {item.name for item in fields(Task)}
    return Task(**{key: value for key, value in data.items() if key in known})


def load(root: Path, task_id: str) -> Task:
    path = _folder(root) / f"{task_id}.json"
    if not path.is_file():
        raise LookupError(f"no task {task_id} on this computer. `akasha board` shows the tasks of the team, and "
                          f"`akasha resume {task_id}` continues a task of the board here")
    return _from(json.loads(path.read_text(encoding="utf-8")))


def all_local(root: Path) -> list[Task]:
    """The tasks on this computer. A damaged file does not stop the others."""
    found = []
    for path in sorted(_folder(root).glob("*.json")):
        try:
            found.append(_from(json.loads(path.read_text(encoding="utf-8"))))
        except (ValueError, TypeError, OSError):
            continue
    return found


def forget(root: Path, task_id: str) -> None:
    (_folder(root) / f"{task_id}.json").unlink(missing_ok=True)


def block(task: Task) -> str:
    """The hidden block of the task in the body of its pull request."""
    data = {key: value for key, value in asdict(task).items() if key not in LOCAL_ONLY}
    text = json.dumps(data, ensure_ascii=False).replace("-->", "--\\u003e")     # the comment must not end early
    return f"<!-- akasha:task {text} -->"


def parse_block(text: str) -> Task | None:
    found = BLOCK.search(text or "")
    if not found:
        return None
    try:
        return _from(json.loads(found.group(1)))
    except (ValueError, TypeError):
        return None
