"""The steps of a plan: a work order that an AI without the conversation can build, and the check `scope`.

plan.md holds its work as steps. Each step is small enough for one go, and names what it touches:

    ### S2 The orders as CSV text
    - files: `src/orders/export.py`, `src/orders/api.py`
    - uses: `list_orders(filter)` in src/orders/queries.py:44
    - rules: csv-filter, csv-empty
    - tests: `tests/test_orders_export.py`
    - done when: the tests of this step pass

Akasha reads `files`, `tests`, and `rules`. The rest is for the AI that builds: what to call, and when the step is
done. A file is a path or a pattern, in backticks.

The check `scope` holds the plan and the change together:

- The plan has steps, and each step names its files.
- Each rule of the preview is in a step: nothing that the person approved is without a place in the work.
- Each file of code that the task changes is in a step. A test, a sheet of an area, and the records need none.

Nobody marks a step as done. Akasha sees it: a step is done when the change touches each of its files and each of
its tests is there. `akasha status --brief` names the next step, so a new session, or another AI, goes on at the
right place."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from akasha import core
from akasha.checks import matches
from akasha.config import pattern
from akasha.sheets import AREA_FILE, CODE
from akasha.task import outside

CHECK = "scope"
HEAD = re.compile(r"^#{2,4}[ \t]*(S\d+)\b[ \t:.\-—]*(.*)$", re.M)
FIELD = re.compile(r"^[ \t]*[-*][ \t]*(files|tests|rules)[ \t]*:[ \t]*(.*(?:\n(?![ \t]*[-*#]|[ \t]*$).*)*)",
                   re.I | re.M)
QUOTED = re.compile(r"`([^`\n]+)`")
SHOWN = 8


@dataclass
class Step:
    id: str
    title: str
    files: list[str] = field(default_factory=list)
    tests: list[str] = field(default_factory=list)
    rules: list[str] = field(default_factory=list)


def _paths(text: str) -> list[str]:
    """The paths of a field: each text in backticks, without a name after `::` and without a line number."""
    found = []
    for item in QUOTED.findall(text):
        item = item.split("::")[0].strip()
        item = re.sub(r":\d+$", "", item)
        if item and " " not in item and ("/" in item or "." in item or "*" in item):
            found.append(pattern(item))
    return list(dict.fromkeys(found))


def parse(plan: str) -> list[Step]:
    """The steps of a plan, in their order."""
    heads = list(HEAD.finditer(plan or ""))
    found = []
    for at, head in enumerate(heads):
        body = plan[head.end():heads[at + 1].start() if at + 1 < len(heads) else len(plan)]
        end = re.search(r"^#{1,6}[ \t]", body, re.M)
        body = body[:end.start()] if end else body
        step = Step(head.group(1).upper(), head.group(2).strip())
        for name, value in FIELD.findall(body):
            name = name.lower()
            if name == "rules":
                step.rules += [key for key in re.split(r"[,\s`]+", value) if re.fullmatch(r"[\w.\-]+", key)]
            else:
                getattr(step, name).extend(_paths(value))
        found.append(step)
    return found


def _planned(path: str, steps: list[Step]) -> bool:
    return any(matches(path, item) for step in steps for item in step.files + step.tests)


def _free(path: str, own: tuple[str, ...]) -> bool:
    """A file that needs no step: no code, a test, the sheet of an area, or a record of the task."""
    return not path.endswith(CODE) or bool(core.TEST.search(path)) or path.endswith("/" + AREA_FILE) \
        or not outside(path, own)


def progress(steps: list[Step], tree: Path, changed: list[str]) -> list[tuple[Step, bool]]:
    """Each step with whether it is done: the change touches each of its files, and each of its tests is there."""
    found = []
    for step in steps:
        touched = bool(step.files) and all(any(matches(path, item) for path in changed) for item in step.files)
        tested = all(any(matches(path, item) for path in changed) or (tree / item).is_file() for item in step.tests)
        found.append((step, touched and tested))
    return found


def line(steps: list[Step], tree: Path, changed: list[str]) -> str:
    """One line for `akasha status --brief`: how far the build is, and the next step. "" without steps."""
    seen = progress(steps, tree, changed)
    if not seen:
        return ""
    done = [step.id for step, ended in seen if ended]
    following = next((step for step, ended in seen if not ended), None)
    if following is None:
        return f"steps: each of the {len(seen)} steps is done"
    files = ", ".join(following.files[:4]) or "no file yet"
    return (f"steps: {len(done)} of {len(seen)} done · next {following.id} {following.title} ({files}): its part of "
            "plan.md tells what to call and when it is done")


def examine(plan: str | None, rules: list[str], tree: Path, changed: list[str], own: tuple[str, ...] = ()) \
        -> tuple[str, str, list[str]]:
    """The check: (PASS, FAIL, or NOT_NEEDED, what to do, the notes). `plan`: the text of plan.md, or None for a task
    without a plan (a quick task). `rules`: the keys of the rules of the preview. `own`: the records of the task."""
    if plan is None:
        return "NOT_NEEDED", "the task has no plan", []
    steps = parse(plan)
    if not steps:
        return "FAIL", ("plan.md has no steps. Write the work as steps under \"## Steps\": `### S1 <what it makes>`, "
                        "then `- files:` (each path in backticks), `- rules:` (the keys of the preview that it "
                        "builds), and `- tests:`. One step is small enough to build in one go"), []
    stops = [f"{step.id} {step.title}: the step names no file. Write `- files:` with each path in backticks"
             for step in steps if not step.files]
    placed = {key for step in steps for key in step.rules}
    lost = [key for key in rules if key not in placed]
    if lost:
        stops.append(f"no step builds the rule {', '.join(lost[:SHOWN])} of the preview. Name each rule in `- rules:` "
                     "of the step that builds it")
    loose = [path for path in changed if not _free(path, own) and not _planned(path, steps)]
    if loose:
        more = f" … and {len(loose) - SHOWN} more" if len(loose) > SHOWN else ""
        stops.append(f"the task changes {', '.join(loose[:SHOWN])}{more}, and no step of plan.md names them. Undo "
                     "what the task does not need. For what it needs, add the file to the step that changes it, or "
                     "add a step")
    return ("FAIL" if stops else "PASS"), "\n".join(stops), []
