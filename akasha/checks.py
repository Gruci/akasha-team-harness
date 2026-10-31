"""Run the required checks of the team in a work copy, and in the checkout of the server check.

Each command runs in the shell of the operating system: cmd.exe on Windows, /bin/sh on macOS and Linux."""

from __future__ import annotations

import fnmatch
import locale
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from akasha import secrets
from akasha.config import CONFIG_FILE, Check, Team
from akasha.repo import GROUP, names, stop

TIMEOUT_SECONDS = 1800
WINDOWS = os.name == "nt"
PASSING = ("PASS", "NOT_NEEDED")         # NOT_NEEDED: the change touches no file that the check examines


@dataclass
class Result:
    status: dict[str, str] = field(default_factory=dict)     # check -> PASS, FAIL, SKIP, or NOT_NEEDED
    details: dict[str, str] = field(default_factory=dict)    # check -> the end of its output


def matches(path: str, pattern: str) -> bool:
    """A file pattern: * also matches /, and a leading **/ also matches a file at the top."""
    if pattern.startswith("**/") and fnmatch.fnmatchcase(path, pattern[3:]):
        return True
    return fnmatch.fnmatchcase(path, pattern)


def changed_files(tree: Path, base: str) -> list[str]:
    """The files that changed in the work copy since the base commit, also new files that git does not track."""
    changed = names(tree, "diff", "--name-only", "--no-renames", base) if base else []
    return sorted(set(changed) | set(names(tree, "ls-files", "--others", "--exclude-standard")))


def _decode(raw: bytes) -> str:
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode(locale.getpreferredencoding(False), errors="replace")


def shell(command: str, folder: Path) -> tuple[str, str]:
    """Run one command: PASS or FAIL, and the end of its output."""
    if WINDOWS and command.startswith("./"):
        command = ".\\" + command[2:]
    process = subprocess.Popen(command, shell=True, cwd=folder, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               **GROUP)
    try:
        output, _ = process.communicate(timeout=TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        stop(process)
        process.communicate()
        return "FAIL", f"the command did not stop in {TIMEOUT_SECONDS} seconds: {command}"
    return ("PASS" if process.returncode == 0 else "FAIL"), _short(_decode(output).strip())


def _short(text: str, size: int = 3000) -> str:
    """The start and the end of a long output: a check can name its failure early and sum up at the end."""
    return text if len(text) <= size else f"{text[:size // 3]}\n…\n{text[-(size * 2 // 3):]}"


def secrets_status(tree: Path, changed: list[str]) -> tuple[str, str]:
    hits = []
    for name in changed:
        path = tree / name
        if path.is_file():
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            hits += [f"{name}:{line} {kind}" for line, kind in secrets.find(text)]
    return ("FAIL", "\n".join(hits)) if hits else ("PASS", "")


def needed(check: Check, changed: list[str], run_all_when: tuple[str, ...]) -> bool:
    patterns = check.only_when + run_all_when
    return not check.only_when or any(matches(path, item) for path in changed for item in patterns)


def command(check: Check) -> str:
    return check.command_windows if WINDOWS and check.command_windows else check.command


def run(team: Team, tree: Path, changed: list[str], only: tuple[str, ...] = ()) -> Result:
    """Run each required check, or only the checks `only`. A required check without a command is SKIP, and SKIP is
    not a pass."""
    result = Result()
    for name in team.required_checks:
        if only and name not in only:
            continue
        if name == "secrets":
            status, detail = secrets_status(tree, changed)
        elif name not in team.checks:
            status, detail = "SKIP", f"{CONFIG_FILE} has no command for the check {name}"
        elif not needed(team.checks[name], changed, team.run_all_when):
            status, detail = "NOT_NEEDED", "no changed file matches only_when"
        elif not (tree / team.checks[name].cwd).is_dir():
            status, detail = "FAIL", f"the folder {team.checks[name].cwd} of the check {name} does not exist"
        else:
            status, detail = shell(command(team.checks[name]), tree / team.checks[name].cwd)
        result.status[name], result.details[name] = status, detail
    return result


def passed(status: dict[str, str]) -> bool:
    return bool(status) and all(item in PASSING for item in status.values())


def ci(team: Team, root: Path, base: str) -> Result:
    """The server check: the checks on the files that the pull request changes. The setup command runs first."""
    changed = names(root, "diff", "--name-only", "--no-renames", f"{base}...HEAD")
    if team.setup:
        status, detail = shell(team.setup, root)
        if status != "PASS":
            return Result({"setup": status}, {"setup": detail})
    return run(team, root, changed)
