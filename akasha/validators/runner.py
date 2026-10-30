"""Run the required checks of the team in a work copy."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from akasha.config import Team
from akasha.validators import secrets

TIMEOUT_SECONDS = 1800


@dataclass
class Result:
    status: dict[str, str] = field(default_factory=dict)     # check -> PASS, FAIL, or SKIP
    details: dict[str, str] = field(default_factory=dict)    # check -> the text that tells why


def _secrets(workcopy: Path, changed: list[str]) -> tuple[str, str]:
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


def _command(command: str, workcopy: Path) -> tuple[str, str]:
    try:
        done = subprocess.run(command, shell=True, cwd=workcopy, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        return "FAIL", f"the command did not stop in {TIMEOUT_SECONDS} seconds: {command}"
    output = (done.stdout + done.stderr).strip()
    return ("PASS" if done.returncode == 0 else "FAIL"), output[-3000:]


def prepare(team: Team, folder: Path) -> tuple[str, str]:
    """Run the setup command of the team in a new copy of the repository, for example to install dependencies."""
    return _command(team.commands["setup"], folder) if "setup" in team.commands else ("PASS", "")


def run(team: Team, workcopy: Path, changed: list[str]) -> Result:
    """A check with no command in the team config is SKIP. SKIP is not a pass for a required check."""
    result = Result()
    for name in team.required_checks:
        if name == "secrets":
            status, detail = _secrets(workcopy, changed)
        elif name in team.commands:
            status, detail = _command(team.commands[name], workcopy)
        else:
            status, detail = "SKIP", f"the team config has no command for the check {name}"
        result.status[name], result.details[name] = status, detail
    return result
