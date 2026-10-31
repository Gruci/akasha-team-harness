"""The steps of a task before the landing: start, preview, plan review, and checks. Also the steps between people:
resume, hand off, cancel, and ask for help."""

from __future__ import annotations

import html
import time
import webbrowser
from pathlib import Path

from akasha import board, checks, config, pr, repo, review, trace, work
from akasha.config import Team
from akasha.task import PLAN, PREVIEW, SUMMARY, Task, all_local, digest, forget, load, new_id, record, records, save

STUCK = 3                      # failed checks in a row before Akasha suggests to ask an administrator


def rules(root: Path) -> Team:
    """The team rules on the default branch as git fetched it last."""
    return config.shared(root, repo.default_branch(root))


def gate(task: Task) -> str:
    """What the task still needs before its code can change, or "" when it is ready to build."""
    if task.status == "preview" or not task.approval:
        return (f"The person did not approve its preview yet. Write the preview at {records(task.id)}/{PREVIEW}, "
                f"show it with `akasha preview {task.id}`, and wait for the person to approve it.")
    if digest(record(task, PREVIEW)) != task.approval.get("preview_sha"):
        return f"The preview changed after the approval. Show it again with `akasha preview {task.id}`."
    if not review.passed(task):
        return (f"The plan did not pass the review. Write research.md and plan.md in {records(task.id)}/, ask the "
                f"akasha-reviewer agent to review the plan of task {task.id}, and repair the plan until it passes.")
    return ""


def next_step(task: Task) -> str:
    """The next step of the task, for the agent engine."""
    if task.status in ("merged", "closed"):
        return f"The task is {task.status}."
    if task.status == "landing":
        return f"Wait for the merge: `akasha land {task.id} --wait 540`."
    if task.status == "preview":
        if not record(task, PREVIEW).is_file():
            return (f"Ask the person what they want until it is clear. Then write the preview (an HTML mockup of "
                    f"the screen, or a diagram of the flow and the data) at {records(task.id)}/{PREVIEW}.")
        if not task.shown_at or digest(record(task, PREVIEW)) != task.preview_sha:
            return f"Show the preview: `akasha preview {task.id}`."
        return "Wait for the person to approve the preview, or change it as the person tells."
    missing = gate(task)
    if missing:
        return missing
    tree = Path(task.workcopy)
    if work.dirty(tree) or task.checks.get("commit") != work.head(tree):
        return f"Build the change in {task.workcopy}, then run `akasha check {task.id}`."
    if not record(task, SUMMARY).is_file():
        return (f"Write {records(task.id)}/{SUMMARY} (why, what changed, how to undo it), run `akasha check "
                f"{task.id}` again, then `akasha land {task.id}`.")
    return f"Land the task: `akasha land {task.id} --wait 540`."


def start(root: Path, title: str, name: str = "", scope: tuple[str, ...] = ()) -> tuple[Task, list[str]]:
    """Record a new task: a work copy on a new branch from the latest default branch, and a draft pull request on
    the board. Return the task and the other tasks that plan the same files."""
    team, branch = rules(root), repo.default_branch(root)
    online = board.available(root)
    if online and repo.fetch(root, branch).returncode:
        raise RuntimeError(f"git cannot fetch {branch} from origin. Examine the network and the GitHub login of git")
    task = Task(id=new_id(title, name), title=title.strip(), scope=[config.pattern(item) for item in scope])
    task.branch = team.branch_prefix + task.id
    if any(other.id == task.id for other in all_local(root)) or \
            repo.git(root, "rev-parse", "-q", "--verify", f"refs/heads/{task.branch}").returncode == 0:
        raise ValueError(f"a task {task.id} is already on this computer. Give another name with --name")
    entries = board.read(root) if online else []
    if entries is None:
        raise RuntimeError("gh cannot read the board. Log in to GitHub: gh auth login. Then do the step again")
    task.owner = repo.me(root) if online else repo.person(root, kept=False)
    path = root / team.work_dir / task.id
    work.exclude(root, team.work_dir)
    task.base = work.create(root, path, task.branch, f"origin/{branch}" if online else "HEAD")
    task.workcopy = str(path)
    record(task, PREVIEW).parent.mkdir(parents=True, exist_ok=True)
    save(root, task)
    notes = [f"overlap — {line}" for line in board.overlaps(task, [], entries or [])]
    if team.setup:
        status, detail = checks.shell(team.setup, path)
        if status != "PASS":
            notes.append(f"note — the setup command failed in the work copy: {detail[-300:]}")
    if online:
        work.commit(path, f"akasha: start {task.title}", allow_empty=True)
        work.push(path, task.branch)
        task.pr = pr.create(root, task, branch)
        task.number = pr.number(task.pr)
        save(root, task)
        pr.update(root, task)
        board.forget(root)
    return task, notes


