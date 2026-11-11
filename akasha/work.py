"""The work copy of a task: a git worktree in the work folder, on the branch of the task.

A work copy holds no file of the archive of the other tasks. The archive grows with each merged task, and its
records are no input of the next task: git checks the work copy out without that folder (sparse-checkout). This is
the usual state, not a lock. A conflict in a file of the archive, `git stash -u`, or a file that a person makes
there puts files back: `restore` removes them again, or names what stops it."""

from __future__ import annotations

import re
import shutil
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


def _pattern(folder: str) -> str:
    """A folder as a pattern of sparse-checkout, which has the form of .gitignore: from the top, with its files."""
    return "/" + re.sub(r"([*?\[\]!#\\ ])", r"\\\1", folder.strip("/")) + "/"


def sparse(tree: Path, archive: str, own: tuple[str, ...] = ()) -> None:
    """Leave the archive out of the checkout `tree`, but for the folders `own` in it. `sparse-checkout set` turns the
    worktree config on itself and moves core.worktree there; setting that extension by hand first breaks a repository
    that has core.worktree."""
    done = git(tree, "sparse-checkout", "set", "--no-cone", "/*", "!" + _pattern(archive),
               *(_pattern(folder) for folder in own))
    if done.returncode:
        raise RuntimeError(f"git sparse-checkout failed in {tree}: {done.stderr.strip()[:300]}")


def is_sparse(tree: Path) -> bool:
    return git(tree, "config", "--get", "core.sparseCheckout").stdout.strip() == "true"


def leave_out(tree: Path, archive: str) -> str:
    """Leave the archive out of a checkout that a person uses, for example the main checkout: a session looks for
    files there before its task has a work copy. Return a note, or "". Akasha changes only a checkout that nobody
    set up: sparse rules of a person stay, and so does a checkout where a person turned them off (the doctor tells
    it), or where the folder of the archive has changes."""
    asked = git(tree, "config", "--get", "core.sparseCheckout")
    if asked.stdout.strip() == "true":
        if git(tree, "config", "--get", "core.sparseCheckoutCone").stdout.strip() == "true":
            return "this checkout has its own sparse rules (cone mode): Akasha leaves them as they are"
        listed = git(tree, "sparse-checkout", "list").stdout.splitlines()
        if "!" + _pattern(archive) in listed:
            return ""
        done = git(tree, "sparse-checkout", "add", "!" + _pattern(archive))
        return "" if done.returncode == 0 else f"git sparse-checkout failed: {done.stderr.strip()[:200]}"
    if asked.stdout.strip():                           # false: a person turned it off
        return ""
    if git(tree, "cat-file", "-e", f"HEAD:{archive.strip('/')}").returncode:
        return ""                                      # no archive yet: the checkout stays as it is
    if git(tree, "status", "--porcelain", "--", archive).stdout.strip():
        return (f"{archive} has changes in this checkout, so the checkout still holds the archive. Commit or undo "
                "them, then run `akasha doctor`")
    try:
        sparse(tree, archive)
    except RuntimeError as error:
        return str(error)
    return ""


def include(tree: Path, folder: str) -> None:
    """Bring one folder of the archive into the checkout: the records of the task of this work copy."""
    if not is_sparse(tree):
        return
    done = git(tree, "sparse-checkout", "add", _pattern(folder))
    if done.returncode:
        raise RuntimeError(f"git sparse-checkout failed in {tree}: {done.stderr.strip()[:300]}")


def restore(tree: Path) -> str:
    """Take the files that the checkout leaves out away again, after a merge or its abort put some back. Return a
    problem, or "". Git keeps a file that has changes of a person: then nothing is deleted, and the problem names
    what to do."""
    if not is_sparse(tree):
        return ""
    done = git(tree, "sparse-checkout", "reapply")
    told = (done.stderr or done.stdout).strip()
    if done.returncode or "not up to date" in told or "warning" in told.lower():
        return (f"the work copy {tree} holds files of the archive that it leaves out, and git cannot take them away: "
                f"{told[:300] or 'git sparse-checkout reapply failed'}. Commit or undo the changes of these files "
                "(a change of the archive of another task is a task of an administrator), then do the step again")
    return ""


def create(root: Path, path: Path, branch: str, start: str, new: bool = True, archive: str = "",
           own: tuple[str, ...] = ()) -> str:
    """Make the work copy at `path` on `branch`, from the commit `start`. Return the commit where it starts.
    `archive`: the folder of the archive, which the work copy leaves out, but for `own`: the records of this task
    when the landing moved them there already."""
    head = git(root, "rev-parse", start)
    if head.returncode:
        raise RuntimeError(f"git cannot find {start}. Make the first commit, or fetch the branch")
    path.parent.mkdir(parents=True, exist_ok=True)
    bare = ["--no-checkout"] if archive else []          # the files come after the sparse rules
    local = not new and git(root, "rev-parse", "-q", "--verify", f"refs/heads/{branch}").returncode == 0
    if new:
        made = git(root, "worktree", "add", *bare, "-b", branch, str(path), head.stdout.strip())
    elif local:
        made = git(root, "worktree", "add", *bare, str(path), branch)
    else:
        made = git(root, "worktree", "add", *bare, "--track", "-b", branch, str(path), start)
    if made.returncode:
        raise RuntimeError(f"git worktree add failed: {made.stderr.strip()[:300]}")
    if archive:
        try:
            sparse(path, archive, own)
            out = git(path, "checkout", "-q", branch)
            if out.returncode:
                raise RuntimeError(f"git checkout failed in {path}: {out.stderr.strip()[:300]}")
        except RuntimeError:
            remove(root, path, branch if new else "", force=True)        # no half work copy stays
            raise
    if local:
        git(path, "merge", "-q", "--ff-only", start)
    return head.stdout.strip()


