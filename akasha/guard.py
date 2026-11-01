"""Stop what the agent engine must not do, before it runs.

Commands: a force push, a push to the default branch (also of the current branch), a delete of the default branch, a
merge or an approval of a pull request by hand (Akasha lands each task), a work copy outside Akasha, a recursive
delete outside the project, and a change of the state of Akasha. Edits: a change of the repository in the main checkout or in a git
worktree that is not a task (each change is a task), a change of the code of a task before its preview is approved and
its plan passed the review, and a change by a teammate of a file that only an administrator changes."""

from __future__ import annotations

import os
import re
import shlex
from collections.abc import Callable
from pathlib import Path

from akasha.checks import matches
from akasha.config import STATE_DIR
from akasha.repo import default_branch, git, inside
from akasha.task import Task, records

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


def _git_folder(args: list[str], cwd: Path) -> Path | None:
    """The folder of `git -C <folder>` before the git command, or None."""
    number = 0
    while number < len(args) - 1 and args[number].startswith("-"):
        if args[number] == "-C":
            folder = Path(args[number + 1]).expanduser()
            return folder if folder.is_absolute() else cwd / folder
        number += 2 if args[number] in _GIT_VALUES else 1
    return None


def _current_branch(folder: Path) -> str:
    return git(folder, "symbolic-ref", "--quiet", "--short", "HEAD").stdout.strip() if folder.is_dir() else ""


def _push_reason(rest: list[str], folder: Path | None, root: Path) -> str | None:
    if any(arg.startswith("--force") or _short_flag(arg, "f") or (arg.startswith("+") and len(arg) > 1)
           for arg in rest):
        return "a force push replaces history on the server"
    named = [arg for arg in rest if not arg.startswith("-")]
    if "--all" in rest or "--mirror" in rest or any(arg.lstrip("+") == ":" for arg in named[1:]):
        return f"it pushes each branch, also the default branch. {LAND}"
    targets = {arg.split(":")[-1].removeprefix("refs/heads/") for arg in named}
    defaults = set(DEFAULT_BRANCHES) | {default_branch(root)}
    if ("--delete" in rest or any(_short_flag(arg, "d") for arg in rest)) and targets & defaults:
        return "it deletes the default branch on the server"
    if any(arg in (f":{branch}" for branch in defaults) for arg in named):
        return "it deletes the default branch on the server"
    if targets & defaults:
        return f"it pushes straight to the default branch. {LAND}"
    refspecs = named[1:]
    if refspecs and not any(spec in ("HEAD", "@") for spec in refspecs):
        return None                                   # each one names its branch, and none is the default branch
    if folder is None:
        return ("it pushes the current branch after a change of the folder, so Akasha cannot see the branch. Run "
                "`git -C <folder> push` instead")
    if _current_branch(folder) in defaults:
        return f"it pushes the current branch, which is the default branch. {LAND}"
    return None


def _git_reason(args: list[str], cwd: Path, root: Path, moved: bool, own: bool) -> str | None:
    number = 0
    while number < len(args) and args[number].startswith("-"):
        number += 2 if args[number] in _GIT_VALUES else 1
    command, rest = (args[number].lower(), args[number + 1:]) if number < len(args) else ("", [])
    if command == "push":
        return _push_reason(rest, _git_folder(args, cwd) or (None if moved else cwd), root)
    if command == "worktree" and rest[:1] == ["add"] and not own:
        return "it makes a work copy outside Akasha. Run `akasha start \"<title>\"`: it makes the work copy of a task"
    if command == "branch" and any(flag in rest for flag in ("-D", "-d", "--delete")) \
            and any(branch in rest for branch in DEFAULT_BRANCHES):
        return "it deletes the default branch"
    return None


def _gh_reason(args: list[str], line: str, own: bool) -> str | None:
    words = [arg.lower() for arg in args[1:] if not arg.startswith("-")][:2]
    if (words == ["pr", "merge"] or (words[:1] == ["api"] and _MERGE_API.search(line))) and not own:
        return f"it merges a pull request by hand. {LAND}"
    if words == ["pr", "review"] and any(arg == "--approve" or _short_flag(arg, "a") for arg in args):
        return f"it approves a pull request by hand. Akasha needs no approval of a pull request. {LAND}"
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


