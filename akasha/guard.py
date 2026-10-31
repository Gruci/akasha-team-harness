"""Stop what the agent engine must not do, before it runs.

Commands: a force push, a push to the default branch, a delete of the default branch, a merge or an approval of a
pull request by hand (Akasha lands each task), a recursive delete outside the project, and a change of the state of
Akasha. Edits: a change of the repository in the main checkout (each change is a task), and a change of the code of a
task before its preview is approved and its plan passed the review."""

from __future__ import annotations

import os
import re
import shlex
from collections.abc import Callable
from pathlib import Path

from akasha.config import RECORDS_DIR, STATE_DIR
from akasha.repo import git, inside
from akasha.task import Task

DEFAULT_BRANCHES = ("main", "master")
_SEPARATORS = re.compile(r"&&|\|\||[;|&\n]")
_CONTINUATION = re.compile(r"[\\`]\r?\n")
_DRIVE = re.compile(r"^[A-Za-z]:/")
_FOLDER_CHANGES = ("cd", "chdir", "pushd", "set-location", "sl")
_DELETES = ("rm", "remove-item", "ri", "rd", "rmdir", "del", "erase")
_READERS = ("cat", "type", "get-content", "gc", "ls", "dir", "get-childitem", "head", "tail", "less", "more", "grep",
            "rg", "findstr", "select-string", "python", "py", "git")
_GIT_VALUES = ("-C", "-c", "--git-dir", "--work-tree")
_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_MERGE_API = re.compile(r"pulls/\d+/merge\b|\b(?:mergePullRequest|enablePullRequestAutoMerge)\b")
_ENV_FILE = re.compile(r"^\.env(?:\.(?!example$|sample$|template$|dist$)[\w.-]+)?$", re.I)
_STATE = re.compile(r"\.akasha[\\/]+state", re.I)
LAND = "Akasha lands each task: run `akasha land <task>`"


def _commands(line: str) -> list[list[str]]:
    words = []
    for part in _SEPARATORS.split(_CONTINUATION.sub(" ", line).replace("\\", "/")):
        try:
            tokens = shlex.split(part, posix=True)
        except ValueError:
            tokens = part.split()
        while tokens and (_ASSIGNMENT.match(tokens[0]) or tokens[0] == "env"):
            tokens = tokens[1:]
        if tokens:
            words.append(tokens)
    return words


def _short_flag(arg: str, letter: str) -> bool:
    return re.fullmatch(rf"-[A-Za-z]*{letter}[A-Za-z]*", arg) is not None


def _git_reason(args: list[str]) -> str | None:
    number = 0
    while number < len(args) and args[number].startswith("-"):
        number += 2 if args[number] in _GIT_VALUES else 1
    command, rest = (args[number].lower(), args[number + 1:]) if number < len(args) else ("", [])
    if command == "push":
        if any(arg.startswith("--force") or _short_flag(arg, "f") or (arg.startswith("+") and len(arg) > 1)
               for arg in rest):
            return "a force push replaces history on the server"
        named = [arg for arg in rest if not arg.startswith("-")]
        targets = {arg.split(":")[-1].removeprefix("refs/heads/") for arg in named}
        if ("--delete" in rest or any(_short_flag(arg, "d") for arg in rest)) and targets & set(DEFAULT_BRANCHES):
            return "it deletes the default branch on the server"
        if any(arg in (f":{branch}" for branch in DEFAULT_BRANCHES) for arg in named):
            return "it deletes the default branch on the server"
        if targets & set(DEFAULT_BRANCHES):
            return f"it pushes straight to the default branch. {LAND}"
    if command == "branch" and any(flag in rest for flag in ("-D", "-d", "--delete")) \
            and any(branch in rest for branch in DEFAULT_BRANCHES):
        return "it deletes the default branch"
    return None


