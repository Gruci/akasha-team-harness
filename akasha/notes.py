"""The notes of a task: what each step of the work found, for the step after it.

The work of a task runs in steps: the preview, the plan, and the build. An agent that goes on from one step to the
next reads its whole conversation again at each call: the guides and the code that the preview needed come along to
each call of the plan and of the build. So each step runs in a new context. What a step found must then be in a
file, not in the head of an agent: each step ends with its own part of notes.md in the records of the task, and the
next step starts from that file and from `akasha status <task> --brief`. It opens only the lines that the notes
name, and the files that it changes: it does not explore the code again.

    ## Plan

    ### Facts
    - `src/orders/queries.py:44` `list_orders(filter)` gives the orders of one day. It has two callers:
      `src/orders/api.py:12` and `src/reports/daily.py:80`
    ### Decisions
    ### Next
    ### Examples
    ### Traps
    ### Not verified
    ### Commands

Each part has these seven fields (FIELDS). A field with nothing says `none`. Each fact names its file and line, so
the next step opens only that place, and a wrong fact shows at once.

`akasha notes <task>` examines the part of the step that ends: each field is there, each fact names a file and a
line, and each `path:line` of the part is in the work copy. It keeps the digest of the part that passed (Task.notes).
Akasha does not go on to the next step without it: `akasha preview` shows no preview without the part Preview, and no
code changes without the part Plan (flow.gate). Akasha examines a part once, at the end of its step: the build moves
the lines that the part Plan names, and that stops nothing.

The reviewer never reads the notes: they hold what the worker believes, and a mistake of the worker must not reach
the review through them. The reviewer reads the code itself.

A quick task has no steps and keeps no notes. A task that an older Akasha started has none either (Task.notes is
empty): nothing stops it."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from akasha import review
from akasha.task import Task, load, record, records, save

NOTES = "notes.md"
PARTS = ("preview", "plan", "build")             # in the order of the steps
TITLES = {"preview": "Preview", "plan": "Plan", "build": "Build"}
FIELDS = ("Facts", "Decisions", "Next", "Examples", "Traps", "Not verified", "Commands")
SHOWN = 6                                        # the problems of a part that one message tells

_COMMENT = re.compile(r"<!--.*?-->", re.S)
_PART = re.compile(r"^##[ \t]+(preview|plan|build)\b[^\n]*$", re.I | re.M)
_HEAD = re.compile(r"^##[ \t]+\S", re.M)         # where a part ends: the next part, or another heading of its level
_FIELD = re.compile(r"^###[ \t]+(.+?)[ \t]*#*[ \t]*$", re.M)
_ITEM = re.compile(r"^[ ]{0,1}(?:[-*+]|\d+[.)])[ \t]+", re.M)
_NONE = re.compile(r"[-*+\s`]*none[.\s`]*", re.I)
_URL = re.compile(r"https?://[^\s`)>\]]+")
# A file with a line: `path:44` or `path:44-60`. The path has no blank
_REF = re.compile(r"(?<![\w./\\@~+-])((?:[A-Za-z]:[\\/])?[\w./\\@~+\[\]()-]*[\w\])]):(\d+)(?:[-–](\d+))?(?!\w)")
_EXTENSION = re.compile(r"\.[A-Za-z][A-Za-z0-9]{0,7}$")

FORM = """\
# Notes

<!-- What each step of the work found, for the step after it. Each step runs in a new context: the next agent starts
     from this file and from `akasha status {task} --brief`. It opens only the lines that this file names, and does
     not explore the code again. So write what is true and exact, and only what the next step needs.

     Each step adds its own part at its end: `## Preview`, `## Plan`, or `## Build`, with these seven headings. Write
     `none` under a heading that has nothing. Then run `akasha notes {task}`: it examines the part, and each file
     and line that the part names. Never change the part of another step: when one of its facts is wrong, say so
     in your own part.

     ## Plan

     ### Facts
     - `path/of/file.py:44` what is true there, and what follows from it. Each fact names its file and line, from
       the top of the work copy: `path:line` or `path:line-line`. A fact from outside the code names its address
     ### Decisions
     - what you decided, each way that you did not take, and why not
     ### Next
     - where the next step works: each file with its lines, in the order of the work. Do not repeat plan.md: name
       its step (S2) and add what it does not hold
     ### Examples
     - the existing code whose form the next step follows: `path:line`
     ### Traps
     - what you tried and what did not work; what breaks when it changes
     ### Not verified
     - what is still a guess. The next step verifies it first
     ### Commands
     - `the command of a check or a test`: what it prints when it passes -->
