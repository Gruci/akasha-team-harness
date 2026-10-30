"""The work procedure: request, advance, check, accept, and handover. The command line and the hooks use it."""

from __future__ import annotations

from pathlib import Path

from akasha import config
from akasha.config import RISK_LEVELS, Team
from akasha.coordinator import board, overlap
from akasha.core import handover as handover_document, risk, stages, workcopy
from akasha.core import task as tasks
from akasha.core.task import Task
from akasha.infra import github
from akasha.repo import gh
from akasha.validators import runner


def _publish(root: Path, task: Task) -> None:
    tasks.save(root, task)
    if board.publish(root, task):
        tasks.save(root, task)


def _compare(root: Path, task: Task) -> list[overlap.Overlap]:
    """Compare the task with the tasks of all requesters. Write each overlap also on the issue of the other task."""
    others, _source = board.read(root)
    found = overlap.find(task, others)
    addresses = {other.id: other.board for other in others if other.board}
    for item in found:
        if item.other in addresses:
            board.comment(root, addresses[item.other], f"Akasha found an overlap with the task {task.id} "
                          f"({task.title}, requester {task.requester or 'unknown'}): {item.detail}. "
                          f"{overlap.ACTIONS[item.kind]}")
    return found


def _examine_role(team: Team, role: str, person: str) -> None:
    """A developer or an administrator must be a person that akasha.toml names for that role."""
    names = {"developer": team.developers, "administrator": team.administrators}.get(role, ())
    if names and person.lstrip("@") not in {name.lstrip("@") for name in names}:
        raise ValueError(f"{person} is not a {role} in {config.CONFIG_FILE} — use {', '.join(names)}")


def _tidy(root: Path) -> None:
    """Remove the work copies of finished tasks after their pull request merges."""
    for task in tasks.all_tasks(root):
        if task.status == "done" and task.workcopy and task.pull_request:
            state = gh(root, "pr", "view", task.pull_request, "--json", "state", "--jq", ".state")
            if state.returncode or state.stdout.strip() != "MERGED":
                continue
            try:
                workcopy.remove(root, task)
            except RuntimeError:
                continue                  # the work copy has changes that are not saved; the next request tries again
            tasks.save(root, task)


def _open_workcopy(root: Path, team: Team, task: Task) -> None:
    """Make the work copy and run the setup command of the team in it. A failed setup becomes a note."""
    workcopy.create(root, task)
    status, detail = runner.prepare(team, Path(task.workcopy))
    if status != "PASS":
        task.notes.append(f"the setup command failed in the work copy: {detail[-300:]}")


def outside_scope(task: Task, changed: list[str]) -> tuple[str, ...]:
    """The changed files that the task scope does not permit. A task without a scope permits all files."""
    return tuple(path for path in changed
                 if task.scope and not any(risk.matches(path, pattern) for pattern in task.scope))


def _raise_risk(task: Task, paths: list[str], team: Team) -> None:
    assessed = risk.assess(paths, team)
    if RISK_LEVELS.index(assessed.level) > RISK_LEVELS.index(task.risk):
        task.risk, task.risk_reasons = assessed.level, list(assessed.reasons)
    task.contracts = sorted(set(task.contracts) | set(assessed.contracts))


def start(root: Path, title: str, requester: str, workflow: str = "feature", feature: str = "",
          scope: list[str] | None = None, contracts: list[str] | None = None) -> tuple[Task, list[overlap.Overlap]]:
    """Record a new task, compare it with the open tasks of all requesters, and put it on the shared board."""
    team = config.load(root)
    _tidy(root)
    if workflow not in team.workflows:
        raise ValueError(f"the workflow {workflow} is not enabled — use {', '.join(team.workflows)}")
    flow = team.workflows[workflow]
    task = Task(id=tasks.new_id(title), title=title, workflow=workflow, stage=flow.stages[0].id,
                requester=requester, feature=feature, scope=list(scope or []), contracts=list(contracts or []))
    _raise_risk(task, task.scope, team)
    found = _compare(root, task)
    if task.stage == "build":
        _open_workcopy(root, team, task)
    _publish(root, task)
    return task, found


def context(root: Path, team: Team, task: Task) -> stages.Context:
    """Measure the facts for the exit conditions. The risk level can only go up when the real changes are known."""
    changed = workcopy.changed_files(task) if task.workcopy else []
    if changed:
        _raise_risk(task, changed, team)
    ready = task.stage == "handover" and not github.status(root)
    return stages.Context(approval_roles=team.approval.get(task.risk, ()), required_checks=team.required_checks,
                          outside_scope=outside_scope(task, changed), infra_ready=ready)


def advance(root: Path, task_id: str) -> list[str]:
    """Move the task to its next stage. Return the reasons that block it, in simple words."""
    team, task = config.load(root), tasks.load(root, task_id)
    measured = context(root, team, task)
    blocked = stages.advance(task, team.workflows[task.workflow], measured)
    if not blocked and task.stage == "build" and not task.workcopy:
        _open_workcopy(root, team, task)
    _publish(root, task)
    missing = " and a ".join(role for role in measured.approval_roles if role not in task.approvals)
    return [f"a {missing} must approve the {task.risk} risk level" if name == "risk_approvals"
            else stages.EXPLAIN.get(name, name) for name in blocked]


def specify(root: Path, task_id: str, conditions: list[str], questions: list[str], clear_questions: bool,
            scope: list[str] | None = None) -> tuple[Task, list[overlap.Overlap]]:
    """Add completion conditions, open questions, or file patterns of the scope.

    A wider scope can raise the risk level and touch other tasks, so Akasha compares it with the open tasks again."""
    task = tasks.load(root, task_id)
    task.conditions += [item for item in conditions if item not in task.conditions]
    task.open_questions = [] if clear_questions else task.open_questions + questions
    added = [pattern for pattern in scope or [] if pattern not in task.scope]
    found = []
    if added:
        task.scope += added
        _raise_risk(task, added, config.load(root))
        found = _compare(root, task)
    _publish(root, task)
    return task, found


