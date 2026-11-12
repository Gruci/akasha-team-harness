"""The hooks of git: the two rules that hold for each agent engine, and for a person in a terminal.

The hooks of an agent engine stop a wrong command before it runs, where the engine has hooks (hooks.py). An engine
without hooks, and a person who types git, never meet them. Git itself runs these two, whatever started the command:

- pre-commit: no commit on the default branch. Each change is a task on a branch of its own.
- pre-push: no push to the default branch, and no push that deletes it. Akasha lands each task.

They hold for each person. Only a person who keeps the own procedure of the repository ([team] own_procedure) can
commit on the default branch of their checkout; nobody pushes to it. A repository that does not use Akasha yet has
no rule.

Akasha writes the two files into the hooks folder of the repository on each computer (`akasha setup`, and each
session start). It never replaces a hook of the team: where a file is there already, `akasha doctor` tells which
line to add to it. A hook that cannot run Akasha lets git go on: a broken tool must not stop git. `--no-verify` goes
around a hook of git, so these hooks are a reminder and not a wall: the server check and the watch see the result."""

from __future__ import annotations

import sys
from pathlib import Path

from akasha import config, repo
from akasha.guard import DEFAULT_BRANCHES, LAND

NAMES = ("pre-commit", "pre-push")
MARK = "# akasha-hook"
REFUSED = 2                    # the exit code of a hook that refuses: any other failure lets git go on
ZERO = "0" * 40


def text(command: str, name: str) -> str:
    """The file of one hook. Only the exit code 2 stops git."""
    return (f"#!/bin/sh\n{MARK}: Akasha wrote this file. It keeps each change on the branch of a task "
            "(akasha/githooks.py).\n"
            f'said=$({command} hook --git {name} "$@" 2>&1)\ncode=$?\n'
            f'if [ "$code" -eq {REFUSED} ]; then echo "$said" >&2; exit 1; fi\nexit 0\n')


def folder(root: Path) -> Path | None:
    """The folder of the hooks of this repository: of the main checkout, or the folder of core.hooksPath."""
    found = repo.git(root, "rev-parse", "--git-path", "hooks").stdout.strip()
    return (root / found).resolve() if found else None


def install(root: Path, command: str) -> list[str]:
    """Write the hooks of Akasha where no other hook is, and give a note for each file that Akasha left alone."""
    place = folder(root)
    if place is None:
        return []
    notes = []
    for name in NAMES:
        path, wanted = place / name, text(command, name)
        try:
            old = path.read_text(encoding="utf-8", errors="replace") if path.is_file() else None
            if old is None or (MARK in old and old != wanted):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(wanted, encoding="utf-8", newline="\n")
                path.chmod(0o755)
            elif MARK not in old and "hook --git" not in old:
                notes.append(f"{path.as_posix()} is a hook of the team, so Akasha did not change it. Add this line to "
                             f'it: {command} hook --git {name} "$@" || [ $? -ne {REFUSED} ] || exit 1')
        except OSError as error:
            notes.append(f"Akasha could not write {path.as_posix()}: {error}")
    return notes


def _exempt(root: Path) -> tuple[bool, bool]:
    """(the repository uses Akasha, this person keeps the own procedure of the repository)."""
    branch = repo.default_branch(root)
    if not config.on_server(root, branch):
        return False, False
    try:
        team = config.shared(root, branch)
    except config.ConfigError:
        return True, False
    me = repo.me(root, kept=True, timeout=5)
    return True, bool(me) and me in team.own_procedure


def pre_commit(root: Path, cwd: Path) -> str:
    """Why git must not make this commit, or ""."""
    uses, own = _exempt(root)
    if not uses or own:
        return ""
    branch = repo.git(cwd, "symbolic-ref", "--quiet", "--short", "HEAD").stdout.strip()
    if branch and branch in {*DEFAULT_BRANCHES, repo.default_branch(root)}:
        return (f"Akasha: this commit is on the default branch ({branch}). Each change of this repository is a task "
                "on a branch of its own: `akasha start \"<what you want>\"` makes its work copy. Move the change "
                "there, and commit it with `akasha check <task>`.")
    return ""


def pre_push(root: Path, lines: list[str]) -> str:
    """Why git must not make this push, or "". `lines`: what git gives a pre-push hook, one line for each ref: the
    local ref, its commit, the ref on the server, and its commit there."""
    uses, _own = _exempt(root)
    if not uses:
        return ""
    defaults = {f"refs/heads/{name}" for name in {*DEFAULT_BRANCHES, repo.default_branch(root)}}
    for line in lines:
        parts = line.split()
        if len(parts) != 4 or parts[2] not in defaults:
            continue
        name = parts[2].removeprefix("refs/heads/")
        if parts[1] == ZERO:
            return f"Akasha: this push deletes the default branch ({name}) on the server."
        return f"Akasha: this push goes straight to the default branch ({name}). {LAND}."
    return ""


def main(name: str, root: Path | None, cwd: Path) -> int:
    """The entry of a hook of git: 2 and the reason when the rule refuses, else 0."""
    if root is None:
        return 0
    why = pre_commit(root, cwd) if name == "pre-commit" else \
        pre_push(root, sys.stdin.read().splitlines()) if name == "pre-push" else ""
    if why:
        print(why)
        return REFUSED
    return 0


def state(root: Path, command: str) -> list[tuple[bool, str]]:
    """For `akasha doctor`: whether each hook of git is in place on this computer."""
    place = folder(root)
    if place is None:
        return []
    found = []
    for name in NAMES:
        path = place / name
        try:
            old = path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""
        except OSError:
            old = ""
        on = MARK in old or "hook --git" in old
        found.append((on, f"git hook {name}: " + ("in place" if on else
                                                    f"missing ({path.as_posix()}): the session start writes it, or "
                                                    "add the line of Akasha to the hook of the team")))
    return found