"""


def parts(kind: str) -> dict[str, str]:
    """The parts of the notes that a new task of this kind keeps, each without a digest yet. A quick task has no
    steps: it keeps none. Only a full task has the step of the preview."""
    if kind == "quick":
        return {}
    return {part: "" for part in PARTS if part != "preview" or kind == "full"}


def put(task: Task) -> None:
    """Write the frame of the notes where no file is: it tells how each step fills its part."""
    path = record(task, NOTES)
    if task.notes and task.workcopy and not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(FORM.format(task=task.id), encoding="utf-8")


def read(text: str) -> dict[str, str]:
    """The text of each part of the notes: part -> its text below the heading. A comment is no text."""
    text = _COMMENT.sub("", (text or "").replace("\r\n", "\n"))
    found = {}
    for head in _PART.finditer(text):
        end = _HEAD.search(text, head.end())
        found[head.group(1).lower()] = text[head.end():end.start() if end else len(text)].strip("\n")
    return found


def _fields(body: str) -> dict[str, str]:
    """The text of each field of a part: the name in lower case -> its text."""
    heads = list(_FIELD.finditer(body))
    return {head.group(1).strip().lower(): body[head.end():heads[at + 1].start() if at + 1 < len(heads)
                                               else len(body)].strip()
            for at, head in enumerate(heads)}


def _items(text: str) -> list[str]:
    """The items of a list, each with its lines that follow. A text without a list is one item."""
    starts = [found.start() for found in _ITEM.finditer(text)]
    if not starts:
        return [text] if text.strip() else []
    return [text[start:end].strip() for start, end in zip(starts, starts[1:] + [len(text)])]


def _length(path: Path, kept: dict[Path, int]) -> int:
    """The count of the lines of a file, or -1 when it is not there."""
    if path not in kept:
        try:
            data = path.read_bytes()
            kept[path] = data.count(b"\n") + (1 if data and not data.endswith(b"\n") else 0)
        except OSError:
            kept[path] = -1
    return kept[path]


def references(text: str, tree: Path, kept: dict[Path, int] | None = None) -> tuple[int, list[str]]:
    """The files with a line that a text names (`path:line`): how many of them are in the work copy `tree`, and what
    is wrong with the others. A word with a colon and a number that names no file is no reference: a time, a port, a
    step of the plan."""
    kept = {} if kept is None else kept
    good, wrong = 0, []
    for name, first, last in _REF.findall(_URL.sub(" ", text)):
        while name[0] in "([" and name.count(name[0]) > name.count(")" if name[0] == "(" else "]"):
            name = name[1:]                                   # `(path:44)`: the bracket is no part of the path
        path = name.replace("\\", "/").removeprefix("./")
        lines = _length(tree / path, kept)
        if lines < 0:
            if "/" in path or _EXTENSION.search(path):       # it looks like a file: the notes name what is not there
                wrong.append(f"`{name}:{first}` names a file that the work copy does not have")
            continue
        if max(int(first), int(last or first)) > lines or int(first) < 1:
            wrong.append(f"`{name}:{first}{f'-{last}' if last else ''}` is not in the file: it has {lines} lines")
            continue
        good += 1
    return good, list(dict.fromkeys(wrong))


def problems(body: str, tree: Path) -> list[str]:
    """What the text of one part still lacks, or []: a field, the text of a field, the file and the line of a fact,
    and each file with a line that the part names and the work copy does not have."""
    found, kept = _fields(body), {}
    lacks = [name for name in FIELDS if name.lower() not in found]
    stops = [f"it has no heading `### {name}`" for name in lacks]
    stops += [f"`### {name}` is empty: write `none` when there is nothing" for name in FIELDS
              if name not in lacks and not found[name.lower()]]
    facts = found.get("facts", "")
    if facts and not _NONE.fullmatch(facts):
        loose = [item for item in _items(facts)
                 if references(item, tree, kept) == (0, []) and not _URL.search(item)]
        if loose:
            first = " ".join(loose[0].split())[:80]
            stops.append(f"{len(loose)} of the facts name no file with a line, for example \"{first}\". Write each "
                         "fact with `path:line`, from the top of the work copy")
    stops += references(body, tree, kept)[1]
    return stops


def digest(body: str) -> str:
    """The digest of the text of one part."""
    return hashlib.sha256(body.encode("utf-8", errors="replace")).hexdigest()[:12]


def now(task: Task) -> str:
    """The part of the step that the task is in, or "" for a task that keeps no notes: the preview until the person
    approved it, the plan until the reviewer passed it, then the build."""
    if not task.notes:
        return ""
    if "preview" in task.notes and (task.status == "preview" or not task.approval):
        return "preview"
    return "build" if review.passed(task) and task.notes.get("plan") else "plan"


def _how(task: Task, part: str) -> str:
    return (f"Add the part `## {TITLES[part]}` to {record(task, NOTES)} with the seven headings `### "
            f"{'`, `### '.join(FIELDS)}`: each fact with its file and line (`path:line`), and `none` under a heading "
            f"that has nothing. Then run `akasha notes {task.id}`")


def missing(task: Task, part: str) -> str:
    """What to do when the task keeps notes and this part did not pass yet, or ""."""
    if part not in task.notes or task.notes[part]:
        return ""
    step = {"preview": "the preview", "plan": "the plan", "build": "the build"}[part]
    after = {"preview": "the plan", "plan": "the build", "build": "a repair after the review"}[part]
    return (f"The step of {step} has no notes yet: {after} starts in a new context, from the notes and not from the "
            f"code again. {_how(task, part)}.")


def line(task: Task) -> str:
    """One line for `akasha status <task> --brief`: where the notes are, the parts that passed, and the part that
    this step owes. "" for a task that keeps no notes."""
    if not task.notes:
        return ""
    done = [TITLES[part] for part in PARTS if task.notes.get(part)]
    owed = now(task)
    return (f"notes: {record(task, NOTES)} · " + (f"start from the part {', '.join(done)}" if done else
                                                 "no part yet")
            + (f" · this step ends with the part {TITLES[owed]} (`akasha notes {task.id}`)"
               if owed and not task.notes.get(owed) else ""))


def examine(root: Path, task_id: str) -> str:
    """`akasha notes <task>`: examine each part of the notes that is new or changed, and keep the digest of each
    part that passes. ValueError with what to repair, also when the part of the step that ends is not there."""
    task = load(root, task_id)
    if not task.notes:
        return (f"Task {task.id} keeps no notes between its steps"
                + (": a quick task has no steps." if task.kind == "quick" else "."))
    path, tree, step = record(task, NOTES), Path(task.workcopy), now(task)
    try:
        found = read(path.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        found = {}
    passed = []
    # Only the parts up to this step: a part of a later step waits for the end of that step
    for part in (name for name in PARTS[:PARTS.index(step) + 1] if name in task.notes and name in found):
        sha = digest(found[part])
        if task.notes[part] == sha:
            continue
        stops = problems(found[part], tree)
        if stops:
            more = f" … and {len(stops) - SHOWN} more" if len(stops) > SHOWN else ""
            raise ValueError(f"the part `## {TITLES[part]}` of {path} is not complete: " + "; ".join(stops[:SHOWN])
                             + more + f". Repair it, and run `akasha notes {task.id}` again")
        task.notes[part] = sha
        passed.append(part)
    if passed:
        save(root, task)
    owed = [part for part in PARTS[:PARTS.index(step) + 1] if part in task.notes and not task.notes[part]]
    if owed:
        raise ValueError(f"the notes of this step are not written. {_how(task, owed[0])}")
    told = f"The part {', '.join(TITLES[part] for part in passed)} of the notes passes" if passed else \
        "Each part of the notes passed already, and none changed"
    return f"{told}: {records(task)}/{NOTES}. The step after it starts from there."
