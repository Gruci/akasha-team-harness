"""The landing of a task: bring it up to date with the default branch, make the pull request ready, and merge it
when the checks of the team pass on GitHub.

Where GitHub protects the default branch (server rules "github"), GitHub merges with its auto-merge, as the person
who turned it on, so the workflows after a merge start, for example a deployment. Where it does not, for example a
private repository on GitHub Free (server rules "akasha"), Akasha merges on this computer with the account of the
person, after the same examination. In both cases Akasha brings a pull request that is behind up to date, because
GitHub does not do it."""

from __future__ import annotations

import time
from pathlib import Path

from akasha import board, pr, repo, trace, work
from akasha.checks import matches
from akasha.config import Team
from akasha.flow import gate, rules
from akasha.task import SUMMARY, Task, forget, load, record, records, save

POLL_SECONDS = 15
FAILED = {"FAILURE", "TIMED_OUT", "CANCELLED", "ERROR", "ACTION_REQUIRED", "STARTUP_FAILURE"}
PASSED = {"SUCCESS", "NEUTRAL"}
# The results of a landing. MERGED and CLOSED end it. WAITING asks for one more `akasha land <task> --wait`.
MERGED, CLOSED, WAITING, FAILED_CHECK, CONFLICT, REVIEW, BLOCKED = (
    "MERGED", "CLOSED", "WAITING", "FAILED", "CONFLICT", "REVIEW", "BLOCKED")


def _ready(task: Task) -> str:
    """What stops the landing, or ""."""
    missing = gate(task)
    if missing:
        return missing
    tree = Path(task.workcopy)
    if work.dirty(tree) or task.checks.get("commit") != work.head(tree):
        return f"the checks did not pass on the current work. Run `akasha check {task.id}` first"
    if not record(task, SUMMARY).is_file():
        return f"write {records(task.id)}/{SUMMARY} first: why, what changed, and how to undo it"
    return ""


def _risky(team: Team, task: Task, branch: str) -> list[str]:
    changed = repo.names(Path(task.workcopy), "diff", "--name-only", "--no-renames", f"origin/{branch}...HEAD")
    return [path for path in changed if any(matches(path, item) for item in team.risk_paths)]


def land(root: Path, task_id: str, wait: float = 0) -> tuple[str, list[str]]:
    """Land the task, then wait up to `wait` seconds for the merge."""
    team, task = rules(root), load(root, task_id)
    told: list[str] = []
    if task.status != "landing":
        problem = _ready(task)
        if problem:
            return BLOCKED, [problem]
        if not board.available(root) or not task.number:
            return BLOCKED, ["Akasha lands a task through its pull request on GitHub, and this task has none"]
        state, told = _hand_over(root, team, task)
        if state:
            return state, told
    state, lines = follow(root, team, load(root, task_id), wait)
    return state, told + lines


def _hand_over(root: Path, team: Team, task: Task) -> tuple[str, list[str]]:
    tree, branch = Path(task.workcopy), repo.default_branch(root)
    repo.fetch(root, branch)
    work.pull(tree, task.branch)
    merged = repo.git(tree, "merge", "-q", "--no-edit", f"origin/{branch}")
    if merged.returncode:
        repo.git(tree, "merge", "--abort")
        return CONFLICT, [f"the task conflicts with the latest {branch}. In {tree}, run `git merge origin/{branch}`, "
                          f"repair the conflicts, run `akasha check {task.id}`, then land again"]
    work.push(tree, task.branch)
    task.status = "landing"
    save(root, task)
    pr.update(root, task)
    repo.gh(root, "pr", "ready", str(task.number))
    lines = []
    risky = _risky(team, task, branch)
    me = repo.me(root)
    reviewers = [name for name in team.reviewers if name != me]
    if risky and reviewers:
        repo.gh(root, "pr", "edit", str(task.number), "--add-reviewer", ",".join(reviewers))
        lines.append(f"the task changes {', '.join(risky[:3])}: it waits for the review of "
                     f"{', '.join('@' + name for name in reviewers)}")
    if team.server_rules == "github":
        done = repo.gh(root, "pr", "merge", str(task.number), "--auto", "--squash", "--subject",
                       f"{task.title} (#{task.number})", "--body", pr.commit_body(task))
        if done.returncode and "already" not in done.stderr.lower():
            lines.append(f"GitHub did not turn on auto-merge: {done.stderr.strip()[:200]}. An administrator runs "
                         "`akasha setup --apply`")
    board.forget(root)
    return "", lines


