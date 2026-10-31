"""Stop commands that you cannot undo, commands that change what Akasha and GitHub share, and edits outside the work
copy of an active task.

Akasha pushes the task branches itself and writes the task state on the issues, GitHub merges the pull requests, and
each person writes their own decision comments on GitHub. The agent engine does none of these in the shell, and it
does not edit, delete, or hide a comment."""

from __future__ import annotations

import os
import re
import shlex
from collections.abc import Iterable
from pathlib import Path

from akasha.config import BRANCH_PREFIX, STATE_DIR, WIP_PREFIX, WORK_DIR, Team
from akasha.coordinator.board import DECISIONS
from akasha.core.task import Task
from akasha.infra.server import MERGE_LABEL

DEFAULT_BRANCHES = ("main", "master")
TASK_BRANCHES = (BRANCH_PREFIX, WIP_PREFIX)             # Akasha pushes these branches itself, and those of [work]
_SEPARATORS = re.compile(r"&&|\|\||[;|&\n]")
_CONTINUATION = re.compile(r"[\\`]\r?\n")              # a line that goes on in the next line (shell and PowerShell)
_DRIVE = re.compile(r"^[A-Za-z]:/")
_ACTIVE_STAGES = ("build", "checks")
_FOLDER_CHANGES = ("cd", "chdir", "pushd", "set-location", "sl")
_DELETES = ("rm", "remove-item", "ri", "rd", "rmdir", "del", "erase")
_GH = ("gh", "gh.exe")
_GH_VALUES = ("-R", "--repo")                           # a gh flag with a value, also before the gh command
_GIT_VALUES = ("-C", "-c", "--git-dir", "--work-tree", "--namespace", "--config-env")    # git flags with a value
_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")   # a variable before a command: GH_REPO=a/b gh ...
# A decision word at the start of a line, also after a quote of the shell or after the "\n" of JSON
_DECISION = re.compile(r"(?:^|[\"']|\\n)\s*(?:" + "|".join(map(re.escape, DECISIONS)) + r")\b", re.I | re.M)
# A merge through the REST API or through GraphQL, also the auto-merge
_MERGE_API = re.compile(r"pulls/\d+/merge\b|\b(?:mergePullRequest|enablePullRequestAutoMerge)\b")
_COMMENT_API = re.compile(r"issues/comments/\d+")
_COMMENT_CHANGE = re.compile(r"\b(?:updateIssueComment|deleteIssueComment|minimizeComment)\b")
_ISSUE_API = re.compile(r"issues/\d+/?$")
_ISSUE_CHANGE = re.compile(r"\bupdateIssue\b")
_BODY_FLAGS = ("--body", "-b", "--body-file", "-F")
_LABEL_FLAGS = ("--label", "-l", "--add-label")          # the flags of gh that give labels, with a list of names
_LABEL_API = re.compile(r"issues/\d+/labels\b")
_LABEL_CHANGE = re.compile(r"\baddLabelsToLabelable\b")   # GraphQL names the labels by their ids
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


def _program(args: list[str]) -> list[str]:
    """The command without the variables before it, for example `GH_REPO=a/b gh pr merge 5` or `env X=1 git push`."""
    rest = list(args)
    while rest and (_ASSIGNMENT.match(rest[0]) or rest[0] == "env"):
        rest = rest[1:]
    return rest


def _folder(here: Path | None, args: list[str]) -> Path | None:
    """The folder after cd, pushd, or Set-Location, or None when Akasha cannot tell it."""
    targets = [arg for arg in args if not arg.startswith("-")]
    if not targets or any(mark in targets[0] for mark in "$%`"):
        return None
    path = Path(targets[0]).expanduser()
    if path.is_absolute():
        return path
    return here / path if here is not None else None


def _git_folder(args: list[str], folder: Path | None) -> Path | None:
    """The folder where git works: the folder of the command, or the folder of `git -C <folder>`."""
    number = 0
    while number < len(args) and args[number].startswith("-"):
        if args[number] == "-C" and number + 1 < len(args):
            folder = _folder(folder, [args[number + 1]])
        number += 2 if args[number] in _GIT_VALUES else 1
    return folder


def _git_command(args: list[str]) -> tuple[str, list[str]]:
    """The git command, for example push, and the words after it. The flags of git before the command are not the
    command, for example `git -C <folder> push`. Thus `git stash push` is the command stash."""
    number = 0
    while number < len(args) and args[number].startswith("-"):
        number += 2 if args[number] in _GIT_VALUES else 1
    return (args[number].lower(), args[number + 1:]) if number < len(args) else ("", [])


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _short_flag(arg: str, letter: str) -> bool:
    """True for -f, and also for bundled short flags such as -fu."""
    return re.fullmatch(rf"-[A-Za-z]*{letter}[A-Za-z]*", arg) is not None


def _git_reason(args: list[str], in_work_copy: bool = False, branches: tuple[str, ...] = TASK_BRANCHES) -> str | None:
    command, rest = _git_command(args)
    if command == "push":
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
        if any(target.startswith(branches) for target in targets):
            return _TASK_PUSH
        if "--all" in rest or "--mirror" in rest:
            return "it pushes all branches, also the task branches. Push one branch by its name"
        if in_work_copy and (len(named) < 2 or "HEAD" in targets):       # the current branch is the task branch
            return _TASK_PUSH
    if command == "branch":
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


def _texts(line: str, commands: list[list[str]], cwd: Path) -> list[str]:
    """The command line, each value in it, and each file that gh reads for a text."""
    texts = [line] + [arg.split("=", 1)[-1] for args in commands for arg in args]
    for name in (name for args in commands for name in _files(args)):
        try:
            texts.append((cwd / name).read_text(encoding="utf-8", errors="replace")[:100_000])
        except OSError:
            continue                                  # for example "-": the text comes from the command line
    return texts