def approve(root: Path, task_id: str, role: str, person: str) -> Task:
    if role not in config.ROLES:
        raise ValueError(f"unknown role {role} — use {', '.join(config.ROLES)}")
    _examine_role(config.load(root), role, person)
    task = tasks.load(root, task_id)
    task.approvals[role] = person
    _publish(root, task)
    return task


def resume(root: Path, task_id: str, developer: str) -> Task:
    """A developer examined a stopped task. Open it again with a new count of failed repairs."""
    _examine_role(config.load(root), "developer", developer)
    task = tasks.load(root, task_id)
    if task.status != "stopped":
        raise ValueError(f"the task is {task.status}, not stopped")
    task.status, task.failures = "open", 0
    task.notes.append(f"{developer} examined the problem and opened the task again")
    _publish(root, task)
    return task


def cancel(root: Path, task_id: str, person: str) -> Task:
    """Stop a task for good, for example when the requester withdraws the request. The work copy stays."""
    task = tasks.load(root, task_id)
    if not tasks.active(task):
        raise ValueError(f"the task is {task.status}")
    task.status = "cancelled"
    task.notes.append(f"{person} cancelled the task")
    _publish(root, task)
    return task


def accept(root: Path, task_id: str, condition: str | None, result: bool) -> Task:
    """Record the inspection of one completion condition, or of all conditions when condition is None."""
    task = tasks.load(root, task_id)
    for item in [condition] if condition else task.conditions:
        if item not in task.conditions:
            raise ValueError(f"the task has no completion condition: {item}")
        task.accepted[item] = result
    _publish(root, task)
    return task


def check(root: Path, task_id: str) -> runner.Result:
    """Run the required checks in the work copy. Each failure counts as one failed repair."""
    team, task = config.load(root), tasks.load(root, task_id)
    if not task.workcopy:
        raise ValueError("the task has no work copy — advance it to the build stage first")
    result = runner.run(team, Path(task.workcopy), workcopy.changed_files(task))
    task.checks = result.status
    failed = [name for name, status in result.status.items() if status == "FAIL"]
    if failed:
        stages.record_failure(task, "the check " + ", ".join(failed) + " failed")
    _publish(root, task)
    return result


def ci_check(root: Path, config_path: Path | None, base: str) -> runner.Result:
    """The server check: the rules come from config_path, which CI takes from the default branch."""
    team = config.load(root, config_path)
    diff = workcopy.git(root, "diff", "--name-only", f"{base}...HEAD")
    if diff.returncode:
        raise RuntimeError(f"git diff against {base} failed: {diff.stderr.strip()[:300]}")
    status, detail = runner.prepare(team, root)
    if status != "PASS":
        return runner.Result({"setup": status}, {"setup": detail})
    return runner.run(team, root, [line for line in diff.stdout.splitlines() if line.strip()])


def _commit(tree: Path, title: str) -> None:
    if workcopy.git(tree, "status", "--porcelain").stdout.strip():
        workcopy.git(tree, "add", "-A")
        done = workcopy.git(tree, "commit", "-m", title)
        if done.returncode:
            raise RuntimeError(f"git commit failed: {done.stderr.strip()[:300]}")


def handover(root: Path, task_id: str) -> tuple[str, list[str]]:
    """Check the change again on the latest default branch, then open the pull request with the handover document.

    Return the pull request address and the reasons that keep the task at the handover stage."""
    task = tasks.load(root, task_id)
    if task.stage != "handover":
        raise ValueError(f"the task is at the {task.stage} stage, not at the handover stage")
    found = github.repository(root)
    if found is None:
        raise RuntimeError("the handover needs a GitHub repository — make sure that gh is installed and logged in")
    _slug, branch = found
    tree = Path(task.workcopy)
    _commit(tree, task.title)
    fetched = workcopy.git(tree, "fetch", "origin", branch)
    if fetched.returncode:
        raise RuntimeError(f"git fetch failed: {fetched.stderr.strip()[:300]}")
    merged = workcopy.git(tree, "merge", "--no-edit", f"origin/{branch}")
    if merged.returncode:
        workcopy.git(tree, "merge", "--abort")
        raise RuntimeError(f"the change conflicts with the latest {branch}. In {tree}, run git merge origin/{branch}, "
                           "repair the conflict, and commit. Then do the handover again")
    result = check(root, task_id)
    if any(status != "PASS" for status in result.status.values()):
        raise RuntimeError("a required check did not pass on the latest default branch: " + str(result.status))
    task = tasks.load(root, task_id)
    pushed = workcopy.git(tree, "push", "-u", "origin", task.branch)
    if pushed.returncode:
        raise RuntimeError(f"git push failed: {pushed.stderr.strip()[:300]}")
    if not task.pull_request:                     # a second handover only pushes the new commits
        body = handover_document.render(task, workcopy.changed_files(task))
        if task.board:                            # the merge closes the issue of the task on the board
            body += f"\nCloses #{task.board.rstrip('/').rsplit('/', 1)[-1]}\n"
        created = gh(root, "pr", "create", "--base", branch, "--head", task.branch, "--title", task.title,
                     "--body", body)
        if created.returncode:
            raise RuntimeError(f"gh pr create failed: {created.stderr.strip()[:300]}")
        task.pull_request = created.stdout.strip().splitlines()[-1]
        _publish(root, task)
    return task.pull_request, advance(root, task_id) if task.status == "open" else []
