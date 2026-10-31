"""The work copy of a task: a git worktree in the work folder, on the branch of the task."""

from __future__ import annotations

import re
from pathlib import Path

from akasha.repo import git

PUSH_SECONDS = 180


def exclude(root: Path, folder: str) -> None:
    """Make git ignore the work folder when no ignore file does, in the info/exclude file of this copy. Nobody commits
    that file. Else `git status` in the main checkout shows each work copy."""
    if git(root, "check-ignore", "-q", f"{folder}/x").returncode == 0:
        return
    path = _exclude_file(root)
    if path is None:
        return
    line = "/" + re.sub(r"([*?\[])", r"\\\1", folder) + "/"
    known = path.read_text(encoding="utf-8") if path.is_file() else ""
    if line in known.splitlines():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(("\n" if known and not known.endswith("\n") else "") + line + "\n")


def _exclude_file(root: Path) -> Path | None:
    found = git(root, "rev-parse", "--git-path", "info/exclude").stdout.strip()
    if not found:
        return None
    return Path(found) if Path(found).is_absolute() else root / found


def exclude_files(root: Path, paths: list[str]) -> None:
    """Make git ignore these files on this computer, in each work copy. The files that a check makes, for example
    __pycache__, must not go into a commit."""
    path = _exclude_file(root)
    if path is None:
        return
    known = path.read_text(encoding="utf-8") if path.is_file() else ""
    lines = ["/" + re.sub(r"([*?\[\]!#])", r"\\\1", item) for item in paths]
    missing = [line for line in lines if line not in known.splitlines()]
    if missing:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as file:
            file.write(("\n" if known and not known.endswith("\n") else "") + "\n".join(missing) + "\n")


def untracked(tree: Path) -> list[str]:
    """The files in the work copy that git does not track and does not ignore."""
    listed = git(tree, "-c", "core.quotePath=false", "ls-files", "--others", "--exclude-standard", "-z")
    return [name for name in listed.stdout.split("\0") if name]


def create(root: Path, path: Path, branch: str, start: str, new: bool = True) -> str:
    """Make the work copy at `path` on `branch`, from the commit `start`. Return the commit where it starts."""
    head = git(root, "rev-parse", start)
    if head.returncode:
        raise RuntimeError(f"git cannot find {start}. Make the first commit, or fetch the branch")
    path.parent.mkdir(parents=True, exist_ok=True)
    if new:
        made = git(root, "worktree", "add", "-b", branch, str(path), head.stdout.strip())
    elif git(root, "rev-parse", "-q", "--verify", f"refs/heads/{branch}").returncode == 0:
        made = git(root, "worktree", "add", str(path), branch)
        if made.returncode == 0:
            git(path, "merge", "-q", "--ff-only", start)
    else:
        made = git(root, "worktree", "add", "--track", "-b", branch, str(path), start)
    if made.returncode:
        raise RuntimeError(f"git worktree add failed: {made.stderr.strip()[:300]}")
    return head.stdout.strip()


def dirty(tree: Path) -> bool:
    return bool(git(tree, "status", "--porcelain").stdout.strip())


def head(tree: Path) -> str:
    return git(tree, "rev-parse", "HEAD").stdout.strip()


def commit(tree: Path, message: str, allow_empty: bool = False) -> bool:
    """Commit each change of the work copy. True when a commit was made."""
    if not allow_empty and not dirty(tree):
        return False
    git(tree, "add", "-A")
    done = git(tree, "commit", "-q", "-m", message, *(["--allow-empty"] if allow_empty else []))
    if done.returncode:
        raise RuntimeError(f"git commit failed: {(done.stderr or done.stdout).strip()[:300]}")
    return True


def push(tree: Path, branch: str) -> None:
    """Push the branch of the task, never with force. When the server has newer commits of the branch, for example
    an update of the pull request, merge them first."""
    done = git(tree, "push", "-q", "-u", "origin", f"HEAD:refs/heads/{branch}", timeout=PUSH_SECONDS)
    if done.returncode and "rejected" in done.stderr + done.stdout:
        pull(tree, branch)
        done = git(tree, "push", "-q", "-u", "origin", f"HEAD:refs/heads/{branch}", timeout=PUSH_SECONDS)
    if done.returncode:
        raise RuntimeError(f"git push failed: {done.stderr.strip()[:300]}. Akasha never forces a push")


def pull(tree: Path, branch: str) -> None:
    """Merge the commits of the branch on the server into the work copy."""
    git(tree, "fetch", "-q", "origin", f"+refs/heads/{branch}:refs/remotes/origin/{branch}", timeout=PUSH_SECONDS)
    if git(tree, "rev-parse", "-q", "--verify", f"refs/remotes/origin/{branch}").returncode:
        return
    merged = git(tree, "merge", "-q", "--no-edit", f"origin/{branch}")
    if merged.returncode:
        git(tree, "merge", "--abort")
        raise RuntimeError(f"the branch {branch} on the server conflicts with the work copy {tree}. Run git merge "
                           f"origin/{branch} there, repair the conflicts, and commit")


def remove(root: Path, path: Path, branch: str, force: bool = False) -> str:
    """Remove the work copy and the local branch. Return a problem, or ""."""
    if path.is_dir():
        done = git(root, "worktree", "remove", *(["--force"] if force else []), str(path))
        if done.returncode:
            return f"git cannot remove the work copy {path}: {done.stderr.strip()[:200]}"
    git(root, "worktree", "prune")
    if branch:
        git(root, "branch", "-D", branch)
    return ""
