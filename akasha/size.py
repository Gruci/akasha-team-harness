"""The check `size`: a function, a file, and a task stay small enough to read and to undo.

    [size]
    function = 100     # lines of one function. 0 turns the rule off
    file = 800         # lines of one file of code
    task = 1500        # lines that one task changes in code, without tests and records

- function: a function that the change makes or makes longer is not over the limit. Python only: for another
  language the linter of the team holds the rule.
- file: a file over the limit does not grow. A file under the limit does not go over it.
- task: one task does not change more lines of code than the limit. A move of a file counts as no change. A larger
  change goes in parts: each part is its own task, so that a person can see what it does and a revert undoes one thing.

A limit is a signal, not the goal: the goal is code where one part changes for one reason. So the check never asks
to cut an old file into pieces. It looks only at what the change makes new or longer, and an administrator can change
each number. The limit of a task does not stop an administrator: a rename across the repository is their task."""

from __future__ import annotations

import ast
from pathlib import Path

from akasha import core, diff
from akasha.config import Team
from akasha.repo import git, names
from akasha.sheets import CODE
from akasha.task import outside

CHECK = "size"
SHOWN = 8


def _functions(text: str) -> dict[str, tuple[int, int]]:
    """name with its classes -> (first line, lines) of each function of a Python file. A function inside a function
    is part of the outer one."""
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError, RecursionError):
        return {}
    found: dict[str, tuple[int, int]] = {}

    def walk(body: list[ast.stmt], owner: str) -> None:
        for node in body:
            if isinstance(node, ast.ClassDef):
                walk(node.body, f"{owner}{node.name}.")
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                found[owner + node.name] = (node.lineno, (node.end_lineno or node.lineno) - node.lineno + 1)

    walk(tree.body, "")
    return found


def _code(path: str, own: tuple[str, ...]) -> bool:
    return path.endswith(CODE) and not core.TEST.search(path) and outside(path, own)


def _at(tree: Path, commit: str, path: str) -> str | None:
    shown = git(tree, "show", f"{commit}:{path}")
    return shown.stdout if shown.returncode == 0 else None


def examine(team: Team, tree: Path, base: str, changed: list[str], own: tuple[str, ...] = (), admin: bool = False) \
        -> tuple[str, str, list[str]]:
    """The check: (PASS, FAIL, or NOT_NEEDED, what to do, the notes). `own`: the folders of the records of the task."""
    if not (team.size_function or team.size_file or team.size_task):
        return "NOT_NEEDED", "the team turned each limit of [size] off", []
    stops, notes = [], []
    code = [path for path in changed if _code(path, own) and (tree / path).is_file()]
    for path in code:
        try:
            text = (tree / path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        old = _at(tree, base, path)
        if team.size_file:
            now, before = text.count("\n") + 1, (old.count("\n") + 1 if old is not None else 0)
            if now > team.size_file and now > before:
                grew = f"this change makes it longer ({before} before)" if before > team.size_file else \
                    "this change takes it over the limit" if before else "it is new"
                stops.append(f"file — {path} has {now} lines, the limit is {team.size_file}, and {grew}. Put the new "
                             "code into a file of its own responsibility in the same area")
        if team.size_function and path.endswith(core.PY):
            before_sizes = _functions(old) if old is not None else {}
            for name, (line, size) in _functions(text).items():
                if size > team.size_function and size > before_sizes.get(name, (0, 0))[1]:
                    stops.append(f"function — {path}:{line} {name} has {size} lines, and the limit is "
                                 f"{team.size_function}. Extract the steps that have a name of their own; each one "
                                 "does one thing")
    if team.size_task:
        counted = {path: sum(count) for path, count in diff.counts(tree, base, renames=True).items()
                   if _code(path, own)}
        untracked = [path for path in names(tree, "ls-files", "--others", "--exclude-standard") if _code(path, own)]
        for path in untracked:
            try:
                counted.setdefault(path, (tree / path).read_text(encoding="utf-8", errors="replace").count("\n") + 1)
            except OSError:
                pass
        total = sum(counted.values())
        if total > team.size_task:
            line = (f"task — the change is {total} lines of code in {len(counted)} files, and one task is at most "
                    f"{team.size_task}. Land one part that works alone first, and make the next part a task of its "
                    "own: a person can then see what each one does, and a revert undoes one thing")
            (notes if admin else stops).append(("note — " if admin else "") + line)
    more = f"\n… and {len(stops) - SHOWN} more" if len(stops) > SHOWN else ""
    return ("FAIL" if stops else "PASS"), "\n".join(stops[:SHOWN]) + more, notes