def _gh_reason(args: list[str], line: str) -> str | None:
    words = [arg.lower() for arg in args[1:] if not arg.startswith("-")][:2]
    if words == ["pr", "merge"] or (words[:1] == ["api"] and _MERGE_API.search(line)):
        return f"it merges a pull request by hand. {LAND}"
    if words == ["pr", "review"] and any(arg == "--approve" or _short_flag(arg, "a") for arg in args):
        return "it approves a pull request. A reviewer approves on GitHub, in person"
    return None


def _delete_reason(args: list[str], cwd: Path, root: Path, moved: bool) -> str | None:
    if args[0].lower() not in _DELETES:
        return None
    if not any(arg.lower() in ("--recursive", "/s") or (arg.startswith("-") and not arg.startswith("--")
                                                         and "r" in arg.lower()) for arg in args[1:]):
        return None
    targets = [arg for arg in args[1:] if not arg.startswith("-") and not (len(arg) == 2 and arg.startswith("/"))]
    if targets and moved:
        return "it deletes files after a change of the folder in the same command, so Akasha cannot see the target"
    for target in targets:
        if any(mark in target for mark in "$%`"):
            return f"it deletes {target}, which has a variable that Akasha cannot examine"
        if _DRIVE.match(target) and os.name != "nt":
            return f"it deletes {target}, which is outside the project"
        resolved = Path(target).expanduser()
        resolved = resolved if resolved.is_absolute() else cwd / resolved
        if target in ("/", "~", "*") or not inside(resolved, root) or resolved.resolve() == root.resolve():
            return f"it deletes {target}, which is outside the project or the whole project"
    return None


def check_command(line: str, cwd: Path, root: Path) -> str | None:
    """The reason to stop the shell command, or None."""
    commands = _commands(line)
    if _STATE.search(line) and any(args[0].lower() not in _READERS for args in commands):
        return "Akasha stopped this command because it can change the state of Akasha in .akasha/state."
    moved = False
    for args in commands:
        program = args[0].lower()
        if program in _FOLDER_CHANGES:
            moved = True
            continue
        if program in ("git", "git.exe"):
            reason = _git_reason(args[1:])
        elif program in ("gh", "gh.exe"):
            reason = _gh_reason(args, line)
        else:
            reason = _delete_reason(args, cwd, root, moved)
        if reason:
            return f"Akasha stopped this command because {reason}."
    return None


def _ignored(root: Path, path: Path) -> bool:
    try:
        relative = path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return False
    return git(root, "check-ignore", "-q", relative).returncode == 0


def check_edit(path: Path, root: Path, tasks: list[Task], set_up: bool, gate: Callable[[Task], str]) -> str | None:
    """The reason to stop an edit of the file, or None.

    `gate(task)` tells what the task still needs before its code can change, or "" when it is ready. `set_up` is True
    when the default branch has akasha.toml: before that, the administrator sets up Akasha in the main checkout."""
    if _ENV_FILE.match(path.name):
        return (f"Akasha stopped this edit: {path.name} holds secret values. Ask a person to change it, and read the "
                "values from the environment in the code.")
    if inside(path, root / STATE_DIR):
        return "Akasha stopped this edit: Akasha writes its state in .akasha/state itself."
    for task in tasks:
        if not task.workcopy or not inside(path, Path(task.workcopy)):
            continue
        if inside(path, Path(task.workcopy) / RECORDS_DIR / task.id):
            return None                                       # the preview, the research, the plan, the summary
        missing = gate(task)
        return (f"Akasha stopped this edit: task {task.id} is not ready to build. {missing}") if missing else None
    if not inside(path, root) or not set_up:
        return None
    work = [Path(task.workcopy) for task in tasks if task.workcopy]
    if any(inside(path, folder) for folder in work) or _ignored(root, path):
        return None
    return ("Akasha stopped this edit in the main checkout. Each change of the repository is a task: run "
            "`akasha start \"<title>\"`, then change the files in the work copy of the task.")
