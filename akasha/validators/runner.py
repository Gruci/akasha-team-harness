"""Run the required checks of the team in a work copy."""

from __future__ import annotations

import locale
import os
import signal
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from akasha.config import Team
from akasha.validators import secrets

TIMEOUT_SECONDS = 1800
# A new process group, so that a timeout stops the command and all the processes that it started
_GROUP = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}


@dataclass
class Result:
    status: dict[str, str] = field(default_factory=dict)     # check -> PASS, FAIL, or SKIP
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


def _stop(process: subprocess.Popen) -> None:
    if os.name == "nt":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(process.pid)], capture_output=True)
    else:
        os.killpg(process.pid, signal.SIGKILL)


def _command(command: str, workcopy: Path) -> tuple[str, str]:
    if os.name == "nt" and command.startswith("./"):
        command = ".\\" + command[2:]                 # cmd.exe runs .\gradlew, not ./gradlew
    process = subprocess.Popen(command, shell=True, cwd=workcopy, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               **_GROUP)
    try:
        output, _ = process.communicate(timeout=TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        _stop(process)
        try:
            process.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            pass                                      # a process that ignores the stop keeps its output to itself
        return "FAIL", f"the command did not stop in {TIMEOUT_SECONDS} seconds: {command}"
    return ("PASS" if process.returncode == 0 else "FAIL"), _decode(output).strip()[-3000:]


def prepare(team: Team, folder: Path) -> tuple[str, str]:
    """Run the setup command of the team in a new copy of the repository, for example to install dependencies."""
    return _command(team.commands["setup"], folder) if "setup" in team.commands else ("PASS", "")


def run(team: Team, workcopy: Path, changed: list[str]) -> Result:
    """A check with no command in the team config is SKIP. SKIP is not a pass for a required check."""
    result = Result()
    for name in team.required_checks:
        if name == "secrets":
            status, detail = secrets_status(workcopy, changed)
        elif name in team.commands:
            status, detail = _command(team.commands[name], workcopy)
        else:
            status, detail = "SKIP", f"the team config has no command for the check {name}"
        result.status[name], result.details[name] = status, detail
    return result
