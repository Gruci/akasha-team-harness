"""The steps of a task before the landing: start, preview, plan review, and checks. Also the steps between people:
resume, hand off, cancel, and ask for help."""

from __future__ import annotations

import html
import os
import time
import webbrowser
from pathlib import Path

from akasha import approval, board, checks, config, github, pr, repo, review, trace, work
from akasha.config import Team
from akasha.task import PLAN, PREVIEW, SUMMARY, Task, all_local, digest, forget, load, new_id, record, records, save

STUCK = 3                      # failed checks in a row before Akasha suggests to ask an administrator


def rules(root: Path) -> Team:
    """The team rules on the default branch as git fetched it last."""
    return config.shared(root, repo.default_branch(root))


def gate(task: Task) -> str:
    """What the task still needs before its code can change, or "" when it is ready to build."""
    if task.status == "preview" or not task.approval:
        return (f"The person did not approve its preview yet. Write the preview at {records(task)}/{PREVIEW}, "
                f"show it with `akasha preview {task.id}`, and ask the person in the chat. When their own message "
                f"approves it, run `akasha approve {task.id}` (an answer in a choice tool such as AskUserQuestion is "
                "not a message of the person).")
    if digest(record(task, PREVIEW)) != task.approval.get("preview_sha"):
        return f"The preview changed after the approval. Show it again with `akasha preview {task.id}`."
    if not review.passed(task):
        return (f"The plan did not pass the review. Write research.md and plan.md in {records(task)}/, ask the "
                f"akasha-reviewer agent to review the plan of task {task.id}, and repair the plan until it passes.")
    return ""


def next_step(task: Task) -> str:
    """The next step of the task, for the agent engine."""
    if task.status == "merged" and task.checks.get("merge"):
        return f"Wait for the deployment: `akasha land {task.id} --wait 540` (shell timeout 600000 ms)."
    if task.status in ("merged", "closed"):
        return f"The task is {task.status}."
    if task.status == "landing":
        return f"Wait for the merge: `akasha land {task.id} --wait 540` (shell timeout 600000 ms)."
    if task.status == "preview":
        if not record(task, PREVIEW).is_file():
            return (f"Ask the person what they want until it is clear. Then write the preview (an HTML mockup of "
                    f"the screen, or a diagram of the flow and the data) at {records(task)}/{PREVIEW}.")
        if not task.shown_at or digest(record(task, PREVIEW)) != task.preview_sha:
            return f"Show the preview: `akasha preview {task.id}`."
        if time.time() - task.shown_at > approval.MAX_AGE:
            return f"The person saw the preview more than a day ago. Show it again: `akasha preview {task.id}`."
        return (f"Wait for the message of the person. When it approves the preview, run `akasha approve {task.id}`; "
                "else change the preview as the person tells.")
    missing = gate(task)
    if missing:
        return missing
    tree = Path(task.workcopy)
    if work.dirty(tree) or task.checks.get("commit") != work.head(tree):
        return f"Build the change in {task.workcopy}, then run `akasha check {task.id}`."
    if not record(task, SUMMARY).is_file():
        return (f"Write {records(task)}/{SUMMARY} (why, what changed, how to undo it), run `akasha check "
                f"{task.id}` again, then `akasha land {task.id}`.")
    return f"Land the task: `akasha land {task.id} --wait 540` (shell timeout 600000 ms)."


def _name_taken(root: Path, task: Task, branch: str, entries: list[board.Entry], online: bool) -> bool:
    """True when the name of the task is in use: on this computer, on the board, on the server, or in the records of
    an earlier task of the same name."""
    if any(other.id == task.id for other in all_local(root)) or \
            repo.git(root, "rev-parse", "-q", "--verify", f"refs/heads/{task.branch}").returncode == 0:
        return True
    if any(entry.task.id == task.id or entry.branch == task.branch for entry in entries):
        return True
    return online and (repo.git(root, "ls-remote", "--exit-code", "origin", f"refs/heads/{task.branch}").returncode == 0
                       or repo.git(root, "cat-file", "-e", f"origin/{branch}:{records(task)}").returncode == 0)


