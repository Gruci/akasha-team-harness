"""A separate git worktree for each task, so that two tasks never write over each other."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from akasha.core.task import Task

WORK_DIR = Path(".akasha") / "work"
_QUIET = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}     # git must fail, not wait for a password that nobody types


def git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                          env=_QUIET)


def names(cwd: Path, *args: str) -> list[str]:
    """File names from a git listing. Names with Korean or other non-ASCII letters stay as they are."""
    listed = git(cwd, "-c", "core.quotePath=false", *args, "-z")
    if listed.returncode:
        raise RuntimeError(f"git {args[0]} failed: {listed.stderr.strip()[:300]}")
    return [name for name in listed.stdout.split("\0") if name.strip()]


def create(root: Path, task: Task, start: str = "HEAD") -> Path:
    """Make the work copy of the task on a new branch from the start commit.

    When an earlier run stopped after it made the branch or the folder, Akasha uses them again."""
    head = git(root, "rev-parse", start)
    if head.returncode:
        raise RuntimeError("the repository has no commit — make the first commit before a task starts"
                           if start == "HEAD" else f"git cannot find {start}")
    path = root / WORK_DIR / task.id
    branch = f"akasha/{task.id}"
    base = head.stdout.strip()
    if git(root, "rev-parse", "--verify", "-q", branch).returncode == 0:
        base = git(root, "merge-base", base, branch).stdout.strip() or base
        made = git(root, "worktree", "add", str(path), branch) if not path.is_dir() else None
    else:
        made = git(root, "worktree", "add", "-b", branch, str(path), base)
    if made is not None and made.returncode:
        raise RuntimeError(f"git worktree add failed: {made.stderr.strip()[:300]}")
    task.base, task.branch, task.workcopy = base, branch, str(path)
    return path


def changed_files(task: Task) -> list[str]:
    """The files that the task changed since its base commit, also files that git does not track yet.

    A moved file counts at its old place and at its new place."""
    tree = Path(task.workcopy)
    changed = names(tree, "diff", "--name-only", "--no-renames", task.base)
    return sorted(set(changed) | set(names(tree, "ls-files", "--others", "--exclude-standard")))


def remove(root: Path, task: Task) -> None:
    """Remove the work copy. The branch stays until the pull request merges."""
    if task.workcopy and Path(task.workcopy).exists():
        removed = git(root, "worktree", "remove", task.workcopy)
        if removed.returncode:
            raise RuntimeError(f"git worktree remove failed: {removed.stderr.strip()[:300]}")
    task.workcopy = ""
