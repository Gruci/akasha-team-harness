"""Run the required checks of the team in a work copy, and in the checkout of the server check.

Each check command runs in the shell of the operating system with shell=True: cmd.exe on Windows, /bin/sh on macOS
and Linux. It is not the shell of the person, for example PowerShell or zsh."""

from __future__ import annotations

import locale
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from akasha.config import CONFIG_FILE, Check, Team
from akasha.core.risk import matches
from akasha.core.workcopy import GROUP, stop
from akasha.validators import secrets

TIMEOUT_SECONDS = 1800
WINDOWS = os.name == "nt"
# A check that did not run because the change touches no file that it examines (only_when) is not needed. It is a
# pass. SKIP (no command for a required check) and FAIL are not.
PASSING = ("PASS", "NOT_NEEDED")


@dataclass
class Result:
    status: dict[str, str] = field(default_factory=dict)     # check -> PASS, FAIL, SKIP, or NOT_NEEDED
    details: dict[str, str] = field(default_factory=dict)    # check -> the text that tells why
    notes: list[str] = field(default_factory=list)           # what occurred after the checks, for example a push


def secrets_status(workcopy: Path, changed: list[str]) -> tuple[str, str]:
    """FAIL and one line for each secret key in the changed files, else PASS."""
    hits = []
    for name in changed:
        path = workcopy / name
        if path.is_file():
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            hits += [f"{name}:{line} {kind}" for line, kind in secrets.find(text)]
    return ("FAIL", "\n".join(hits)) if hits else ("PASS", "")


def _decode(raw: bytes) -> str:
    """Most tools write UTF-8. Windows tools can write the code page of the computer, for example Korean."""
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode(locale.getpreferredencoding(False), errors="replace")


def passed(status: dict[str, str]) -> bool:
    """True when the result has checks, and each of them passed or was not needed. The stages, check, handover, and
    the server check use this one rule."""
    return bool(status) and all(item in PASSING for item in status.values())


def _command(command: str, folder: Path) -> tuple[str, str]:
    if WINDOWS and command.startswith("./"):
        command = ".\\" + command[2:]                 # cmd.exe runs .\gradlew, not ./gradlew
    process = subprocess.Popen(command, shell=True, cwd=folder, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               **GROUP)
    try:
        output, _ = process.communicate(timeout=TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        stop(process)
        try:
            process.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            pass                                      # a process that ignores the stop keeps its output to itself
        return "FAIL", f"the command did not stop in {TIMEOUT_SECONDS} seconds: {command}"
    return ("PASS" if process.returncode == 0 else "FAIL"), _decode(output).strip()[-3000:]


def prepare(team: Team, folder: Path) -> tuple[str, str]:
    """Run the setup command of the team in a new copy of the repository, for example to install dependencies."""
    return _command(team.setup, folder) if team.setup else ("PASS", "")


def needed(check: Check, changed: list[str], run_all_when: tuple[str, ...]) -> bool:
    """True when the check must run: it has no only_when, a changed file matches only_when, or a changed file
    matches run_all_when. The patterns are relative to the top of the repository."""
    patterns = check.only_when + run_all_when
    return not check.only_when or any(matches(path, pattern) for path in changed for pattern in patterns)


def command(check: Check) -> str:
    """The command of the check on this computer: on Windows, command_windows replaces the command."""
    return check.command_windows if WINDOWS and check.command_windows else check.command


def _check(name: str, check: Check, workcopy: Path, changed: list[str], team: Team) -> tuple[str, str]:
    """Run one check of the team in its folder."""
    if not needed(check, changed, team.run_all_when):
        return "NOT_NEEDED", f"no changed file matches only_when: {', '.join(check.only_when)}"
    folder = workcopy / check.cwd
    if not folder.is_dir():
        return "FAIL", (f"the folder {check.cwd} of the check {name} does not exist. Correct cwd in [checks.{name}] "
                        f"of {CONFIG_FILE}, or add the folder")
    return _command(command(check), folder)


def run(team: Team, workcopy: Path, changed: list[str]) -> Result:
    """Run each required check. A check with no command in the team config is SKIP. SKIP is not a pass for a
    required check. The built-in check secrets examines the changed files and runs no command."""
    result = Result()
    for name in team.required_checks:
        if name == "secrets":
            status, detail = secrets_status(workcopy, changed)
        elif name in team.checks:
            status, detail = _check(name, team.checks[name], workcopy, changed, team)
        else:
            status, detail = "SKIP", f"the team config has no command for the check {name}"
        result.status[name], result.details[name] = status, detail
    return result
