"""Stop commands that you cannot undo, commands that change what Akasha and GitHub share, and edits outside the work
copy of an active task.

Akasha pushes the task branches itself, GitHub merges the pull requests, and each person writes their own decision
comments on GitHub. The agent engine does none of these in the shell."""

from __future__ import annotations

import os
import re
import shlex
from collections.abc import Iterable
from pathlib import Path

from akasha.config import STATE_DIR
from akasha.coordinator.board import DECISIONS
from akasha.core.task import Task
from akasha.core.workcopy import BRANCH_PREFIX, WIP_PREFIX, WORK_DIR

DEFAULT_BRANCHES = ("main", "master")
TASK_BRANCHES = (BRANCH_PREFIX, WIP_PREFIX)             # Akasha pushes these branches itself
_SEPARATORS = re.compile(r"&&|\|\||[;|&\n]")
_CONTINUATION = re.compile(r"[\\`]\r?\n")              # a line that goes on in the next line (shell and PowerShell)
_DRIVE = re.compile(r"^[A-Za-z]:/")
_ACTIVE_STAGES = ("build", "checks")
_FOLDER_CHANGES = ("cd", "chdir", "pushd", "set-location", "sl")
_DELETES = ("rm", "remove-item", "ri", "rd", "rmdir", "del", "erase")
_GH = ("gh", "gh.exe")
# A decision word at the start of a line, also after a quote of the shell or after the "\n" of JSON
_DECISION = re.compile(r"(?:^|[\"']|\\n)\s*(?:" + "|".join(map(re.escape, DECISIONS)) + r")\b", re.I | re.M)
_MERGE_API = re.compile(r"pulls/\d+/merge\b")
_TASK_PUSH = ("it pushes to or deletes a task branch on the server. Akasha pushes the task branches itself: run the "
              "Akasha command check, handoff, or handover")


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


def _git_reason(args: list[str], in_work_copy: bool = False) -> str | None:
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
        named = [arg for arg in rest if not arg.startswith("-")]
        targets = {arg.split(":")[-1].removeprefix("refs/heads/") for arg in named}
        if targets & set(DEFAULT_BRANCHES):
            return "it pushes straight to the default branch. Akasha merges each change through a pull request"
        if any(target.startswith(TASK_BRANCHES) for target in targets):
            return _TASK_PUSH
        if "--all" in rest or "--mirror" in rest:
            return "it pushes all branches, also the task branches. Push one branch by its name"
        if in_work_copy and (len(named) < 2 or "HEAD" in targets):       # the current branch is the task branch
            return _TASK_PUSH
    if "branch" in args:
        rest = args[args.index("branch") + 1:]
        if any(flag in rest for flag in ("-D", "--delete", "-d")) and any(b in rest for b in DEFAULT_BRANCHES):
            return "it deletes the default branch"
    return None


def _files(args: list[str]) -> list[str]:
    """The files that gh reads for the text of a comment: --body-file, --input, and a field value @<file>."""
    found = []
    for number, arg in enumerate(args):
        value = arg.split("=", 1)[1] if "=" in arg else ""
        if value.startswith("@"):
            found.append(value[1:])
        elif arg.startswith(("--body-file=", "--input=")):
            found.append(value)
        elif arg in ("--body-file", "-F", "--input") and number + 1 < len(args) and "=" not in args[number + 1]:
            found.append(args[number + 1])
    return found


def _writes_decision(line: str, commands: list[list[str]], cwd: Path) -> bool:
    """True when the command line, a value in it, or a file that gh reads has a line that starts with a decision word,
    for example `/approve`."""
    texts = [line] + [arg.split("=", 1)[-1] for args in commands for arg in args]
    for name in (name for args in commands for name in _files(args)):
        try:
            texts.append((cwd / name).read_text(encoding="utf-8", errors="replace")[:100_000])
        except OSError:
            continue                                  # for example "-": the text comes from the command line
    return any(_DECISION.search(text) for text in texts)


def _gh_reason(args: list[str], line: str, commands: list[list[str]], cwd: Path) -> str | None:
    verb = tuple(arg.lower() for arg in args[1:3])
    api = verb[:1] == ("api",)
    if verb == ("pr", "merge") or (api and any(_MERGE_API.search(arg) for arg in args[2:])):
        return ("it merges a pull request. GitHub, or the merge workflow of Akasha, merges each pull request when the "
                "server check passes")
    commenting = verb in (("issue", "comment"), ("pr", "comment")) or \
        (api and any("comments" in arg or "addComment" in arg for arg in args[2:]))
    if commenting and _writes_decision(line, commands, cwd):
        return ("it writes a decision comment. A decision counts only from the GitHub account of the person who "
                "decides. Tell the person to write it on GitHub. When the person is the GitHub account of this "
                "computer, run the Akasha command approve, accept, resume, or cancel")
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
    commands = _commands(line)
    in_work_copy = _inside(cwd, root / WORK_DIR)
    for args in commands:
        if args[0].lower() in _FOLDER_CHANGES:
            moved = True
            continue
        if args[0] == "git":
            reason = _git_reason(args[1:], in_work_copy)
        elif args[0].lower() in _GH:
            reason = _gh_reason(args, line, commands, cwd)
        else:
            reason = _delete_reason(args, cwd, root, moved)
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