def start(root: Path, title: str, name: str = "", scope: tuple[str, ...] = ()) -> tuple[Task, list[str]]:
    """Record a new task: a work copy on a new branch from the latest default branch, and a draft pull request on
    the board. Return the task and the other tasks that plan the same files."""
    team, branch = rules(root), repo.default_branch(root)
    online = board.available(root)
    if online and repo.fetch(root, branch).returncode:
        raise RuntimeError(f"git cannot fetch {branch} from origin. Examine the network and the GitHub login of git")
    task = Task(id=new_id(title, name), title=title.strip(), scope=[config.pattern(item) for item in scope],
                records_dir=team.records_dir)
    task.branch = team.branch_prefix + task.id
    entries = board.read(root) if online else []
    if entries is None:
        raise RuntimeError("gh cannot read the board. Log in to GitHub: gh auth login. Then do the step again")
    if _name_taken(root, task, branch, entries, online):
        raise ValueError(f"the name {task.id} is in use by another task, now or before. Give another name with --name")
    task.owner = (repo.me(root) if online else "") or repo.person(root, kept=False)
    path = root / team.work_dir / task.id
    work.exclude(root, team.work_dir)
    task.base = work.create(root, path, task.branch, f"origin/{branch}" if online else "HEAD")
    task.workcopy = str(path)
    record(task, PREVIEW).parent.mkdir(parents=True, exist_ok=True)
    save(root, task)
    notes = [f"overlap — {line}" for line in board.overlaps(task, [], entries)]
    risky = [item for item in task.scope if github.reviews_needed(team, [item], {task.owner})]
    if risky:
        notes.append(f"review — the task plans {', '.join(risky[:3])}: an administrator approves it "
                     "before the merge. Tell the person now")
    if online:
        pushed = ""
        try:
            # No CI run for a commit without a change: GitHub skips the workflows of a head commit with [skip ci]
            work.commit(path, f"akasha: start {task.title} [skip ci]", allow_empty=True)
            work.push(path, task.branch, adopt=False)         # rejected: another task took the name a moment ago
            pushed = work.head(path)
            task.pr = pr.create(root, task, branch)
        except RuntimeError as error:                 # undo the start, so that the same step can run again
            if pushed:                                # only the commit of this start: never the branch of another task
                repo.git(root, "push", "-q", f"--force-with-lease=refs/heads/{task.branch}:{pushed}", "origin",
                         f":refs/heads/{task.branch}", timeout=60)
            work.remove(root, path, task.branch, force=True)
            forget(root, task.id)
            if "rejected" in str(error):
                raise ValueError(f"the name {task.id} is in use by another task. Give another name with --name") \
                    from None
            raise
        task.number = pr.number(task.pr)
        save(root, task)
        pr.update(root, task)
        board.forget(root)
    return task, notes + _prepare(team, path)        # after the pull request: a slow setup does not lose the task


def _prepare(team: Team, path: Path) -> list[str]:
    """Run the setup command of the team in a new work copy, for example npm ci."""
    if not team.setup:
        return []
    status, detail = checks.shell(team.setup, path)
    return [] if status == "PASS" else [f"note — the setup command failed in the work copy: {detail[-300:]}"]


def _simple_preview(title: str, text: str) -> str:
    lines = "".join(f"<p>{html.escape(line)}</p>" for line in text.splitlines() if line.strip())
    return (f'<!doctype html><html lang="ko"><meta charset="utf-8"><title>{html.escape(title)}</title>'
            f'<body style="font-family:sans-serif;max-width:720px;margin:40px auto;line-height:1.6">'
            f"<h1>{html.escape(title)}</h1>{lines}</body></html>\n")


