"""A separate git worktree for each task, so that two tasks never write over each other."""

from __future__ import annotations

import os
import re
import signal
import subprocess
from pathlib import Path

from akasha.config import Team
from akasha.core.task import Task

_QUIET = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}     # git must fail, not wait for a password that nobody types
# A new process group, so that a timeout stops a program and all the programs that it started
GROUP = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}


def stop(process: subprocess.Popen) -> None:
    """Stop a program that started in a new process group (GROUP), and all the programs that it started."""
    if os.name == "nt":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(process.pid)], capture_output=True)
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass                                      # the programs stopped before


def git(cwd: Path, *args: str, timeout: float | None = None) -> subprocess.CompletedProcess:
    """Run git. With `timeout`, git and the programs that it started for the network, for example ssh, stop after
    that many seconds, and the return code is not zero. subprocess.run stops only git, and on Windows it then waits
    for the other programs, for example until the computer stops a connection to a server that does not answer."""
    if timeout is None:
        return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", env=_QUIET)
    process = subprocess.Popen(["git", *args], cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                               encoding="utf-8", errors="replace", env=_QUIET, **GROUP)
    try:
        output, errors = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        stop(process)
        try:
            process.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            pass                                      # a program that ignores the stop keeps its output to itself
        return subprocess.CompletedProcess(["git", *args], 124, "", f"the server did not answer in {timeout:g} seconds")
    return subprocess.CompletedProcess(["git", *args], process.returncode, output, errors)


def fetch(cwd: Path, branch: str) -> subprocess.CompletedProcess:
    """Fetch one branch of origin into origin/<branch>, also in a clone that fetches only some branches."""
    return git(cwd, "fetch", "-q", "origin", f"+refs/heads/{branch}:refs/remotes/origin/{branch}")


def names(cwd: Path, *args: str) -> list[str]:
    """File names from a git listing. Names with Korean or other non-ASCII letters stay as they are."""
    listed = git(cwd, "-c", "core.quotePath=false", *args, "-z")
    if listed.returncode:
        raise RuntimeError(f"git {args[0]} failed: {listed.stderr.strip()[:300]}")
    return [name for name in listed.stdout.split("\0") if name.strip()]


def _exclude(root: Path, folder: str) -> None:
    """Make git ignore the work folder when no ignore file does: in the info/exclude file of this copy of the
    repository. Nobody commits that file, and each computer adds the folder at its first work copy. Else git status
    in the main checkout shows each work copy as a new folder."""
    if git(root, "check-ignore", "-q", f"{folder}/").returncode == 0:
        return
    found = git(root, "rev-parse", "--git-path", "info/exclude").stdout.strip()
    if not found:
        return
    path = Path(found) if Path(found).is_absolute() else root / found
    line = ("/" + re.sub(r"([*?\[])", r"\\\1", folder) + "/").encode("utf-8")      # the wildcards stay plain text
    known = path.read_bytes() if path.is_file() else b""
    if line in known.splitlines():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("ab") as file:
        file.write((b"\n" if known and not known.endswith(b"\n") else b"") + line + b"\n")


def create(root: Path, team: Team, task: Task, start: str = "HEAD") -> Path:
    """Make the work copy of the task in the work folder of the team, on the branch of the task from the start commit.
    A task that has a branch keeps it, for example a task from another computer: its branch and its pull request on
    the server stay the same, also after the team changed the branch prefix. A new task gets <branch prefix><task>.

    When an earlier run stopped after it made the branch or the folder, Akasha uses them again."""
    head = git(root, "rev-parse", start)
    if head.returncode:
        raise RuntimeError("the repository has no commit — make the first commit before a task starts"
                           if start == "HEAD" else f"git cannot find {start}")
    path = root / team.work_dir / task.id
    branch = task.branch or f"{team.branch_prefix}{task.id}"
    base = head.stdout.strip()
    _exclude(root, team.work_dir)
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
