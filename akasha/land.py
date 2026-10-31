"""The landing of a task: bring it up to date with the default branch, make the pull request ready, and merge it
when the checks of the team pass on GitHub.

Where GitHub protects the default branch, GitHub merges with its auto-merge, as the person who turned it on, so the
workflows after a merge start, for example a deployment. Where it does not, for example a private repository on
GitHub Free, Akasha merges on this computer with the account of the person, after the same examination: the required
checks passed on the current head, the branch is up to date, and a reviewer or an administrator approved a change of
a risky path or of the rules of the team. Akasha asks GitHub before each landing whether it protects the branch, so a
missing or old [server] rules never sends a merge to an auto-merge that nothing stops. In both cases Akasha brings a
pull request that is behind up to date, because GitHub does not do it. With [deploy] workflow, the landing then
waits for that deployment, because the change is live only after it."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

from akasha import board, github, pr, repo, trace, work
from akasha.config import Team
from akasha.flow import drop, gate, rules, taken
from akasha.task import SUMMARY, Task, load, record, records, save

POLL_SECONDS = 15
DEPLOY_GRACE = 120             # seconds after the merge before Akasha decides that no deployment started
FAILED = {"FAILURE", "TIMED_OUT", "ERROR", "ACTION_REQUIRED", "STARTUP_FAILURE"}
PASSED = {"SUCCESS", "NEUTRAL"}
QUEUED = ("QUEUED", "PENDING", "WAITING", "REQUESTED")
_RUN = re.compile(r"/actions/runs/(\d+)")
# The results of a landing. WAITING and DEPLOYING ask for one more `akasha land <task> --wait`.
MERGED, CLOSED, WAITING, FAILED_CHECK, CONFLICT, REVIEW, BLOCKED = (
    "MERGED", "CLOSED", "WAITING", "FAILED", "CONFLICT", "REVIEW", "BLOCKED")
DEPLOYED, DEPLOY_FAILED, DEPLOYING = "DEPLOYED", "DEPLOY_FAILED", "DEPLOYING"
AGAIN = "Run `akasha land {task} --wait 540` again (shell timeout 600000 ms)"


def _ready(task: Task) -> str:
    """What stops the landing, or ""."""
    missing = gate(task)
    if missing:
        return missing
    if _moved(task):
        return f"the checks did not pass on the current work. Run `akasha check {task.id}` first"
    if not record(task, SUMMARY).is_file():
        return f"write {records(task)}/{SUMMARY} first: why, what changed, and how to undo it"
    return ""


def _moved(task: Task) -> bool:
    """True when the work copy changed after the checks passed (or after the landing merged the default branch)."""
    tree = Path(task.workcopy)
    return work.dirty(tree) or work.head(tree) not in (task.checks.get("commit"), task.checks.get("landed"))


def land(root: Path, task_id: str, wait: float = 0) -> tuple[str, list[str]]:
    """Land the task, then wait up to `wait` seconds for the merge (and the deployment)."""
    team, task = rules(root), load(root, task_id)
    deadline = time.monotonic() + max(wait, 0)
    if task.status == "merged" and task.checks.get("merge"):
        return _deploy(root, team, task, deadline)
    if not board.available(root) or not task.number:
        return BLOCKED, ["Akasha lands a task through its pull request on GitHub, and this task has none. Run "
                         f"`akasha cancel {task.id}`, then start the task again"]
    holder = taken(root, task)
    if holder:
        return BLOCKED, [f"@{holder} holds task {task.id} now. Run `akasha tidy` to remove the copy on this computer"]
    # No answer from GitHub is no protection: then Akasha merges itself, after its own examination
    akasha_merges = team.server_rules == "akasha" or not github.protected(root, team)
    told: list[str] = []
    if task.status != "landing":
        problem = _ready(task)
        if problem:
            return BLOCKED, [problem]
        state, told = _hand_over(root, team, task, akasha_merges)
        if state:
            return state, told
    state, lines = follow(root, team, load(root, task_id), deadline, akasha_merges)
    return state, told + lines


def _hand_over(root: Path, team: Team, task: Task, akasha_merges: bool) -> tuple[str, list[str]]:
    view = pr.view(root, task)
    if view is None:
        return WAITING, ["gh did not answer. " + AGAIN.format(task=task.id)]
    if view.get("state") != "OPEN":
        return "", []                                 # merged or closed on GitHub: follow ends the task
    tree, branch = Path(task.workcopy), repo.default_branch(root)
    repo.fetch(root, branch)
    work.pull(tree, task.branch)
    merged = repo.git(tree, "merge", "-q", "--no-edit", f"origin/{branch}")
    if merged.returncode:
        repo.git(tree, "merge", "--abort")
        return CONFLICT, [f"the task conflicts with the latest {branch}. In {tree}, run `git merge origin/{branch}`, "
                          f"repair the conflicts, run `akasha check {task.id}`, then land again"]
    repo.gh(root, "pr", "ready", str(task.number))        # first, so that the run of the push is a real run
    work.push(tree, task.branch)
    task.status = "landing"
    task.checks["landed"] = work.head(tree)
    save(root, task)
    pr.update(root, task)
    lines = []
    files = repo.names(tree, "diff", "--name-only", "--no-renames", f"origin/{branch}...HEAD")
    authors = {repo.me(root), str(task.owner), str((view.get("author") or {}).get("login") or "").lower()}
    for path, people in github.reviews_needed(team, files, authors):
        repo.gh(root, "pr", "edit", str(task.number), "--add-reviewer", ",".join(sorted(people)))
        lines.append(f"the task changes {path}: it waits for the review of {_names(people)}")
    if not akasha_merges:
        lines += _auto_merge(root, task)
    board.forget(root)
    return "", lines


def _auto_merge(root: Path, task: Task) -> list[str]:
    done = repo.gh(root, "pr", "merge", str(task.number), "--auto", "--squash", "--subject",
                   f"{task.title} (#{task.number})", "--body", pr.commit_body(task))
    if done.returncode and "already" not in done.stderr.lower():
        return [f"GitHub did not turn on auto-merge: {done.stderr.strip()[:200]}. An administrator runs "
                "`akasha setup --apply`"]
    return []


def _names(people: set[str]) -> str:
    return ", ".join(f"@{name}" for name in sorted(people))


def _result(item: dict) -> str:
    """One run of a check: RAN (it passed), SKIPPED, CANCELLED, FAIL, or WAIT."""
    result = (item.get("conclusion") or item.get("state") or "").upper()
    if (item.get("status") or "COMPLETED").upper() != "COMPLETED" or result in ("", "PENDING", "EXPECTED"):
        return "WAIT"
    if result in ("SKIPPED", "CANCELLED"):
        return result
    return "RAN" if result in PASSED else "FAIL" if result in FAILED else "WAIT"


def _states(view: dict, names: tuple[str, ...]) -> dict[str, str]:
    """The state of each required check of the team on the head of the pull request: PASS, FAIL, CANCELLED, WAIT, or
    MISSING (no run of that name).

    One check can have several runs on the head: a run that a draft skipped, a run that a newer run cancelled, and a
    run again. A run that did not end decides first. Else the latest run that did not skip decides, as on GitHub. A
    skipped run alone is the draft: the real run has not started yet."""
    runs: dict[str, list[tuple[str, str]]] = {}
    for item in view.get("statusCheckRollup") or []:
        name = item.get("name") or item.get("context") or ""
        if name in names:
            runs.setdefault(name, []).append((str(item.get("startedAt") or ""), _result(item)))
    states = {}
    for name in names:
        found = runs.get(name)
        done = [run for run in found or [] if run[1] not in ("WAIT", "SKIPPED")]
        if not found:
            states[name] = "MISSING"
        elif any(result == "WAIT" for _start, result in found) or not done:
            states[name] = "WAIT"
        else:
            latest = sorted(done, key=lambda run: run[0])[-1][1]
            states[name] = "PASS" if latest == "RAN" else latest
    return states


def _behind(root: Path, view: dict) -> int:
    """How many commits of the default branch the pull request lacks, or -1 when GitHub does not tell."""
    found = repo.gh_json(root, "api", f"repos/{repo.origin(root)}/compare/{view.get('baseRefName')}..."
                         f"{view.get('headRefOid')}")
    if not isinstance(found, dict) or "behind_by" not in found:
        return -1
    return int(found["behind_by"])


def _rerun(root: Path, task: Task, view: dict, names: list[str]) -> bool:
    """Start a cancelled check again, once for each head. False when it was started again already."""
    head = str(view.get("headRefOid") or "")
    if task.checks.get("rerun") == head:
        return False
    for item in view.get("statusCheckRollup") or []:
        found = _RUN.search(str(item.get("detailsUrl") or ""))
        if (item.get("name") or "") in names and _result(item) == "CANCELLED" and found:
            repo.gh(root, "run", "rerun", found.group(1))
    task.checks["rerun"] = head
    save(root, task)
    return True


def _failed(root: Path, task: Task, view: dict, failed: list[str], cancelled: bool) -> tuple[str, list[str]]:
    trace.note(root, "server_check_failed", task=task.id, checks=failed)
    counts = task.stats.setdefault("server_check_failures", {})
    for name in failed:
        counts[name] = counts.get(name, 0) + 1
    task.status = "approved"
    save(root, task)
    if cancelled:
        return FAILED_CHECK, [f"the check {', '.join(failed)} was cancelled on GitHub again: {view.get('url')}/checks. "
                              f"Ask an administrator: `akasha help {task.id} \"<the check was cancelled>\"`"]
    return FAILED_CHECK, [f"the check {', '.join(failed)} failed on GitHub: {view.get('url')}/checks. Repair it in "
                          f"the work copy, run `akasha check {task.id}`, then land again"]


def _files(root: Path, number: int) -> list[str] | None:
    """Each file that the pull request changes, also beyond the first 100, or None when GitHub does not answer."""
    done = repo.gh(root, "api", "--paginate", f"repos/{repo.origin(root)}/pulls/{number}/files?per_page=100",
                   "--jq", ".[].filename")
    return None if done.returncode else [line for line in done.stdout.splitlines() if line.strip()]


def _waiting_review(root: Path, team: Team, task: Task, view: dict) -> tuple[str, set[str]]:
    """Who must still approve the pull request, or nobody. "CHANGES" when one of them asked for changes, "WAIT" also
    when GitHub did not list the files."""
    files = _files(root, task.number)
    if files is None:
        return "WAIT", set()
    authors = {str((view.get("author") or {}).get("login") or "").lower(), repo.me(root), str(task.owner)}
    needs = github.reviews_needed(team, files, authors)
    if not needs:
        return "", set()
    states = github.review_states(repo.gh_json(root, "api", f"repos/{repo.origin(root)}/pulls/{task.number}/"
                                               "reviews?per_page=100"))
    for _path, people in needs:
        if any(states.get(name) == "CHANGES_REQUESTED" for name in people):
            return "CHANGES", people
        if not any(states.get(name) == "APPROVED" for name in people):
            return "WAIT", people
    return "", set()


def _merge(root: Path, task: Task, view: dict) -> str:
    """Merge the pull request at its current head. "" when it merged, "later" when GitHub asks to try again (the head
    moved, or GitHub still computes whether it can merge), else the error."""
    done = repo.gh(root, "pr", "merge", str(task.number), "--squash", "--match-head-commit",
                   str(view.get("headRefOid")), "--subject", f"{task.title} (#{task.number})",
                   "--body", pr.commit_body(task))
    if done.returncode == 0:
        return ""
    error = done.stderr.strip()
    return "later" if any(word in error.lower() for word in ("head", "mergeable", "try again")) else \
        error[:200] or "gh failed"


def follow(root: Path, team: Team, task: Task, deadline: float, akasha_merges: bool) -> tuple[str, list[str]]:
    """Watch the pull request until it merges, a check fails, it conflicts, or the deadline passes."""
    tree = Path(task.workcopy)
    while True:
        view = pr.view(root, task)
        if view is None:
            return WAITING, ["gh did not answer. " + AGAIN.format(task=task.id)]
        state, head, waiting_for = view.get("state"), str(view.get("headRefOid") or ""), set()
        if state in (MERGED, CLOSED):
            return _finish(root, team, task, state, view, deadline)
        if _moved(task):                              # for example an edit while the landing waits in the background
            task.status = "approved"
            save(root, task)
            return BLOCKED, [f"the work copy changed after the checks. Run `akasha check {task.id}`, then land again"]
        if view.get("isDraft"):
            done = repo.gh(root, "pr", "ready", str(task.number))
            if done.returncode:
                return WAITING, [f"GitHub did not make the pull request ready: {done.stderr.strip()[:200]}. "
                                 + AGAIN.format(task=task.id)]
        if view.get("mergeStateStatus") == "DIRTY":
            task.status = "approved"
            save(root, task)
            return CONFLICT, [f"the pull request conflicts with the latest {view.get('baseRefName')}. Run `akasha land "
                              f"{task.id}` again: it brings the latest {view.get('baseRefName')} into the work copy "
                              "and names the files"]
        states = _states(view, team.status_checks)
        failed = [name for name, value in states.items() if value == "FAIL"]
        cancelled = [name for name, value in states.items() if value == "CANCELLED"]
        if cancelled and not _rerun(root, task, view, cancelled):
            return _failed(root, task, view, cancelled, cancelled=True)
        if failed:
            return _failed(root, task, view, failed, cancelled=False)
        if not work.contains(tree, head, task.number):            # the checked work has commits that GitHub lacks
            work.push(tree, task.branch)
        else:
            behind = _behind(root, view)
            if behind > 0:
                repo.gh(root, "pr", "update-branch", str(task.number))
                trace.note(root, "brought_up_to_date", task=task.id)
            elif behind == 0 and all(value == "PASS" for value in states.values()):
                review, waiting_for = _waiting_review(root, team, task, view)
                if review == "CHANGES" or view.get("reviewDecision") == "CHANGES_REQUESTED":
                    task.status = "approved"
                    save(root, task)
                    return REVIEW, [f"a reviewer asked for changes: {view.get('url')}. Read the review, repair the "
                                    f"work, run `akasha check {task.id}`, then land again"]
                if akasha_merges and not review and view.get("mergeStateStatus") != "UNKNOWN":
                    error = _merge(root, task, view)
                    if not error:
                        return _finish(root, team, task, MERGED, {**view, "state": MERGED}, deadline)
                    if error != "later":
                        return BLOCKED, [f"gh could not merge: {error}"]
                elif not akasha_merges and not view.get("autoMergeRequest"):
                    _auto_merge(root, task)
        if time.monotonic() >= deadline:
            return _late(task, view, states, waiting_for)
        time.sleep(POLL_SECONDS)


def _late(task: Task, view: dict, states: dict[str, str], waiting_for: set[str]) -> tuple[str, list[str]]:
    """The result when the deadline passed: what the landing waits for."""
    again = AGAIN.format(task=task.id)
    if waiting_for or view.get("reviewDecision") == "REVIEW_REQUIRED":
        who = _names(waiting_for) if waiting_for else "a code owner"
        return REVIEW, [f"the pull request waits for the review of {who}: {view.get('url')}. After the review, "
                        f"{again[0].lower()}{again[1:]}"]
    rollup = view.get("statusCheckRollup") or []
    missing = [name for name, value in states.items() if value == "MISSING"]
    if missing:
        ran = sorted({str(item.get("name") or item.get("context") or "") for item in rollup} - {""})
        return WAITING, [f"no check named {', '.join(missing)} ran on this pull request yet (checks that ran: "
                         f"{', '.join(ran) or 'none'}). If it stays so, an administrator corrects [ci] required in "
                         "akasha.toml: use the name of the job, for example \"checks\", not the name of the workflow. "
                         + again]
    queued = sorted({str(item.get("name") or "") for item in rollup if (item.get("name") or "") in states
                     and str(item.get("status") or "").upper() in QUEUED})
    if queued:
        return WAITING, [f"{', '.join(queued)} waits for a runner of GitHub. If it waits long, ask an administrator: "
                         f"`akasha help {task.id} \"<the check waits for a runner>\"`. " + again]
    return WAITING, ["the checks of GitHub still run. " + again]


def _finish(root: Path, team: Team, task: Task, state: str, view: dict, deadline: float) -> tuple[str, list[str]]:
    task.status, task.checks["head"] = state.lower(), str(view.get("headRefOid") or "?")
    save(root, task)
    problem = drop(root, task, server=task.checks["head"])
    lines = [f"task {task.id} {state.lower()}: {task.pr}"] + ([problem] if problem else [])
    if state != MERGED or not team.deploy_workflow:
        return state, lines
    if not view.get("mergeCommit"):                   # Akasha merged it a moment ago
        view = pr.view(root, task) or view
    merge = str((view.get("mergeCommit") or {}).get("oid") or "")
    if not merge:
        return state, lines + ["GitHub did not tell the merge commit, so Akasha cannot follow the deployment"]
    task.checks.update({"merge": merge, "merged_at": time.time()})
    save(root, task)
    deployed, more = _deploy(root, team, task, deadline)
    return deployed, lines + more


def _deploy(root: Path, team: Team, task: Task, deadline: float) -> tuple[str, list[str]]:
    """Wait for the run of the deployment workflow on the merge commit."""
    while True:
        done = repo.gh(root, "run", "list", "--workflow", team.deploy_workflow, "--commit",
                       str(task.checks.get("merge")), "--json", "status,conclusion,url", "--limit", "5")
        try:
            runs = json.loads(done.stdout or "null") if done.returncode == 0 else None
        except ValueError:
            runs = None
        latest = runs[0] if isinstance(runs, list) and runs else None
        late = time.time() - float(task.checks.get("merged_at") or 0) > DEPLOY_GRACE
        done_now = bool(latest) and str(latest.get("status") or "").lower() == "completed"
        if done_now or (late and not latest):
            task.checks.pop("merge", None)            # the task is an ended merged task again
            save(root, task)
            drop(root, task, server=str(task.checks.get("head") or "?"))
        if done_now:
            if str(latest.get("conclusion") or "").lower() == "success":
                return DEPLOYED, [f"the deployment put the change live: {latest.get('url')}"]
            return DEPLOY_FAILED, [f"the deployment failed: {latest.get('url')}. Tell the person, and ask an "
                                   f"administrator: `akasha help {task.id} \"<the deployment failed>\"`"]
        if late and not latest:
            if runs is None:
                return MERGED, [f"Akasha cannot read the runs of the workflow {team.deploy_workflow}: "
                                f"{done.stderr.strip()[:200]}. Tell an administrator to correct [deploy] workflow"]
            return MERGED, ["no deployment started for this change (the deployment workflow skipped it): it needs "
                            "none"]
        if time.monotonic() >= deadline:
            return DEPLOYING, ["the deployment still runs. " + AGAIN.format(task=task.id)]
        time.sleep(POLL_SECONDS)