def _simple_preview(title: str, text: str) -> str:
    lines = "".join(f"<p>{html.escape(line)}</p>" for line in text.splitlines() if line.strip())
    return (f'<!doctype html><html lang="ko"><meta charset="utf-8"><title>{html.escape(title)}</title>'
            f'<body style="font-family:sans-serif;max-width:720px;margin:40px auto;line-height:1.6">'
            f"<h1>{html.escape(title)}</h1>{lines}</body></html>\n")


def preview(root: Path, task_id: str, text: str = "", show: bool = True) -> tuple[Task, str]:
    """Show the preview to the person and wait for the approval. A preview that changed after an approval needs a new
    approval. `text` makes a plain preview for a change without a screen, when the file is not there."""
    task = load(root, task_id)
    path = record(task, PREVIEW)
    if text and not path.is_file():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_simple_preview(task.title, text), encoding="utf-8")
    if not path.is_file():
        raise ValueError(f"write the preview first: {path}")
    sha = digest(path)
    changed = bool(task.approval) and task.approval.get("preview_sha") != sha
    if changed:
        task.approval, task.status = {}, "preview"
    task.preview_sha, task.shown_at = sha, time.time()
    save(root, task)
    if board.available(root) and task.number:
        work.commit(Path(task.workcopy), f"akasha: preview of {task.title}")
        try:
            work.push(Path(task.workcopy), task.branch)
        except RuntimeError:
            pass                                      # the next push sends it
        pr.update(root, task)
    if show:
        webbrowser.open(path.resolve().as_uri())
    again = " The preview changed after the approval, so the person approves it again." if changed else ""
    return task, (f"Showed {path} in the browser.{again} Tell the person in simple words what they see, and ask them "
                  "to approve it or to tell what to change. Only their own message approves it: Akasha records it.")


def self_review(root: Path, task_id: str, verdict: str) -> Task:
    """Record a review that the agent engine did itself, where the agent engine has no reviewer agent. The pull
    request tells that it was not the reviewer agent."""
    task = load(root, task_id)
    sha = review.plan_digest(task)
    if not sha:
        raise ValueError(f"write the plan first: {record(task, PLAN)}")
    review.note(root, task, verdict, sha, "self")
    return task


def check(root: Path, task_id: str, only: tuple[str, ...] = ()) -> tuple[checks.Result, list[str]]:
    """Run the checks of the team in the work copy. When each check passes, save the work as a commit and push it."""
    team, task = rules(root), load(root, task_id)
    tree = Path(task.workcopy)
    before = set(work.untracked(tree))
    result = checks.run(team, tree, checks.changed_files(tree, task.base), only)
    notes = []
    made = sorted(set(work.untracked(tree)) - before)
    if made:                                          # for example __pycache__ of the tests: never into a commit
        work.exclude_files(root, made)
        notes.append(f"note — the checks made files that git does not ignore: {', '.join(made[:5])}. Akasha keeps "
                     "them out of the commits on this computer. Add their pattern to .gitignore in this task")
    failed = [name for name, status in result.status.items() if status == "FAIL"]
    if failed:
        task.failures += 1
        counts = task.stats.setdefault("check_failures", {})
        for name in failed:
            counts[name] = counts.get(name, 0) + 1
            trace.note(root, "check_failed", task=task.id, check=name, detail=result.details[name][-300:])
        if task.failures >= STUCK:
            notes.append(f"{task.failures} failed checks in a row. If the cause is not in this task, ask an "
                         f"administrator: `akasha help {task.id} \"<what blocks you>\"`")
    elif checks.passed(result.status) and not only:
        work.commit(tree, task.title)
        task.failures = 0
        task.checks = {"status": result.status, "commit": work.head(tree), "at": time.strftime("%Y-%m-%d %H:%M")}
        if board.available(root) and task.number:
            try:
                work.push(tree, task.branch)
            except RuntimeError as error:
                notes.append(f"note — {error}. The landing pushes again")
    save(root, task)
    if task.number and checks.passed(result.status) and not only:
        pr.update(root, task)
    return result, notes


