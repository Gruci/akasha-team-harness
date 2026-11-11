"""A task: one change of one person, from the request to the merge.

The task lives in three places. Its branch and its draft pull request are on GitHub: the open pull requests with
the label akasha are the shared board. A block in the body of the pull request holds the state of the task for the
other computers. A file in .docs/state/tasks/ holds the state on this computer, with the work copy.

The records of a task (preview, research, plan, review, summary) are in one folder. While the task is in work, the
folder is <records>/<task>, and only the branch of the task has it. The landing moves it to the archive,
<archive>/YYYY/MM/YYYY-MM-DD-<task>, and the merge brings it into the default branch (archive.py). Akasha reads
the folder of one task only: never the archive of the other tasks."""

from __future__ import annotations

import hashlib
import json
import re
import secrets
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field, fields
from datetime import date
from pathlib import Path

from akasha.config import RECORDS_DIR, STATE_DIR, Team
from akasha.repo import write_whole

STATUSES = ("preview", "approved", "landing", "merged", "closed")
TASK_ID = re.compile(r"[a-z0-9][a-z0-9-]{0,59}")
# This computer and this session only: never on GitHub
LOCAL_ONLY = ("workcopy", "shown_in", "heard", "parts", "session", "active_at")
REVIEW_LOCAL = ("plan", "rows")     # the plan and the rows that the last review read: too long for the PR body
APPROVAL_LOCAL = ("words",)         # the words of the approval stay on this computer: GitHub names who and when
BLOCK = re.compile(r"<!-- akasha:task (\{.*?\}) -->", re.S)
# A folder of the archive: YYYY-MM-DD-<task>, or YYYY-MM-DD.<number>-<task> when that day already has the name.
# The number stands with the date, so that the name after the date is the task, also for a task "fix-2"
DATED = re.compile(r"\d{4}-\d{2}-\d{2}(?:\.\d+)?-(.+)")
DATE_FIRST = re.compile(r"\d{4}-\d{2}-\d{2}-")
PREVIEW, PLAN, RESEARCH, SUMMARY = "preview.html", "plan.md", "research.md", "summary.md"


@dataclass
class Task:
    id: str
    title: str
    kind: str = "full"              # "full", or "quick": a small change without a preview and a plan (quick.py)
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
    heard: dict = field(default_factory=dict)               # the last message of the person after it: words, at
    approval: dict = field(default_factory=dict)            # by, at, preview_sha, words, source
    review: dict = field(default_factory=dict)              # verdict, plan_sha, at, source, rounds
    checks: dict = field(default_factory=dict)              # status, tree, at
    failures: int = 0               # failed checks in a row
    stats: dict = field(default_factory=dict)               # for the retro: failed checks by name, review rounds
    records_dir: str = RECORDS_DIR  # the folder that holds the records of the task: [work] records, and [work]
    #                                 archive after the landing moved them
    records_name: str = ""          # the folder of this task in it: the task id, and YYYY/MM/YYYY-MM-DD-<task>
    #                                 in the archive
    workcopy: str = ""
    # The parts of the work for workers at the same time (`akasha split`): name, branch, scope, workcopy. Each part
    # is a work copy on this computer only, on a local branch from the branch of the task; `akasha join` merges it
    parts: list[dict] = field(default_factory=list)
    defs: dict = field(default_factory=dict)                # the keys of the definitions that the task adds, changes
    session: str = ""               # the session of the agent engine that works on the task on this computer
    active_at: float = 0.0          # when that session last edited the work copy or named the task in a command


def new_id(title: str, name: str = "") -> str:
    """The name of a task: the name that the person gave, or a short name from the title with a random end."""
    if name:
        name = name.strip().lower()
        if not TASK_ID.fullmatch(name):
            raise ValueError(f"the task name {name!r} can have only a to z, 0 to 9, and -, up to 60 characters")
        if DATE_FIRST.match(name):
            raise ValueError(f"the task name {name!r} cannot start with a date: the archive puts the date of the "
                             "landing before the name")
        return name
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:40].strip("-")
    if DATE_FIRST.match(slug):
        slug = f"task-{slug}"[:40].strip("-")
    return f"{slug}-{secrets.token_hex(2)}" if slug else f"task-{secrets.token_hex(4)}"


def archive_name(task_id: str, day: date | None = None, number: int = 0) -> str:
    """The folder of a task in the archive, below [work] archive: YYYY/MM/YYYY-MM-DD-<task>. The date is the day of
    the first move. One folder for each month, so that no folder grows without end. With `number`, the name for a
    day that already has the same task name: YYYY-MM-DD.<number>-<task>."""
    day = day or date.today()
    mark = f".{number}" if number else ""
    return f"{day:%Y}/{day:%m}/{day.isoformat()}{mark}-{task_id}"


def task_of(folder: str) -> str:
    """The task id of a folder of the archive: the name without the date at the start. Only the archive has dated
    folders: in [work] records the name of the folder is the task id as it is."""
    found = DATED.fullmatch(folder)
    return found.group(1) if found else folder


