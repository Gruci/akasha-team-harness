"""A task without a screen: a change of data, a batch job, an API, a rule, the speed, or the docs, where a preview of a
screen shows nothing. Only an administrator makes one, and approves its plan in place of a preview.

Akasha decides it from the files. `[preview] screens` of akasha.toml names the files that make a screen. A task
without a screen (`akasha start --no-screen`) plans none of them, and its change touches none (the check `screen`).

The order: the research, the plan, the review of the akasha-reviewer agent, then the approval of the plan by the
person, then the build. The approval holds the digest of plan.md: a later change of the plan needs the review and the
approval again.

A teammate approves a preview, as before. The server check examines the same rule on GitHub for each pull request
whose records hold a plan without a preview, a request, or impact.md, and the watch reports such a task of a person
who is not an administrator."""

from __future__ import annotations

from pathlib import Path

from akasha.checks import matches
from akasha.config import Team
from akasha.task import PLAN, PREVIEW, Task, folders_of, outside, record_folders

KIND = "no-screen"
CHECK = "screen"
OTHER_RECORDS = (PREVIEW, "request.md", "impact.md")    # the records of a full, an agent, and a quick task


def is_no_screen(task: Task) -> bool:
    return task.kind == KIND


def allowed(team: Team, me: str) -> bool:
    """True when this person can make a task without a screen: an administrator."""
    return bool(me) and me in team.admins


def _screens(team: Team, items: list[str], files: list[str]) -> list[str]:
    """The patterns of `items` that can hold a file that makes a screen."""
    found = []
    for item in items:
        if any(matches(item, screen) or matches(screen, item) for screen in team.screen_paths) or \
                any(matches(path, item) and any(matches(path, screen) for screen in team.screen_paths)
                    for path in files):
            found.append(item)
    return found


def start_problem(team: Team, me: str, scope: list[str], files: list[str]) -> str:
    """Why this person cannot start a task without a screen with this scope, or "". `files` are the files of the
    repository, to find a screen file that a pattern of the scope holds."""
    if not allowed(team, me):
        return "only an administrator starts a task without a screen: start it without --no-screen, with a preview"
    if not team.screen_paths:
        return ("akasha.toml names no files that make a screen. An administrator lists them in [preview] screens "
                "first, so that Akasha can examine that the task has no screen")
    if not scope:
        return "give the files of the task with --scope: Akasha examines that none of them makes a screen"
    found = _screens(team, scope, files)
    if found:
        return (f"the scope {', '.join(found[:3])} holds files that make a screen ([preview] screens). Start the task "
                "without --no-screen, with a preview")
    return ""


def problems(team: Team, changed: list[str], own: tuple[str, ...]) -> list[str]:
    """Why the change is not a change without a screen, or []. `own`: the records folders of the task."""
    if not team.screen_paths:
        return ["akasha.toml names no files that make a screen ([preview] screens)"]
    return [f"{path}: it makes a screen" for path in changed
            if outside(path, own) and any(matches(path, screen) for screen in team.screen_paths)]


def marked(team: Team, changed: list[str], root: Path | None = None) -> list[str]:
    """The tasks that a pull request marks as without a screen: their records in the changed files hold plan.md, and
    no preview, request, or impact.md. With `root`, the records folder in the work copy must hold none of them either:
    a pull request that only edits the plan of an earlier full task does not mark it. The records are in [work]
    records before the landing and in the archive after it (task.placed)."""
    return sorted({task for folder, (task, names) in record_folders(team, changed).items()
                   if PLAN in names and not names & set(OTHER_RECORDS)
                   and not (root and any((root / folder / name).is_file() for name in OTHER_RECORDS))})


def server(team: Team, changed: list[str], root: Path | None = None) -> tuple[str, str] | None:
    """The screen check of the server: None when the team names no screen files (it makes no task without a screen:
    start_problem refuses one) or the pull request marks no task without a screen, else PASS or FAIL and why. The
    watch still reports a merged task without a screen of the wrong kind from its block."""
    if not team.screen_paths:
        return None
    tasks = marked(team, changed, root)
    if not tasks:
        return None
    found = problems(team, changed, folders_of(team, changed, tasks))
    if found:
        return "FAIL", (f"task {', '.join(tasks)} has a plan without a preview, so it must have no screen: "
                        + "; ".join(found[:10]))
    return "PASS", ""
