"""The checks of the product itself: does the change work as approved, is it in its place, can it go live, and is
it small enough to undo.

`akasha check` on a computer and the server check run the same functions, in the same order. Each one looks only at
what the change makes new, so a team can turn a rule on in a repository that has old code. A check gives its status
(PASS, FAIL, or NOT_NEEDED), what to do, and its notes. The notes are advice, and never stop a task.

| Check | The question | The module |
| proof | Has each rule and each value that the person approved a test? | proof.py |
| scope | Does the change stay inside the steps of its plan? | steps.py |
| map | Is the new code in its area, and does the map of the product still hold? | sheets.py |
| ops | Can the change go live, and stay visible there? | ops.py |
| size | Is each function, each file, and the task small enough? | size.py |"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from akasha import ops, proof, sheets, size, steps
from akasha.config import Team

Answer = tuple[str, str, list[str]]
INTEGRATION = "integration"        # the check that a change of data ran against a real store


@dataclass
class Change:
    """One change, as each check needs it."""
    team: Team
    tree: Path                         # the work copy, or the checkout of the server
    base: str                          # the commit before the change
    changed: list[str]                 # the files that the change touches
    maps: object                       # codemap.Pair: the code now and before
    admin: bool = False                # the change is of an administrator
    plan: str | None = None            # the text of plan.md, or None for a task without a plan
    preview: str | None = None         # the text of preview.html, or None for a task without a preview
    own: tuple[str, ...] = ()          # the folders of the records of the task


def checks(change: Change) -> dict[str, Callable[[], Answer]]:
    """The checks by name, in the order of their weight."""
    skip = change.team.record_roots + (change.team.work_dir,)
    rules = proof.keys(change.preview)[0] if change.preview is not None else []
    return {
        proof.CHECK: lambda: proof.examine(change.tree, change.preview, skip),
        steps.CHECK: lambda: steps.examine(change.plan, rules, change.tree, change.changed, change.own),
        sheets.CHECK: lambda: sheets.examine(change.team, change.tree, change.base, change.changed, change.maps,
                                             change.admin),
        ops.CHECK: lambda: ops.examine(change.team, change.tree, change.base, change.changed),
        size.CHECK: lambda: size.examine(change.team, change.tree, change.base, change.changed, change.own,
                                         change.admin),
    }


def run(change: Change, only: tuple[str, ...] = ()) -> tuple[dict[str, str], dict[str, str], list[str]]:
    """Run them: the status of each, what to do for each, and the notes of all. A check that the change does not
    need is not in the answer: the list of a task names only what was examined."""
    status, details, notes = {}, {}, []
    for name, examine in checks(change).items():
        if only and name not in only:
            continue
        try:
            said, why, found = examine()
        except (RuntimeError, OSError) as error:
            said, why, found = "FAIL", f"Akasha could not examine the change: {error}", []
        notes += found
        if said != "NOT_NEEDED" or only:
            status[name], details[name] = said, why
    return status, details, notes


def integration(team: Team, changed: list[str], status: dict[str, str]) -> tuple[str, str]:
    """The check `integration`: a change of files that make data ran a check against a real store. (status, what to
    do). A team without such a check has NOT_NEEDED: `akasha doctor` tells its administrator."""
    from akasha.checks import touches
    real = [name for name in team.required_checks if name in team.checks and team.checks[name].kind == "integration"]
    touched = touches(changed, team.data_paths)
    if not real or not touched:
        return "NOT_NEEDED", ""
    if any(status.get(name) == "PASS" for name in real):
        return "PASS", ""
    return "FAIL", (f"the change touches {', '.join(touched[:5])}, which make data, and no check against a real store "
                    f"ran ({', '.join(real)}). Its only_when must name these files: a query that never ran is not "
                    "proven")
