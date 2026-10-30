"""A separate git worktree for each task, so that two tasks never write over each other."""

from __future__ import annotations

import subprocess
from pathlib import Path

from akasha.core.task import Task

WORK_DIR = Path(".akasha") / "work"


def git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")


def create(root: Path, task: Task) -> Path:
    """Make the work copy of the task on a new branch from the current commit."""
    head = git(root, "rev-parse", "HEAD")
    if head.returncode:
        raise RuntimeError("the repository has no commit — make the first commit before a task starts")
    path = root / WORK_DIR / task.id
    branch = f"akasha/{task.id}"
    made = git(root, "worktree", "add", "-b", branch, str(path), head.stdout.strip())
    if made.returncode:
        raise RuntimeError(f"git worktree add failed: {made.stderr.strip()[:300]}")
    task.base, task.branch, task.workcopy = head.stdout.strip(), branch, str(path)
    return path


def changed_files(task: Task) -> list[str]:
    """The files that the task changed since its base commit, also files that git does not track yet."""
    tree = Path(task.workcopy)
    diff = git(tree, "diff", "--name-only", task.base)
    new = git(tree, "ls-files", "--others", "--exclude-standard")
    return sorted({line for line in (diff.stdout + new.stdout).splitlines() if line.strip()})


def remove(root: Path, task: Task) -> None:
    """Remove the work copy. The branch stays until the pull request merges."""
    if task.workcopy and Path(task.workcopy).exists():
        removed = git(root, "worktree", "remove", task.workcopy)
        if removed.returncode:
            raise RuntimeError(f"git worktree remove failed: {removed.stderr.strip()[:300]}")
    task.workcopy = ""
