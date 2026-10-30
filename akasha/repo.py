"""Find the main checkout of the repository, also from inside the work copy of a task."""

from __future__ import annotations

import subprocess
from pathlib import Path


def main_root(cwd: Path) -> Path | None:
    """The main checkout. A work copy is a git worktree, so its common git folder points to the main checkout."""
    found = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=cwd,
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
    if found.returncode:
        return None
    return Path(found.stdout.strip()).parent