def preview(root: Path, task_id: str, text: str = "", show: bool = True) -> tuple[Task, str]:
    """Show the preview to the person and wait for the approval. A preview that changed after an approval needs a new
    approval. `text` makes a plain preview for a change without a screen, when the file is not there."""
    task = load(root, task_id)
    holder = taken(root, task)
    if holder:
        raise ValueError(f"@{holder} holds task {task.id} now. Run `akasha tidy` to remove the copy on this computer")
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
    # Claude Code gives its commands the session: only a message of that session, after now, approves this preview
    task.preview_sha, task.shown_at, task.shown_in = sha, time.time(), approval.session(root)
    task.heard = {}
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
                  "in plain chat whether to build it like this, or what to change. When their own message approves "
                  f"it, run `akasha approve {task.id}`. Do not ask with AskUserQuestion or another choice tool: only a "
                  "message that the person types counts.")


def approve(root: Path, task_id: str) -> tuple[Task, str]:
    """Record the approval of the person from their last message after the preview, in this session."""
    task = load(root, task_id)
    problem = approval.approve(root, task, approval.session(root))
    if problem:
        raise ValueError(problem)
    if board.available(root) and task.number:
        pr.update(root, task)
    return task, (f"Recorded the approval of {task.approval['by']}: \"{task.approval['words']}\". Do not ask the person "
                  "anything more unless the plan must change what they approved. Next, without stopping: write "
                  "research.md and plan.md in the records folder of the task, ask the akasha-reviewer agent to review "
                  "the plan until it passes, then build, run `akasha check`, write summary.md, and run `akasha land`.")


def self_review(root: Path, task_id: str, verdict: str) -> Task:
    """Record a review that the agent engine did itself, where the agent engine has no reviewer agent. The pull
    request tells that it was not the reviewer agent."""
    if os.environ.get("CLAUDECODE") == "1":
        raise ValueError("Claude Code has the akasha-reviewer agent: ask it to review the plan")
    task = load(root, task_id)
    sha = review.plan_digest(task)
    if not sha:
        raise ValueError(f"write the plan first: {record(task, PLAN)}")
    if task.review.get("source") == "reviewer" and task.review.get("plan_sha") == sha:
        raise ValueError("the reviewer agent already judged this version of the plan: repair the plan")
    review.note(root, task, verdict, sha, "self")
    return task


def check(root: Path, task_id: str, only: tuple[str, ...] = ()) -> tuple[checks.Result, list[str]]:
    """Run the checks of the team in the work copy. When each check passes, save the work as a commit and push it."""
    team, task = rules(root), load(root, task_id)
    tree = Path(task.workcopy)
    repo.git(tree, "add", "-A")          # some checks list the files with git ls-files: new files must be in the index
    before = set(work.untracked(tree))
    # The changes of the task only: after a merge of the default branch, its newer files are not changes of the task
    base = repo.git(tree, "merge-base", "HEAD", f"origin/{repo.default_branch(root)}").stdout.strip() or task.base
    changed = checks.changed_files(tree, base)
    result = checks.run(team, tree, changed, only)
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
        holder = taken(root, task)
        if holder:
            notes.append(f"note — @{holder} holds task {task.id} now, so Akasha did not push. Run `akasha tidy`")
        elif board.available(root) and task.number:
            try:
                work.push(tree, task.branch)
            except RuntimeError as error:
                notes.append(f"note — {error}. The landing pushes again")
            notes += _ask_reviews(root, team, task, changed)
            pr.update(root, task)
    save(root, task)
    return result, notes


def _ask_reviews(root: Path, team: Team, task: Task, changed: list[str]) -> list[str]:
    """Ask the administrators to review a risky change now, not only at the landing, so that they review while the work goes on."""
    asked, notes = set(task.stats.get("reviews_asked") or []), []
    for path, people, _patterns in github.reviews_needed(team, changed, {repo.me(root, kept=True), task.owner}):
        new = sorted(people - asked)
        if new and repo.gh(root, "pr", "edit", str(task.number), "--add-reviewer", ",".join(new)).returncode == 0:
            asked |= set(new)
        notes.append(f"review — the task changes {path}: {', '.join('@' + name for name in sorted(people))} approves "
                     "it before the merge. Tell the person")
    task.stats["reviews_asked"] = sorted(asked)
    return notes