def placed(team: Team, path: str) -> tuple[str, str, str] | None:
    """The records folder, the task id, and the file name of a path that is a record file of a task, else None:
    <records>/<task>/<file> of a task in work, or <archive>/YYYY/MM/<dated folder>/<file> of a landed task."""
    for top, depth in ((team.records_dir, 1), (team.archive_dir, 3)):
        top = top.rstrip("/") + "/"
        parts = path[len(top):].split("/") if path.startswith(top) else []
        if len(parts) == depth + 1 and all(parts):
            folder = top + "/".join(parts[:depth])
            return folder, (task_of(parts[depth - 1]) if depth == 3 else parts[0]), parts[depth]
    return None


def record_folders(team: Team, changed: Iterable[str]) -> dict[str, tuple[str, set[str]]]:
    """The records folders that the changed files touch: folder -> the task id and the names of its changed files.
    It comes from the changed paths alone. Nothing lists the archive."""
    found: dict[str, tuple[str, set[str]]] = {}
    for path in changed:
        at = placed(team, path)
        if at:
            found.setdefault(at[0], (at[1], set()))[1].add(at[2])
    return found


def folders_of(team: Team, changed: Iterable[str], tasks: Iterable[str]) -> tuple[str, ...]:
    """The records folders of these tasks in the changed files: of a task in work, of a landed task, or both."""
    tasks = set(tasks)
    return tuple(sorted(folder for folder, (task, _names) in record_folders(team, changed).items() if task in tasks))


def each(folders: Iterable[str] | str) -> tuple[str, ...]:
    """The folders as a tuple: one folder can come as plain text."""
    return (folders,) if isinstance(folders, str) else tuple(folders)


def outside(path: str, folders: Iterable[str] | str) -> bool:
    """True when the path is in none of the folders."""
    folders = each(folders)
    return not any((path + "/").startswith(folder.rstrip("/") + "/") for folder in folders)


def records(task: Task) -> str:
    """The folder of the records of the task in the repository: preview, research, plan, and summary. A task that
    started before records_name existed has the folder of its id."""
    return f"{task.records_dir}/{task.records_name or task.id}"


def own_records(task: Task) -> tuple[str, ...]:
    """The folders that hold the records of this task, and of no other task. A change in them is no change of the
    product. The records of another task are not among them: a change of the archive of another task counts as a
    change of the product."""
    return (records(task),)


def record(task: Task, name: str) -> Path:
    """A record file of the task in its work copy."""
    return Path(task.workcopy) / records(task) / name


def digest_of(data: bytes) -> str:
    """The first 12 characters of the SHA-256 of the bytes of a file. The line ends do not count."""
    return hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()[:12]


def digest(path: Path) -> str:
    """The first 12 characters of the SHA-256 of a file, or "" when the file is not there. The line ends do not
    count: git can check out the same file with CRLF on one computer and LF on another (core.autocrlf), and an
    approval on one computer must stay valid on the next."""
    try:
        return digest_of(path.read_bytes())
    except OSError:
        return ""


def _folder(root: Path) -> Path:
    return root / STATE_DIR / "tasks"


def replaced(root: Path, task: Task) -> bool:
    """True when the state of this computer under the name of the task belongs to a later task of the same name:
    its pull request has another number. A merged task gives its name free, so the end of an old landing must not
    write over, or remove, the task that took the name."""
    path = _folder(root) / f"{task.id}.json"
    try:
        kept = int(json.loads(path.read_text(encoding="utf-8")).get("number") or 0)
    except (OSError, ValueError, TypeError, AttributeError):
        return False
    return bool(kept and task.number and kept != task.number)


def save(root: Path, task: Task) -> None:
    if task.status not in STATUSES:
        raise ValueError(f"unknown task status {task.status}")
    if replaced(root, task):
        raise RuntimeError(f"task {task.id} of pull request #{task.number} ended, and a new task has its name now: "
                           "Akasha does not write over the new task")
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


def forget(root: Path, task_id: str, number: int = 0) -> None:
    """Remove the state of the task on this computer. With `number`, only the state of that pull request."""
    path = _folder(root) / f"{task_id}.json"
    if number:
        try:
            kept = int(json.loads(path.read_text(encoding="utf-8")).get("number") or 0)
        except (OSError, ValueError, TypeError, AttributeError):
            kept = 0
        if kept and kept != number:
            return
    path.unlink(missing_ok=True)


def block(task: Task) -> str:
    """The hidden block of the task in the body of its pull request."""
    data = {key: value for key, value in asdict(task).items() if key not in LOCAL_ONLY}
    data["review"] = {key: value for key, value in data["review"].items() if key not in REVIEW_LOCAL}
    data["approval"] = {key: value for key, value in data["approval"].items() if key not in APPROVAL_LOCAL}
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
