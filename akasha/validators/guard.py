"""Stop commands that you cannot undo, and edits outside the work copy of an active task."""

from __future__ import annotations

import os
import re
import shlex
from collections.abc import Iterable
from pathlib import Path

from akasha.config import STATE_DIR
from akasha.core.task import Task

DEFAULT_BRANCHES = ("main", "master")
_SEPARATORS = re.compile(r"&&|\|\||[;|&\n]")
_CONTINUATION = re.compile(r"[\\`]\r?\n")              # a line that goes on in the next line (shell and PowerShell)
_DRIVE = re.compile(r"^[A-Za-z]:/")
_ACTIVE_STAGES = ("build", "checks")
_FOLDER_CHANGES = ("cd", "chdir", "pushd", "set-location", "sl")
_DELETES = ("rm", "remove-item", "ri", "rd", "rmdir", "del", "erase")


def _commands(line: str) -> list[list[str]]:
    words = []
    joined = _CONTINUATION.sub(" ", line)
    for part in _SEPARATORS.split(joined.replace("\\", "/")):   # Windows paths use "\", which shlex reads as an escape
        try:
            tokens = shlex.split(part, posix=True)
        except ValueError:
            tokens = part.split()
        if tokens:
            words.append(tokens)
    return words


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _short_flag(arg: str, letter: str) -> bool:
    """True for -f, and also for bundled short flags such as -fu."""
    return re.fullmatch(rf"-[A-Za-z]*{letter}[A-Za-z]*", arg) is not None


def _git_reason(args: list[str]) -> str | None:
    if "push" in args:
        rest = args[args.index("push") + 1:]
        if any(arg.startswith("--force") or _short_flag(arg, "f") or (arg.startswith("+") and len(arg) > 1)
               for arg in rest):
            return "a force push replaces history on the server"
        deletes = "--delete" in rest or any(_short_flag(arg, "d") for arg in rest)
        if deletes and any(branch in rest for branch in DEFAULT_BRANCHES):
            return "it deletes the default branch on the server"
        if any(arg in (f":{branch}" for branch in DEFAULT_BRANCHES) for arg in rest):
            return "it deletes the default branch on the server"
        targets = {arg.split(":")[-1].removeprefix("refs/heads/") for arg in rest if not arg.startswith("-")}
        if targets & set(DEFAULT_BRANCHES):
            return "it pushes straight to the default branch. Akasha merges each change through a pull request"
    if "branch" in args:
        rest = args[args.index("branch") + 1:]
        if any(flag in rest for flag in ("-D", "--delete", "-d")) and any(b in rest for b in DEFAULT_BRANCHES):
            return "it deletes the default branch"
    return None


def _recursive(arg: str) -> bool:
    low = arg.lower()
    return low in ("--recursive", "/s") or (low.startswith("-") and not low.startswith("--") and "r" in low)


def _delete_reason(args: list[str], cwd: Path, root: Path, moved: bool) -> str | None:
    if args[0].lower() not in _DELETES or not any(_recursive(arg) for arg in args[1:]):
        return None
    targets = [arg for arg in args[1:] if not arg.startswith("-") and not (len(arg) == 2 and arg.startswith("/"))]
    if targets and moved:
        return "it deletes files after a change of the folder in the same command, so Akasha cannot see the target"
    for target in targets:
        if any(mark in target for mark in "$%`"):
            return f"it deletes {target}, which contains a variable that Akasha cannot examine"
        if _DRIVE.match(target) and os.name != "nt":
            return f"it deletes {target}, which is outside the project"
        expanded = Path(target).expanduser()
        resolved = expanded if expanded.is_absolute() else cwd / expanded
        if target in ("/", "~", "*") or not _inside(resolved, root) or resolved.resolve() == root.resolve():
            return f"it deletes {target}, which is outside the project or the whole project"
    return None


def check_command(line: str, cwd: Path, root: Path) -> str | None:
    """The reason to stop the shell command, or None when the command is safe to run."""
    moved = False
    for args in _commands(line):
        if args[0].lower() in _FOLDER_CHANGES:
            moved = True
            continue
        reason = _git_reason(args[1:]) if args[0] == "git" else _delete_reason(args, cwd, root, moved)
        if reason:
            return f"Akasha stopped this command because {reason}. Ask a person to do it if it is necessary."
    return None


def check_edit(path: Path, root: Path, tasks: Iterable[Task]) -> str | None:
    """Stop an edit in the main checkout while a task builds in its own work copy. Task state files are free.

    Only a work copy on this computer counts: after a handoff, the task has no work copy here."""
    active = [task for task in tasks if task.status == "open" and task.stage in _ACTIVE_STAGES and task.workcopy
              and Path(task.workcopy).is_dir()]
    if not active or not _inside(path, root) or _inside(path, root / STATE_DIR):
        return None
    if any(_inside(path, Path(task.workcopy)) for task in active):
        return None
    return (f"Akasha stopped this edit. The task {active[0].id} builds in {active[0].workcopy}. "
            "Make the change in that work copy.")