def _assignees(found: dict | None) -> list[str]:
    return [str(person.get("login") or "").lower() for person in (found or {}).get("assignees") or []]


def _pull(root: Path, task: Task, fields: str) -> dict:
    """Fields of the pull request of the task, or {} without one or without an answer of GitHub."""
    if not (task.number and board.available(root)):
        return {}
    found = repo.gh_json(root, "pr", "view", str(task.number), "--json", fields, timeout=20)
    return found if isinstance(found, dict) else {}


def _holder(root: Path, found: dict) -> str:
    names = _assignees(found)
    me = repo.me(root, kept=True)
    return names[0] if names and me and me not in names else ""


def taken(root: Path, task: Task) -> str:
    """The GitHub name of another person who holds the task now, or "". Then this computer changes nothing of the
    task on GitHub: that person continues it."""
    return _holder(root, _pull(root, task, "assignees"))


def drop(root: Path, task: Task, force: bool = False, server: str = "") -> str:
    """Remove the work copy and the local branch of the task, then forget the task. Return a problem, or "".

    `server` is the head of the pull request on GitHub: the work copy stays when it has work that this head lacks,
    so that nothing that did not reach GitHub is lost. The copy and the task also stay when the session works in the
    copy, or when git cannot remove it: `akasha tidy` at the next session start, or `akasha cancel <task> --force`,
    ends them."""
    tree = Path(task.workcopy)
    if task.workcopy and tree.is_dir():
        if repo.inside(Path.cwd(), tree):
            return f"the session works in {tree}: leave that folder, then run `akasha tidy`"
        if server and (work.dirty(tree) or not work.contains(tree, server, task.number)):
            return (f"the work copy {tree} has changes that are not on GitHub. They stay there: start a new task for "
                    f"them, or drop them with `akasha cancel {task.id} --force`")
    problem = work.remove(root, tree, task.branch, force=force or bool(server)) if task.workcopy else ""
    if not problem:
        forget(root, task.id)
    board.forget(root)
    return problem


def resume(root: Path, ref: str, force: bool = False) -> tuple[Task, list[str]]:
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
    others = [name for name in entry.assignees if name != me]
    repo.gh(root, "pr", "edit", str(entry.number), "--add-assignee", "@me",
            *(item for name in others for item in ("--remove-assignee", name)))
    now = _assignees(repo.gh_json(root, "pr", "view", str(entry.number), "--json", "assignees"))
    if any(name != me for name in now) and not force:
        repo.gh(root, "pr", "edit", str(entry.number), "--remove-assignee", "@me")
        raise ValueError(f"@{next(name for name in now if name != me)} took task {entry.task.id} at the same moment")
    team, task = rules(root), entry.task
    task.number, task.pr, task.owner = entry.number, entry.url, me
    task.branch = entry.branch or task.branch
    if task.status == "preview":
        task.shown_at, task.preview_sha = 0.0, ""             # the new holder sees the preview before an approval
    if repo.fetch(root, task.branch).returncode:
        raise RuntimeError(f"git cannot fetch the branch {task.branch} of the task")
    path = root / team.work_dir / task.id
    work.exclude(root, team.work_dir)
    work.create(root, path, task.branch, f"origin/{task.branch}", new=False)
    task.workcopy = str(path)
    save(root, task)
    notes = _prepare(team, path)
    pr.update(root, task)
    board.forget(root)
    return task, notes


def _outside(task: Task) -> None:
    if task.workcopy and repo.inside(Path.cwd(), Path(task.workcopy)):
        raise ValueError(f"the session works in {task.workcopy}: leave that folder first (ExitWorktree, or cd to the "
                         "main checkout), then run the command again")