def resume(root: Path, ref: str, force: bool = False) -> Task:
    """Continue a task of the board on this computer: the person who held it handed it off, or `force` when that
    person agrees or is gone. The work copy starts from the branch on the server."""
    entries = board.read(root)
    if entries is None:
        raise RuntimeError("gh cannot read the board. Log in to GitHub: gh auth login")
    wanted = ref.lstrip("#")
    entry = next((item for item in entries if wanted in (item.task.id, str(item.number))), None)
    if entry is None:
        raise LookupError(f"no open task {ref} on the board. `akasha board` shows the open tasks")
    me = repo.me(root)
    if entry.assignees and me not in entry.assignees and not force:
        raise ValueError(f"@{entry.holder} holds task {entry.task.id}. Ask them to run `akasha handoff "
                         f"{entry.task.id}`. If they agree or are gone, run `akasha resume {ref} --force`")
    if any(task.id == entry.task.id and task.workcopy for task in all_local(root)):
        raise ValueError(f"task {entry.task.id} is already on this computer")
    team, task = rules(root), entry.task
    task.number, task.pr, task.owner = entry.number, entry.url, me
    task.branch = entry.branch or task.branch
    if repo.fetch(root, task.branch).returncode:
        raise RuntimeError(f"git cannot fetch the branch {task.branch} of the task")
    path = root / team.work_dir / task.id
    work.exclude(root, team.work_dir)
    work.create(root, path, task.branch, f"origin/{task.branch}", new=False)
    task.workcopy = str(path)
    save(root, task)
    others = [name for name in entry.assignees if name != me]
    repo.gh(root, "pr", "edit", str(task.number), "--add-assignee", "@me",
            *(item for name in others for item in ("--remove-assignee", name)))
    pr.update(root, task)
    board.forget(root)
    return task


def handoff(root: Path, task_id: str) -> str:
    """Save the work on the server and free the task, so that another person or computer continues it."""
    task = load(root, task_id)
    tree = Path(task.workcopy)
    work.commit(tree, f"akasha: handoff of {task.title}")
    work.push(tree, task.branch)
    task.owner = ""
    pr.update(root, task)
    if task.number:
        repo.gh(root, "pr", "edit", str(task.number), "--remove-assignee", "@me")
    problem = work.remove(root, tree, task.branch)
    forget(root, task.id)
    board.forget(root)
    return problem or f"handed off task {task.id}: `akasha resume {task.id}` continues it on any computer"


def cancel(root: Path, task_id: str, force: bool = False) -> str:
    """Stop a task for good: close its pull request, delete its branch, and remove the work copy."""
    task = load(root, task_id)
    tree = Path(task.workcopy)
    if tree.is_dir() and work.dirty(tree) and not force:
        raise ValueError(f"the work copy {tree} has changes that are not saved. Run with --force to drop them")
    if task.number:
        repo.gh(root, "pr", "close", str(task.number), "--delete-branch", "--comment", "Akasha: the task is cancelled.")
    problem = work.remove(root, tree, task.branch, force=True)
    forget(root, task.id)
    board.forget(root)
    return problem or f"cancelled task {task.id}"


def ask_help(root: Path, task_id: str, text: str) -> str:
    """Ask the administrators on the pull request of the task. GitHub tells them."""
    team, task = rules(root), load(root, task_id)
    if not task.number:
        raise ValueError("the task has no pull request: tell an administrator yourself")
    people = " ".join(f"@{name}" for name in team.admins)
    repo.gh(root, "label", "create", config.HELP_LABEL, "--color", "d93f0b", "--description", "Waits for an admin")
    repo.gh(root, "pr", "edit", str(task.number), "--add-label", config.HELP_LABEL)
    done = repo.gh(root, "pr", "comment", str(task.number), "--body",
                   f"{people} Akasha: task `{task.id}` needs help. {text.strip()}".strip())
    if done.returncode:
        raise RuntimeError(f"gh pr comment failed: {done.stderr.strip()[:200]}")
    trace.note(root, "help", task=task.id, text=text[:300])
    return f"asked {people or 'the team'} on {task.pr}"


def tidy(root: Path) -> list[str]:
    """Remove the work copies of the tasks of this computer whose pull request merged or closed."""
    lines = []
    for task in all_local(root):
        if not task.number:
            continue
        found = repo.gh_json(root, "pr", "view", str(task.number), "--json", "state", timeout=20)
        state = (found or {}).get("state")
        if state not in ("MERGED", "CLOSED"):
            continue
        problem = work.remove(root, Path(task.workcopy), task.branch, force=state == "MERGED")
        forget(root, task.id)
        lines.append(problem or f"task {task.id} {state.lower()}: its work copy is removed")
    if lines:
        board.forget(root)
    return lines
