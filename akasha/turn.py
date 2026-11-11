"""The order of the landings: the task that came to the landing first merges first.

Each landing that is behind the default branch comes up to date and runs its checks again. When each of n landings
does it at each merge, the checks run up to n(n+1)/2 times, and a short pull request pushes a long check back again
and again. So only the first task of the line comes up to date and merges; the others wait.

The line is the open pull requests that are no draft and whose task is in its landing, in the order of (the time
that the landing wrote, the number of the pull request). No file and no server holds it: each computer reads the
pull requests and counts in the same way. It is no lock. When two computers see different things for a moment, both
come up to date, as before.

A task that cannot go on does not hold the line. The computer that waits behind it passes that try of the landing:
a comment on the pull request names the try (`attempt`), so each computer reads the same answer, and a late comment
about an older try means nothing for a new one. The landing that comes back reads its pull request first, and goes to
the end of the line with a new try."""

from __future__ import annotations

import re
import secrets
import time
from pathlib import Path
from typing import Callable

from akasha import repo
from akasha.config import LABEL
from akasha.task import Task, parse_block

SKIPPED_LABEL = "akasha-skipped"           # for people on the board. The comment decides, not the label
STALL_SECONDS = 180                        # a first value: it does not prove why the first task stopped
_MARK = "<!-- akasha:skipped {attempt} -->"
_SKIPPED = re.compile(r"<!-- akasha:skipped ([\w-]+) -->")
LIST = "number,isDraft,body"
DETAIL = ("number,state,isDraft,body,comments,mergeStateStatus,statusCheckRollup,reviewDecision,headRefOid,"
          "baseRefName,url,autoMergeRequest")
# What the landing gives for a pull request: the state of each required check, and how far it is behind (-1: no
# answer)
Judge = Callable[[dict], tuple[dict[str, str], int]]


def enter(task: Task) -> None:
    """A new try of the landing: the task goes to the end of the line."""
    task.checks["landed_at"] = time.time()
    task.checks["attempt"] = secrets.token_hex(4)


def skipped(view: dict, attempt: str) -> bool:
    """True when a comment of the pull request passed this try."""
    return any(attempt in _SKIPPED.findall(str(comment.get("body") or "")) for comment in view.get("comments") or [])


def _place(task: Task, number: int) -> tuple[float, int]:
    try:
        return float(task.checks.get("landed_at") or 0), number
    except (TypeError, ValueError):
        return 0.0, number


def line(root: Path) -> list[tuple[int, Task]] | None:
    """The landings in their order, or None when GitHub does not answer. It reads each open pull request now, and
    not the copy of the board."""
    items = repo.gh_json(root, "pr", "list", "--label", LABEL, "--state", "open", "--limit", "1000", "--json", LIST)
    if not isinstance(items, list):
        return None
    found = []
    for item in items:
        task, number = parse_block(str(item.get("body") or "")), int(item.get("number") or 0)
        if task and number and not item.get("isDraft") and task.status == "landing":
            found.append((number, task))
    return sorted(found, key=lambda entry: _place(entry[1], entry[0]))


def rejoin(task: Task, view: dict) -> bool:
    """Read the own pull request before the landing changes anything. True when the task changed.

    Another call of the landing put the task into the line again: this computer takes that try, and does not write
    its old one over it. The try of this computer was passed: a new try, at the end of the line."""
    mine = str(task.checks.get("attempt") or "")
    remote = parse_block(str(view.get("body") or ""))
    theirs = str(remote.checks.get("attempt") or "") if remote else ""
    if theirs and theirs != mine and not task.checks.get("unwritten"):
        task.checks["attempt"], task.checks["landed_at"] = theirs, remote.checks.get("landed_at")
        return True
    if mine and skipped(view, mine):
        enter(task)
        task.checks["unwritten"] = True
        return True
    return False


def _stopped(other: Task, number: int, view: dict, judge: Judge, clock: dict) -> str:
    """Why the first task of the line does not go on, or "". `clock` holds since when this computer saw it first in
    the line without a step."""
    if view.get("mergeStateStatus") == "DIRTY":
        return "it conflicts with the default branch"
    states, behind = judge(view)
    if any(value == "FAIL" for value in states.values()):
        return "a required check failed"
    if view.get("reviewDecision") == "REVIEW_REQUIRED":
        return "it waits for a review"
    passed = bool(states) and all(value == "PASS" for value in states.values())
    if other.kind == "agent" and other.approval.get("source") != "result" and passed and behind == 0:
        return "it waits for the person who approves its result"
    if behind < 0:
        return ""                                     # no answer is no proof that it stopped
    still = behind > 0 or (passed and view.get("mergeStateStatus") != "UNKNOWN")
    if not still:                                     # its checks run: it goes on
        clock.clear()
        return ""
    key = (number, str(other.checks.get("attempt") or ""), str(view.get("headRefOid") or ""), behind)
    if clock.get("key") != key:
        clock.update(key=key, since=time.monotonic())
        return ""
    if time.monotonic() - clock["since"] >= STALL_SECONDS:
        return ("it did not come up to date after its turn came" if behind > 0 else
                "its checks passed, and nothing merged it after its turn came")
    return ""


def _pass(root: Path, number: int, attempt: str, reason: str) -> bool:
    """Pass one try of a landing, so that each computer reads it. True when GitHub shows the comment and no
    auto-merge."""
    me = repo.me(root) or "someone"
    repo.gh(root, "pr", "comment", str(number), "--body",
            _MARK.format(attempt=attempt) + f"\nThe line of the landings went on without this pull request (@{me} "
            f"waited behind it): {reason}. `akasha land` of this task puts it at the end of the line again.")
    repo.gh(root, "pr", "merge", str(number), "--disable-auto")
    repo.gh(root, "label", "create", SKIPPED_LABEL, "--color", "9ca3af", "--description",
            "The line of the landings of Akasha went on without this pull request")
    repo.gh(root, "pr", "edit", str(number), "--add-label", SKIPPED_LABEL)
    view = repo.gh_json(root, "pr", "view", str(number), "--json", DETAIL)
    return isinstance(view, dict) and skipped(view, attempt) and not view.get("autoMergeRequest")


def back(root: Path, task: Task) -> None:
    """The task is in the line again: the label for people leaves."""
    repo.gh(root, "pr", "edit", str(task.number), "--remove-label", SKIPPED_LABEL)


def before(root: Path, task: Task, judge: Judge, clock: dict) -> str | None:
    """What this landing waits behind, or None when it is the first of the line. A text is a wait: the number of the
    pull request before it, or that GitHub did not answer."""
    found = line(root)
    if found is None:
        return "GitHub did not tell the line of the landings"
    mine = _place(task, task.number)
    for number, other in found:
        if number == task.number or _place(other, number) >= mine:
            continue
        view = repo.gh_json(root, "pr", "view", str(number), "--json", DETAIL)
        if not isinstance(view, dict):
            return f"GitHub did not tell the state of #{number}"
        other = parse_block(str(view.get("body") or "")) or other
        if view.get("state", "OPEN") != "OPEN" or view.get("isDraft") or other.status != "landing":
            continue
        attempt = str(other.checks.get("attempt") or "") or "-"
        if skipped(view, attempt):
            continue
        reason = _stopped(other, number, view, judge, clock)
        if not reason or not _pass(root, number, attempt, reason):
            return f"#{number}"
    return None