def handoff(root: Path, task_id: str) -> str:
    """Save the work on the server and free the task, so that another person or computer continues it."""
    task = load(root, task_id)
    _outside(task)
    holder = taken(root, task)
    if holder:
        raise ValueError(f"@{holder} holds task {task.id} now. Run `akasha tidy` to remove the copy on this computer")
    tree = Path(task.workcopy)
    work.commit(tree, f"akasha: handoff of {task.title}")
    work.push(tree, task.branch)
    task.owner, task.checks["handoff"] = "", work.head(tree)
    save(root, task)                                  # tidy ends what is left of a task that this computer handed off
    pr.update(root, task)
    if task.number:
        repo.gh(root, "pr", "edit", str(task.number), "--remove-assignee", "@me")
    problem = drop(root, task, server=task.checks["handoff"])
    return problem or f"handed off task {task.id}: `akasha resume {task.id}` continues it on any computer"


def cancel(root: Path, task_id: str, force: bool = False) -> str:
    """Stop a task for good: close its pull request, delete its branch, and remove the work copy. When another person
    holds the task now, only remove the copy on this computer."""
    task = load(root, task_id)
    _outside(task)
    tree = Path(task.workcopy)
    if tree.is_dir() and work.dirty(tree) and not force:
        raise ValueError(f"the work copy {tree} has changes that are not saved. Run with --force to drop them")
    found = _pull(root, task, "assignees,headRefOid")
    holder = _holder(root, found)
    if not holder:
        if task.number:
            repo.gh(root, "pr", "close", str(task.number), "--delete-branch", "--comment",
                    "Akasha: the task is cancelled.")
        return drop(root, task, force=True) or f"cancelled task {task.id}"
    problem = drop(root, task, force=True) if force else drop(root, task, server=str(found.get("headRefOid") or "?"))
    return problem or f"@{holder} holds task {task.id}: removed only the copy on this computer"


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


def ask(root: Path, text: str) -> str:
    """Ask the administrators a question that is not a change of the repository, for example about the data or the
    server, in an issue. GitHub tells them."""
    team, me = rules(root), repo.me(root)
    people = " ".join(f"@{name}" for name in team.admins)
    first = text.strip().splitlines()[0][:80] if text.strip() else "a question"
    repo.gh(root, "label", "create", config.HELP_LABEL, "--color", "d93f0b", "--description", "Waits for an admin")
    done = repo.gh(root, "issue", "create", "--label", config.HELP_LABEL, "--title", f"[akasha] {first}",
                   "--body", f"{people}\n\n{text.strip()}\n\n— asked by @{me or 'unknown'} through Akasha".strip())
    if done.returncode:
        raise RuntimeError(f"gh issue create failed: {done.stderr.strip()[:200]}")
    trace.note(root, "ask", text=text[:300])
    return f"asked {people or 'the team'}: {done.stdout.strip().splitlines()[-1] if done.stdout.strip() else ''}"


def tidy(root: Path, timeout: float = 20) -> list[str]:
    """Remove the work copies of the tasks of this computer whose pull request merged or closed, or that another
    person holds now."""
    lines = []
    for task in all_local(root):
        if task.status == "merged" and task.checks.get("merge"):
            continue                                  # the landing still follows its deployment
        if task.checks.get("handoff"):                # handed off: the work is on the server
            lines += [problem] if (problem := drop(root, task, server=task.checks["handoff"])) else []
            continue
        if not task.number:
            continue
        found = repo.gh_json(root, "pr", "view", str(task.number), "--json", "state,assignees,headRefOid",
                             timeout=timeout)
        found = found if isinstance(found, dict) else {}
        state, head = found.get("state"), str(found.get("headRefOid") or "?")
        if state in ("MERGED", "CLOSED"):
            task.status = state.lower()
            save(root, task)
            problem = drop(root, task, server=head)
            lines.append(problem or f"task {task.id} {state.lower()}: its work copy is removed")
        elif state == "OPEN" and (holder := _holder(root, found)):
            problem = drop(root, task, server=head)
            lines.append(problem or f"@{holder} holds task {task.id} now: the copy on this computer is removed")
    return lines
