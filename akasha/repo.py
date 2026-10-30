"""Find the main checkout of the repository, also from inside the work copy of a task, and run the GitHub command line."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


def main_root(cwd: Path) -> Path | None:
    """The main checkout. A work copy is a git worktree, so its common git folder points to the main checkout."""
    found = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=cwd,
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
    if found.returncode:
        return None
    return Path(found.stdout.strip()).parent


def gh(root: Path, *args: str, payload: dict | None = None) -> subprocess.CompletedProcess:
    """Run the GitHub command line. When gh is missing or does not answer, the return code is not zero."""
    try:
        return subprocess.run(["gh", *args], cwd=root, input=json.dumps(payload) if payload is not None else None,
                              capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
    except (OSError, subprocess.TimeoutExpired) as error:
        return subprocess.CompletedProcess(["gh", *args], 127, "", str(error))