def folders(line: str, cwd: Path) -> list[Path]:
    """The folders that a shell command acts on: the folders of `git -C` and of a change of the folder."""
    found = []
    for args in _commands(line):
        program = args[0].lower()
        if program in _FOLDER_CHANGES and len(args) > 1:
            folder = Path(args[-1]).expanduser()
            found.append(folder if folder.is_absolute() else cwd / folder)
        elif program in ("git", "git.exe") and (folder := _git_folder(args[1:], cwd)) is not None:
            found.append(folder)
    return found


def check_command(line: str, cwd: Path, root: Path, git_only: bool = False, own: bool = False) -> str | None:
    """The reason to stop the shell command, or None. `git_only` examines only git and gh: the session works in
    another folder, and its deletes are not in this repository. `own`: the person keeps the own procedure of the
    repository ([team] own_procedure), with its own work copies and merges."""
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
            reason = _git_reason(args[1:], cwd, root, moved, own)
        elif program in ("gh", "gh.exe"):
            reason = _gh_reason(args, line, own)
        else:
            reason = None if git_only else _delete_reason(args, cwd, root, moved)
        if reason:
            return f"Akasha stopped this command because {reason}."
    return None


def _ignored(root: Path, path: Path) -> bool:
    try:
        relative = path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return False
    return git(root, "check-ignore", "-q", relative).returncode == 0


def _other_worktree(path: Path, root: Path, tasks: list[Task]) -> Path | None:
    """The top of a git worktree of this repository that holds the file and is not the work copy of a task, or None.
    Such a copy can be in a folder that git ignores, or outside the repository."""
    folder = path.parent
    while not folder.is_dir() and folder != folder.parent:
        folder = folder.parent
    found = git(folder, "rev-parse", "--path-format=absolute", "--show-toplevel", "--git-common-dir")
    lines = found.stdout.split("\n")
    if found.returncode or len(lines) < 2 or not lines[1].strip():
        return None
    top, common = Path(lines[0].strip()), Path(lines[1].strip())
    if common.parent.resolve() != root.resolve() or top.resolve() == root.resolve():
        return None
    return None if any(task.workcopy and Path(task.workcopy).resolve() == top.resolve() for task in tasks) else top


def check_edit(path: Path, root: Path, tasks: list[Task], set_up: bool, gate: Callable[[Task], str],
               own: bool = False, locked: tuple[str, ...] = ()) -> str | None:
    """The reason to stop an edit of the file, or None.

    `gate(task)` tells what the task still needs before its code can change, or "" when it is ready. `set_up` is True
    when the default branch has akasha.toml: before that, the administrator sets up Akasha in the main checkout. A
    person who keeps the own procedure of the repository (`own`) edits outside the work copies of tasks freely.
    `locked`: the file patterns that only an administrator changes, empty for an administrator."""
    if _ENV_FILE.match(path.name):
        return (f"Akasha stopped this edit: {path.name} holds secret values. Ask a person to change it, and read the "
                "values from the environment in the code.")
    if inside(path, root / STATE_DIR):
        return "Akasha stopped this edit: Akasha writes its state in .akasha/state itself."
    for task in tasks:
        if not task.workcopy or not inside(path, Path(task.workcopy)):
            continue
        if inside(path, Path(task.workcopy) / records(task)):
            return None                                       # the preview, the research, the plan, the summary
        relative = path.resolve().relative_to(Path(task.workcopy).resolve()).as_posix()
        if any(matches(relative, item) for item in locked):
            return (f"Akasha stopped this edit: only an administrator changes {relative} (the rules of Akasha, the "
                    f"GitHub files, or a risky part such as the database or the deployment). Leave it out of task "
                    f"{task.id}, or ask an administrator: `akasha help {task.id} \"<what the task needs there>\"`.")
        missing = gate(task)
        return (f"Akasha stopped this edit: task {task.id} is not ready to build. {missing}") if missing else None
    if own:
        return None
    if set_up and (other := _other_worktree(path, root, tasks)) is not None:
        return (f"Akasha stopped this edit: {other} is a git worktree that is not an Akasha task. Run `akasha start "
                "\"<title>\"` and change the files in the work copy of the task.")
    if not inside(path, root) or not set_up:
        return None
    work = [Path(task.workcopy) for task in tasks if task.workcopy]
    if any(inside(path, folder) for folder in work) or _ignored(root, path):
        return None
    return ("Akasha stopped this edit in the main checkout. Each change of the repository is a task: run "
            "`akasha start \"<title>\"`, then change the files in the work copy of the task.")