def _gh_verb(args: list[str]) -> tuple[str, ...]:
    """The gh command, for example ("pr", "merge"). gh also reads the flag -R <repository> before the command."""
    words, rest = [], iter(args[1:])
    for arg in rest:
        if arg in _GH_VALUES:
            next(rest, None)
        elif not arg.startswith("-"):
            words.append(arg.lower())
            if len(words) == 2:
                break
    return tuple(words)


def _method(args: list[str]) -> str:
    """The HTTP method that `gh api` names with -X or --method, in upper case, or ""."""
    for number, arg in enumerate(args):
        if arg in ("-X", "--method") and number + 1 < len(args):
            return args[number + 1].upper()
        if arg.startswith("--method="):
            return arg.removeprefix("--method=").upper()
        if arg.startswith("-X") and len(arg) > 2:
            return arg.removeprefix("-X").upper()
    return ""


def _changes_comment(verb: tuple[str, ...], args: list[str], texts: list[str]) -> bool:
    """True when gh edits, deletes, or hides a comment."""
    if verb[1:] == ("comment",):
        return any(arg in ("--edit-last", "--delete-last") for arg in args)
    return verb[:1] == ("api",) and (any(_COMMENT_CHANGE.search(text) for text in texts) or (
        _method(args) in ("PATCH", "DELETE") and any(_COMMENT_API.search(arg) for arg in args)))


def _changes_issue(verb: tuple[str, ...], args: list[str], texts: list[str]) -> bool:
    """True when gh gives an issue a new body, or changes an issue through the API."""
    if verb == ("issue", "edit"):
        return any(arg in _BODY_FLAGS or arg.startswith(("--body=", "--body-file=")) for arg in args)
    return verb[:1] == ("api",) and (any(_ISSUE_CHANGE.search(text) for text in texts) or (
        _method(args) == "PATCH" and any(_ISSUE_API.search(arg) for arg in args)))


def _gives_merge_label(verb: tuple[str, ...], args: list[str], texts: list[str]) -> bool:
    """True when gh gives an issue or a pull request the merge label of Akasha, also in a list of labels. GraphQL
    names the labels by their ids, so each label change through GraphQL counts."""
    if verb[:1] == ("api",):
        return any(_LABEL_CHANGE.search(text) for text in texts) or (
            any(_LABEL_API.search(arg) for arg in args) and any(MERGE_LABEL in text.lower() for text in texts))
    if verb not in (("pr", "create"), ("pr", "edit"), ("issue", "create"), ("issue", "edit")):
        return False
    values = [args[number + 1] for number, arg in enumerate(args[:-1]) if arg in _LABEL_FLAGS]
    values += [arg.split("=", 1)[1] for arg in args if arg.split("=", 1)[0] in _LABEL_FLAGS and "=" in arg]
    return any(name.strip().lower() == MERGE_LABEL for value in values for name in value.split(","))


def _gh_reason(args: list[str], line: str, commands: list[list[str]], cwd: Path) -> str | None:
    verb, texts = _gh_verb(args), _texts(line, commands, cwd)
    api = verb[:1] == ("api",)
    if verb == ("pr", "merge") or (api and any(_MERGE_API.search(text) for text in texts)):
        return ("it merges a pull request or turns on its auto-merge. GitHub, or the merge workflow of Akasha, merges "
                "each pull request when the server check passes")
    if _gives_merge_label(verb, args, texts):
        return (f"it can give a pull request the label {MERGE_LABEL}. Akasha gives that label at the handover, and "
                "where GitHub has no auto-merge, the merge workflow of Akasha merges each pull request with it")
    if _changes_comment(verb, args, texts):
        return ("it edits, deletes, or hides a comment. Then a later decision comment can stop counting, and an "
                "earlier decision counts again")
    if _changes_issue(verb, args, texts):
        return ("it changes the body or the fields of an issue. The issue of an Akasha task holds the state of the "
                "task, and Akasha writes it itself")
    commenting = verb in (("issue", "comment"), ("pr", "comment")) or \
        (api and any("comments" in arg or "addComment" in arg for arg in args[1:]))
    if commenting and any(_DECISION.search(text) for text in texts):
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


def check_command(line: str, cwd: Path, root: Path, team: Team | None = None,
                  tasks: Iterable[Task] = ()) -> str | None:
    """The reason to stop the shell command, or None when the command is safe to run.

    In a work copy, a push of the current branch is a push of the task branch. The folder of git is the folder of the
    command, the folder after a change of the folder in the same command, or the folder of `git -C`. The task
    branches and the work copies have the prefixes and the folder of [work] in the team rules `team`, and the default
    ones too. Each task keeps its branch and its work copy after a change of [work], so the branches and the work
    copies of the tasks on this computer `tasks` count too."""
    team, known = team or Team(), list(tasks)
    branches = tuple(dict.fromkeys((*TASK_BRANCHES, team.branch_prefix, team.wip_prefix,
                                    *(task.branch for task in known if task.branch))))
    folders = (root / WORK_DIR, root / team.work_dir, *(Path(task.workcopy) for task in known if task.workcopy))
    moved, here = False, cwd
    commands = [args for args in map(_program, _commands(line)) if args]
    for args in commands:
        if args[0].lower() in _FOLDER_CHANGES:
            moved, here = True, _folder(here, args[1:])
            continue
        if args[0] == "git":
            folder = _git_folder(args[1:], here)
            in_work_copy = folder is not None and any(_inside(folder, work) for work in folders)
            reason = _git_reason(args[1:], in_work_copy, branches)
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