def _result(item: dict) -> str:
    """One run of a check: RAN (it passed), SKIPPED, FAIL, or WAIT."""
    result = (item.get("conclusion") or item.get("state") or "").upper()
    if (item.get("status") or "COMPLETED").upper() != "COMPLETED" or result in ("", "PENDING", "EXPECTED"):
        return "WAIT"
    if result == "SKIPPED":
        return "SKIPPED"
    return "RAN" if result in PASSED else "FAIL" if result in FAILED else "WAIT"


def _states(view: dict, names: tuple[str, ...]) -> dict[str, str]:
    """The state of each required check of the team on the head of the pull request: PASS, FAIL, or WAIT.

    One check can have several runs on the head: a run that a draft skipped, and the run after the pull request got
    ready. A failure or a run that did not end decides first. A check passes only when one run really ran and passed:
    a skipped run alone is the draft, and the real run has not started yet."""
    runs: dict[str, set[str]] = {}
    for item in view.get("statusCheckRollup") or []:
        name = item.get("name") or item.get("context") or ""
        if name in names:
            runs.setdefault(name, set()).add(_result(item))
    states = {}
    for name in names:
        found = runs.get(name, set())
        states[name] = "FAIL" if "FAIL" in found else "WAIT" if "WAIT" in found or "RAN" not in found else "PASS"
    return states


def _behind(root: Path, view: dict) -> int:
    slug = repo.origin(root)
    found = repo.gh_json(root, "api", f"repos/{slug}/compare/{view.get('baseRefName')}...{view.get('headRefOid')}")
    return int((found or {}).get("behind_by") or 0)


def _finish(root: Path, task: Task, state: str) -> list[str]:
    problem = work.remove(root, Path(task.workcopy), task.branch, force=state == MERGED)
    forget(root, task.id)
    board.forget(root)
    done = f"task {task.id} {state.lower()}: {task.pr}"
    return [done] + ([problem] if problem else [])


def _risky_files(root: Path, team: Team, task: Task) -> bool:
    if not team.risk_paths:
        return False
    files = repo.gh_json(root, "pr", "view", str(task.number), "--json", "files") or {}
    return any(matches(item.get("path", ""), pattern) for item in files.get("files") or [] for pattern in team.risk_paths)


def follow(root: Path, team: Team, task: Task, wait: float) -> tuple[str, list[str]]:
    """Watch the pull request until it merges, a check fails, it conflicts, or `wait` seconds pass."""
    deadline = time.monotonic() + max(wait, 0)
    while True:
        view = pr.view(root, task)
        if view is None:
            return WAITING, ["gh did not answer. Run the landing again later"]
        state = view.get("state")
        if state in (MERGED, CLOSED):
            return state, _finish(root, task, state)
        if view.get("mergeStateStatus") == "DIRTY":
            return CONFLICT, [f"the pull request conflicts with the latest {view.get('baseRefName')}. Run `akasha "
                              f"land {task.id}` after you merge it in the work copy: `git merge "
                              f"origin/{view.get('baseRefName')}`, repair, `akasha check {task.id}`"]
        states = _states(view, team.status_checks)
        failed = [name for name, value in states.items() if value == "FAIL"]
        if failed:
            trace.note(root, "server_check_failed", task=task.id, checks=failed)
            task.status = "approved"
            save(root, task)
            return FAILED_CHECK, [f"the check {', '.join(failed)} failed on GitHub: {view.get('url')}/checks. Repair "
                                  f"it in the work copy, run `akasha check {task.id}`, then land again"]
        if _behind(root, view):
            repo.gh(root, "pr", "update-branch", str(task.number))
            trace.note(root, "brought_up_to_date", task=task.id)
        elif all(value == "PASS" for value in states.values()):
            review = view.get("reviewDecision") or ""
            if review == "CHANGES_REQUESTED" or (review == "REVIEW_REQUIRED" and team.server_rules == "github"):
                return REVIEW, [f"the pull request waits for a review: {view.get('url')}"]
            if team.server_rules == "akasha":
                if _risky_files(root, team, task) and team.reviewers and review != "APPROVED":
                    return REVIEW, [f"the pull request changes a risky path and waits for the review of "
                                    f"{', '.join('@' + name for name in team.reviewers)}: {view.get('url')}"]
                done = repo.gh(root, "pr", "merge", str(task.number), "--squash", "--match-head-commit",
                               str(view.get("headRefOid")), "--subject", f"{task.title} (#{task.number})",
                               "--body", pr.commit_body(task))
                if done.returncode == 0:
                    return MERGED, _finish(root, task, MERGED)
        if time.monotonic() >= deadline:
            return WAITING, [f"the checks of GitHub still run. Run `akasha land {task.id} --wait 540` again"]
        time.sleep(POLL_SECONDS)