def dirty(tree: Path) -> bool:
    return bool(git(tree, "status", "--porcelain").stdout.strip())


def unsaved(tree: Path) -> list[str]:
    """The files of the work copy that hold work that no commit has. A form that Akasha wrote and nobody filled
    (forms.py) holds no work: a task that only started is free to go."""
    from akasha import forms
    found = []
    for line in git(tree, "-c", "core.quotePath=false", "status", "--porcelain", "--untracked-files=all").stdout.splitlines():
        path = line[3:].strip().strip('"')
        if line.startswith("??") and not forms.written(tree / path) and (tree / path).is_file():
            continue
        found.append(path)
    return found


def head(tree: Path) -> str:
    return git(tree, "rev-parse", "HEAD").stdout.strip()


def commit(tree: Path, message: str, allow_empty: bool = False) -> bool:
    """Commit each change of the work copy. True when a commit was made."""
    if not allow_empty and not dirty(tree):
        return False
    add_all(tree)
    done = git(tree, "commit", "-q", "-m", message, *(["--allow-empty"] if allow_empty else []))
    if done.returncode:
        raise RuntimeError(f"git commit failed: {(done.stderr or done.stdout).strip()[:300]}")
    return True


def add_all(tree: Path) -> None:
    """Put each change of the work copy into the index. `git add -A` can fail and still add a part, and the commit
    after it passes: for example with a new file in a folder that the checkout leaves out. So a failure stops the
    step. The index stays as it is: a person decides about what is in it."""
    done = git(tree, "add", "-A")
    if done.returncode:
        raise RuntimeError(f"git add failed in {tree}: {(done.stderr or done.stdout).strip()[:400]}. A part of the "
                           "changes can be in the index already. Akasha made no commit. Move or remove the files that "
                           "git names (a folder of the archive of another task is not part of this task), then do "
                           "the step again")


def remote_head(tree: Path, branch: str) -> str | None:
    """The commit of the branch on the server, "" when the server has no such branch, None when git cannot ask."""
    asked = git(tree, "ls-remote", "origin", f"refs/heads/{branch}", timeout=PUSH_SECONDS)
    if asked.returncode:
        return None
    return asked.stdout.split()[0] if asked.stdout.strip() else ""


def delete_remote(tree: Path, branch: str, head: str) -> str:
    """Delete the branch of a merged task on the server, only while it is at `head`, the head of that pull
    request: a new task of the same name has another commit there, and its branch stays. A branch that is gone
    is no problem. Return a problem, or "". The step can run again."""
    now = remote_head(tree, branch)
    if now == "" or (now and now != head):
        return ""                                      # gone, or the branch of a newer task of the same name
    done = git(tree, "push", "-q", f"--force-with-lease=refs/heads/{branch}:{head}", "origin",
               f":refs/heads/{branch}", timeout=PUSH_SECONDS) if now else None
    if done is None or done.returncode:
        why = "git cannot reach the server" if done is None else done.stderr.strip()[:200]
        return (f"the branch {branch} of the merged task stays on the server ({why}), so the name of the task is not "
                "free yet. `akasha tidy` deletes it again")
    return ""


def push(tree: Path, branch: str, adopt: bool = True) -> None:
    """Push the branch of the task, never with force. When the server has newer commits of the branch, for example
    an update of the pull request, merge them first (`adopt`). A new task adopts nothing: its branch is new."""
    done = git(tree, "push", "-q", "-u", "origin", f"HEAD:refs/heads/{branch}", timeout=PUSH_SECONDS)
    if adopt and done.returncode and "rejected" in done.stderr + done.stdout:
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
        restore(tree)
        raise RuntimeError(f"the branch {branch} on the server conflicts with the work copy {tree}. Run git merge "
                           f"origin/{branch} there, repair the conflicts, and commit")


def contains(tree: Path, commit: str, number: int = 0) -> bool:
    """True when `commit` has each commit of the work copy: it is its HEAD, or a commit after it. Git fetches the
    head of pull request `number` when it does not know the commit."""
    local = head(tree)
    if local == commit:
        return True
    if number and git(tree, "cat-file", "-e", f"{commit}^{{commit}}").returncode:
        git(tree, "fetch", "-q", "origin", f"refs/pull/{number}/head", timeout=PUSH_SECONDS)
    return git(tree, "merge-base", "--is-ancestor", local, commit).returncode == 0


def _registered(root: Path, path: Path) -> bool:
    listed = git(root, "worktree", "list", "--porcelain").stdout
    return any(Path(line[len("worktree "):]).resolve() == path.resolve()
               for line in listed.splitlines() if line.startswith("worktree "))


def remove(root: Path, path: Path, branch: str, force: bool = False) -> str:
    """Remove the work copy and the local branch. Return a problem, or "" when the folder is gone."""
    if path.is_dir() and not force and dirty(path) and not unsaved(path):
        force = True                                  # only forms that nobody filled: git would refuse them
    if path.is_dir():
        done = git(root, "worktree", "remove", *(["--force"] if force else []), str(path))
        if done.returncode:
            git(root, "worktree", "prune")
            if _registered(root, path):
                return f"git cannot remove the work copy {path}: {done.stderr.strip()[:200]}"
            shutil.rmtree(path, ignore_errors=True)            # git let go of it: what is left is no work copy
            if path.is_dir():
                return f"a program still uses files in {path}: close it, then run `akasha tidy` or remove the folder"
    git(root, "worktree", "prune")
    if branch:
        git(root, "branch", "-D", branch)
    return ""
