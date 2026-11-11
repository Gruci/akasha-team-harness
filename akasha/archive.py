"""The archive of the records: the landing moves the records of a task from [work] records to [work] archive.

While a task is in work, its records are in <records>/<task>, and only the branch of the task has that folder. When
the task lands, Akasha moves the folder to <archive>/YYYY/MM/YYYY-MM-DD-<task> in one commit, after it merged the
latest default branch and before the push. So the default branch holds only the records of merged tasks, each in its
own new folder: two landings of the same day never change the same file, and no file lists the tasks.

Akasha reads the folder of one task. It finds that folder from the files that the branch of the task changed, and asks
git about one exact path: it never lists the archive. No work copy holds the archive of other tasks (work.sparse).

The network can stop the landing between two steps. `sync` runs before each step that needs the records, and brings
the state of the task in line with git again, so that the step after it continues."""

from __future__ import annotations

from pathlib import Path

from akasha import repo, work
from akasha.config import Team
from akasha.task import Task, archive_name, folders_of, records, save


def _in(folder: str, top: str) -> bool:
    return (folder + "/").startswith(top.rstrip("/") + "/")


def archived(team: Team, task: Task) -> bool:
    """True when the records of the task are in the archive."""
    return _in(records(task), team.archive_dir)


def _has(tree: Path, commit: str, path: str) -> bool:
    """True when the commit has the path. The checkout leaves the archive out, so the disk cannot tell."""
    return repo.git(tree, "cat-file", "-e", f"{commit}:{path}").returncode == 0


def _base(tree: Path) -> str:
    return repo.git(tree, "merge-base", "HEAD", f"origin/{repo.default_branch(tree)}").stdout.strip()


def folders(tree: Path, team: Team, task_id: str, start: str, end: str = "HEAD") -> tuple[str, ...]:
    """The records folders of the task that the commits from `start` to `end` hold: from the changed files alone."""
    if not start:
        return ()
    changed = repo.names(tree, "diff", "--name-only", "--no-renames", start, end)
    return tuple(folder for folder in folders_of(team, changed, [task_id]) if _has(tree, end, folder))


def of_branch(root: Path, team: Team, task_id: str, branch: str) -> tuple[str, ...]:
    """The folders of the task in the archive, on a branch of the server: the work copy of a task that another
    computer landed takes them in, and leaves the rest of the archive out."""
    ref = f"origin/{branch}"
    start = repo.git(root, "merge-base", ref, f"origin/{repo.default_branch(root)}").stdout.strip()
    return tuple(folder for folder in folders(root, team, task_id, start, ref) if _in(folder, team.archive_dir))


def _target(tree: Path, team: Team, task: Task) -> str:
    """The folder of the task in the archive. When this day already has a folder of the same task name, the number of
    the pull request stands with the date. Akasha asks git about that one path."""
    name = archive_name(task.id)
    if _has(tree, "HEAD", f"{team.archive_dir}/{name}"):
        name = archive_name(task.id, number=task.number or 2)
    return name


def _only_records(paths: list[str], own: tuple[str, ...]) -> bool:
    return bool(paths) and all(any(_in(path, folder) for folder in own) for path in paths)


def move(root: Path, team: Team, task: Task) -> bool:
    """Move the records of the task into the archive, in one commit. True when it moved them now. The work copy is
    clean before: the landing examined it. The task keeps the new folder at once, before the push: a push that fails
    must not leave a task that names a folder that is gone."""
    if archived(team, task):
        return False
    tree, old = Path(task.workcopy), records(task)
    if not (tree / old).is_dir():
        raise RuntimeError(f"the records folder {old} of task {task.id} is not in {tree}")
    name = _target(tree, team, task)
    new = f"{team.archive_dir}/{name}"
    work.include(tree, new)                             # else git refuses a path that the checkout leaves out
    (tree / new).parent.mkdir(parents=True, exist_ok=True)
    moved = repo.git(tree, "mv", old, new)
    if moved.returncode:
        raise RuntimeError(f"git cannot move {old} to {new}: {moved.stderr.strip()[:300]}")
    work.commit(tree, f"akasha: archive the records of {task.title}")
    task.records_dir, task.records_name = team.archive_dir, name
    save(root, task)
    return True


def sync(root: Path, team: Team, task: Task) -> str:
    """Bring the records folder of the task, as Akasha keeps it, in line with git. Return a problem, or "".

    It ends a move that stopped before its commit, and it takes over a move whose commit is there while the state of
    the task still names the old folder: the landing stopped between the commit and the save, or another computer
    moved the records and the pull request still names the old folder. A change of the product is never part of it:
    then the task needs its checks again."""
    if not task.workcopy or not Path(task.workcopy).is_dir():
        return ""
    tree = Path(task.workcopy)
    start = _base(tree)
    kept = folders(tree, team, task.id, start)
    old = [folder for folder in kept if not _in(folder, team.archive_dir)]
    new = [folder for folder in kept if _in(folder, team.archive_dir)]
    if len(new) > 1 or (new and old):
        return (f"task {task.id} has more than one records folder in {tree}: {', '.join(old + new)}. Keep the records "
                "in one of them, remove the other, and commit")
    staged = repo.names(tree, "diff", "--cached", "--name-only", "--no-renames")
    if staged and not new and start:
        # The move stopped before its commit: the index holds the folder in the archive, the commit the old one
        moving = folders_of(team, staged, [task.id])
        target = [folder for folder in moving if _in(folder, team.archive_dir)]
        if target and _only_records(staged, tuple(moving)) and not repo.git(tree, "diff", "--quiet").returncode:
            work.commit(tree, f"akasha: archive the records of {task.title}")
            new = target[:1]
        elif target:
            return (f"the move of the records of task {task.id} to the archive stopped, and the work copy {tree} has "
                    f"other changes too. Run `akasha check {task.id}`: it examines the work as it is")
    if new and records(task) != new[0]:
        head = work.head(tree)
        before = repo.git(tree, "rev-parse", "-q", "--verify", "HEAD^").stdout.strip()
        only = _only_records(repo.names(tree, "diff", "--name-only", "--no-renames", "HEAD^", "HEAD") if before else [],
                             (new[0], f"{team.records_dir}/{task.id}"))
        task.records_dir, task.records_name = team.archive_dir, new[0][len(team.archive_dir.rstrip("/")) + 1:]
        if only and before in (task.checks.get("commit"), task.checks.get("landed")):
            task.checks["landed"] = head                # the commit moved only records: the checks still hold
        save(root, task)
    if new:
        work.include(tree, new[0])
    return work.restore(tree)
