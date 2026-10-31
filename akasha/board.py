"""The shared board: the open pull requests with the label akasha. Each one is the task of one person.

GitHub already knows the branch, the author, the person who holds the task (the assignee), and the changed files of
each pull request, so the board needs no other store. The hooks read a copy of the board that is at most five
minutes old, so that the hook after each edit stays fast."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from akasha.checks import matches
from akasha.config import LABEL, STATE_DIR
from akasha.repo import gh, origin, write_whole
from akasha.task import Task, parse_block

FIELDS = "number,title,url,headRefName,isDraft,author,assignees,body,files"
CACHE = STATE_DIR / "board.json"
CACHE_AGE = 300                  # seconds
QUIET_AFTER_FAILURE = 60         # after gh did not answer, the hooks do not ask again for this long


@dataclass
class Entry:
    task: Task
    number: int
    url: str
    draft: bool
    author: str
    branch: str = ""
    assignees: list[str] = field(default_factory=list)
    files: list[str] = field(default_factory=list)

    @property
    def holder(self) -> str:
        """The person who holds the task: the assignee. "" when the task is free after a handoff."""
        return self.assignees[0] if self.assignees else ""

    @property
    def person(self) -> str:
        """The person to name in a notice: the holder, else the author."""
        return self.holder or self.author


def available(root: Path) -> bool:
    return bool(origin(root))


def _entries(items: list) -> list[Entry]:
    found = []
    for item in items if isinstance(items, list) else []:
        task = parse_block(item.get("body") or "") or Task(id=str(item.get("headRefName") or item.get("number")),
                                                           title=str(item.get("title") or ""))
        found.append(Entry(task=task, number=int(item.get("number") or 0), url=str(item.get("url") or ""),
                           draft=bool(item.get("isDraft")),
                           author=str((item.get("author") or {}).get("login") or "").lower(),
                           branch=str(item.get("headRefName") or ""),
                           assignees=[str(person.get("login") or "").lower() for person in item.get("assignees") or []],
                           files=[str(entry.get("path") or "") for entry in item.get("files") or []]))
    return found


def read(root: Path, timeout: float = 60) -> list[Entry] | None:
    """The open tasks of the team, or None when gh does not answer."""
    done = gh(root, "pr", "list", "--label", LABEL, "--state", "open", "--limit", "200", "--json", FIELDS,
              timeout=timeout)
    if done.returncode:
        return None
    try:
        items = json.loads(done.stdout or "[]")
    except ValueError:
        return None
    path = root / CACHE
    path.parent.mkdir(parents=True, exist_ok=True)
    write_whole(path, json.dumps({"at": time.time(), "items": items}, ensure_ascii=False))
    return _entries(items)


def cached(root: Path, timeout: float = 5) -> list[Entry] | None:
    """The copy of the board for the hooks. None when gh does not answer: the hooks then give no notice."""
    path = root / CACHE
    try:
        known = json.loads(path.read_text(encoding="utf-8"))
        age = time.time() - float(known["at"])
        if age < CACHE_AGE and known.get("items") is not None:
            return _entries(known["items"])
        if known.get("items") is None and age < QUIET_AFTER_FAILURE:
            return None
    except (OSError, ValueError, KeyError, TypeError):
        pass
    found = read(root, timeout=timeout)
    if found is None:
        path.parent.mkdir(parents=True, exist_ok=True)
        write_whole(path, json.dumps({"at": time.time(), "items": None}))
    return found


def forget(root: Path) -> None:
    (root / CACHE).unlink(missing_ok=True)


def _fixed(pattern: str) -> str:
    cut = min((pattern.find(mark) for mark in "*?[" if mark in pattern), default=len(pattern))
    return pattern[:cut]


def touches(first: list[str], second: list[str]) -> list[str]:
    """Pairs of patterns that can match the same file. When in doubt, a touch."""
    return [f"{left} / {right}" for left in first for right in second
            if _fixed(left).startswith(_fixed(right)) or _fixed(right).startswith(_fixed(left))]


def overlaps(task: Task, changed: list[str], entries: list[Entry]) -> list[str]:
    """One line for each other open task that plans or changes the same files."""
    lines = []
    for entry in entries:
        other = entry.task
        if other.id == task.id or (task.number and entry.number == task.number):
            continue
        hits = touches(task.scope, other.scope)
        hits += [path for path in changed if path in entry.files or any(matches(path, item) for item in other.scope)]
        if hits:
            lines.append(f"#{entry.number} {other.title} (@{entry.person}): {', '.join(dict.fromkeys(hits))[:300]}")
    return lines


def lines(entries: list[Entry], me: str) -> list[str]:
    """The board for a person: each open task with its holder, its step, and its planned files."""
    found = []
    for entry in sorted(entries, key=lambda item: item.number):
        step = "draft" if entry.draft else "landing"
        who = f"@{entry.holder}" + (" (you)" if entry.holder == me else "") if entry.holder else "free"
        scope = f" — {', '.join(entry.task.scope[:4])}" if entry.task.scope else ""
        found.append(f"#{entry.number} {entry.task.id}: {entry.task.title} · {who} · {step}{scope}")
    return found
