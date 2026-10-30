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
_SEPARATORS = re.compile(r"&&|\|\||[;|\n]")
_DRIVE = re.compile(r"^[A-Za-z]:/")
_ACTIVE_STAGES = ("build", "checks")


def _commands(line: str) -> list[list[str]]:
    words = []
    for part in _SEPARATORS.split(line.replace("\\", "/")):   # Windows paths use "\", which shlex reads as an escape
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


def _git_reason(args: list[str]) -> str | None:
    if "push" in args:
        rest = args[args.index("push") + 1:]
        if any(arg in ("-f", "--force", "--force-with-lease") or arg.startswith("--force") or
               (arg.startswith("+") and len(arg) > 1) for arg in rest):
            return "a force push replaces history on the server"
        if "--delete" in rest and any(branch in rest for branch in DEFAULT_BRANCHES):
            return "it deletes the default branch on the server"
        if any(arg in (f":{branch}" for branch in DEFAULT_BRANCHES) for arg in rest):
            return "it deletes the default branch on the server"
    if "branch" in args:
        rest = args[args.index("branch") + 1:]
        if any(flag in rest for flag in ("-D", "--delete", "-d")) and any(b in rest for b in DEFAULT_BRANCHES):
            return "it deletes the default branch"
    return None


def _delete_reason(args: list[str], cwd: Path, root: Path) -> str | None:
    name = args[0].lower()
    if name == "rm" and any(arg.startswith("-") and "r" in arg.lower() for arg in args[1:]):
        targets = [arg for arg in args[1:] if not arg.startswith("-")]
    elif name in ("remove-item", "ri", "rd", "rmdir") and any(arg.lower().startswith("-r") for arg in args[1:]):
        targets = [arg for arg in args[1:] if not arg.startswith("-")]
    else:
        return None
    for target in targets:
        if _DRIVE.match(target) and os.name != "nt":
            return f"it deletes {target}, which is outside the project"
        expanded = Path(target).expanduser()
        resolved = expanded if expanded.is_absolute() else cwd / expanded
        if target in ("/", "~", "*") or not _inside(resolved, root) or resolved.resolve() == root.resolve():
            return f"it deletes {target}, which is outside the project or the whole project"
    return None


def check_command(line: str, cwd: Path, root: Path) -> str | None:
    """The reason to stop the shell command, or None when the command is safe to run."""
    for args in _commands(line):
        reason = _git_reason(args[1:]) if args[0] == "git" else _delete_reason(args, cwd, root)
        if reason:
            return f"Akasha stopped this command because {reason}. Ask a person to do it if it is necessary."
    return None


def check_edit(path: Path, root: Path, tasks: Iterable[Task]) -> str | None:
    """Stop an edit in the main checkout while a task builds in its own work copy."""
    active = [task for task in tasks if task.status == "open" and task.stage in _ACTIVE_STAGES and task.workcopy]
    if not active or not _inside(path, root) or _inside(path, root / STATE_DIR.parent):
        return None
    if any(_inside(path, Path(task.workcopy)) for task in active):
        return None
    return (f"Akasha stopped this edit. The task {active[0].id} builds in {active[0].workcopy}. "
            "Make the change in that work copy.")
