"""The work procedure: request, advance, check, accept, and handover. The command line and the hooks use it."""

from __future__ import annotations

from pathlib import Path

from akasha import config
from akasha.config import RISK_LEVELS, Team
from akasha.coordinator import board, overlap
from akasha.core import handover as handover_document, risk, stages, workcopy
from akasha.core import task as tasks
from akasha.core.task import Task
from akasha.infra import github, server
from akasha.repo import gh
from akasha.validators import briefing as briefing_rules, runner

CONTEXT_PREFIX = config.TEAM_CONTEXT.as_posix() + "/"


def _publish(root: Path, task: Task) -> None:
    """Save the task on this computer, then put it on the shared board.

    When the board write fails, the task stays saved here. The error names the task, so that the person puts this
    task on the board later and does not record a second task."""
    tasks.save(root, task)
    try:
        published = board.publish(root, task)
    except board.BoardError as error:
        raise board.BoardError(f"{error}. Akasha saved the task {task.id} on this computer. When gh works again, "
                               f"run `akasha specify {task.id}` to put it on the board. Do not record the task "
                               "again") from error
    if published:
        tasks.save(root, task)


def _find(root: Path, task_id: str) -> Task | None:
    """A task on this computer, else on the shared task board."""
    try:
        return tasks.load(root, task_id)
    except LookupError:
        return board.find(root, task_id)


def _taken(root: Path, task_id: str) -> bool:
    """True when a task file, a branch on this computer or on the server, or an issue on the board has this id."""
    branches = [f"refs/heads/{prefix}{task_id}" for prefix in (workcopy.BRANCH_PREFIX, workcopy.WIP_PREFIX)]
    if tasks.exists(root, task_id) or workcopy.git(root, "rev-parse", "--verify", "-q", branches[0]).returncode == 0:
        return True
    if board.find(root, task_id) is not None:
        return True
    return bool(workcopy.git(root, "ls-remote", "origin", *branches).stdout.strip())    # without a server: empty


def _unique_id(root: Path, title: str) -> str:
    """A new task id that no other task in the repository has. Two tasks with one id share one branch, and the
    handover of the new task can find the merged pull request of the old task."""
    for _ in range(5):
        candidate = tasks.new_id(title)
        if not _taken(root, candidate):
            return candidate
    raise RuntimeError("Akasha made five task ids, and another task has each of them. Do the request again")


def _compare(root: Path, task: Task) -> list[overlap.Overlap]:
    """Compare the task with the tasks of all requesters. Write each overlap also on the issue of the other task.

    When the board is on GitHub and gh cannot read it, the comparison stops with BoardError: a comparison with only
    the tasks on this computer would find no overlap with the tasks of other people."""
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
    """Finish the tasks whose pull request merged, and remove the work copies of finished tasks."""
    for task in tasks.all_tasks(root):
        if task.status == "open" and task.stage == "handover" and task.pull_request:
            try:
                advance(root, task.id)                # the task is done when GitHub merged the pull request
            except board.BoardError:
                pass        # for example a person deleted the issue. The request reads and writes the board itself
            task = tasks.load(root, task.id)
        if task.status == "done" and task.workcopy:
            try:
                workcopy.remove(root, task)
            except RuntimeError:
                continue                  # the work copy has changes that are not saved; the next request tries again
            tasks.save(root, task)


def _start_ref(root: Path, task: Task) -> str:
    """Where the work copy starts: the branch of the earlier task when this task builds on one, else the latest
    default branch from the server. Without a server, the current commit."""
    if task.builds_on:
        branch = f"{workcopy.BRANCH_PREFIX}{task.builds_on}"
        workcopy.git(root, "fetch", "-q", "origin", branch)
        for ref in (branch, f"origin/{branch}"):              # this computer first, then the server
            if workcopy.git(root, "rev-parse", "--verify", "-q", ref).returncode == 0:
                return ref
        raise RuntimeError(f"the branch of {task.builds_on} is not on this computer or on the server yet — "
                           "it appears when all checks of that task pass")
    found = workcopy.git(root, "rev-parse", "--abbrev-ref", "origin/HEAD")      # for example origin/main
    default = found.stdout.strip() if found.returncode == 0 else ""
    if default.startswith("origin/") and default != "origin/HEAD":
        workcopy.git(root, "fetch", "-q", "origin", default.removeprefix("origin/"))
        return default
    return "HEAD"


def _open_workcopy(root: Path, team: Team, task: Task) -> None:
    """Make the work copy and run the setup command of the team in it. A failed setup becomes a note."""
    workcopy.create(root, task, _start_ref(root, task))
    tasks.save(root, task)                            # a stop during the setup command must not lose the work copy
    status, detail = runner.prepare(team, Path(task.workcopy))
    if status != "PASS":
        task.notes.append(f"the setup command failed in the work copy: {detail[-300:]}")


def outside_scope(task: Task, changed: list[str]) -> tuple[str, ...]:
    """The changed files that the task scope does not permit. A task without a scope permits all files.

    The team context, for example the product map, is outside each scope, so that each task can update it."""
    return tuple(path for path in changed if task.scope and not path.startswith(CONTEXT_PREFIX)
                 and not any(risk.matches(path, pattern) for pattern in task.scope))


def _raise_risk(task: Task, paths: list[str], team: Team) -> None:
    assessed = risk.assess(paths, team)
    if RISK_LEVELS.index(assessed.level) > RISK_LEVELS.index(task.risk):
        task.risk, task.risk_reasons = assessed.level, list(assessed.reasons)
    task.contracts = sorted(set(task.contracts) | set(assessed.contracts))


def start(root: Path, title: str, requester: str, workflow: str = "feature", feature: str = "",
          scope: list[str] | None = None, contracts: list[str] | None = None,
          builds_on: str = "") -> tuple[Task, list[overlap.Overlap]]:
    """Record a new task, compare it with the active tasks of all requesters, and put it on the shared board."""
    team = config.load(root)
    _tidy(root)
    if workflow not in team.workflows:
        raise ValueError(f"the workflow {workflow} is not enabled — use {', '.join(team.workflows)}")
    if builds_on and _find(root, builds_on) is None:
        raise ValueError(f"no task {builds_on} on this computer or on the shared task board")
    flow = team.workflows[workflow]
    task = Task(id=_unique_id(root, title), title=title, workflow=workflow, stage=flow.stages[0].id,
                requester=requester, feature=feature, scope=list(scope or []), contracts=list(contracts or []),
                builds_on=builds_on)
    _raise_risk(task, task.scope, team)
    found = _compare(root, task)
    if task.stage == "build":
        _open_workcopy(root, team, task)
    _publish(root, task)
    return task, found


def context(root: Path, team: Team, task: Task) -> stages.Context:
    """Measure the facts for the exit conditions. The risk level can only go up when the real changes are known.

    Akasha asks GitHub only for the facts that the exit conditions of the current stage need."""
    exits = set(team.workflows[task.workflow].stage(task.stage).exit)
    changed = workcopy.changed_files(task) if task.workcopy else []
    if changed:
        _raise_risk(task, changed, team)
    return stages.Context(
        approval_roles=team.approval.get(task.risk, ()), required_checks=team.required_checks,
        outside_scope=outside_scope(task, changed), map_changed=config.PRODUCT_MAP.as_posix() in changed,
        infra_ready="infra_ready" in exits and not github.status(root),
        merged="merged" in exits and bool(task.pull_request) and github.merged(root, task.pull_request))


def advance(root: Path, task_id: str) -> list[str]:
    """Move the task to its next stage. Return the reasons that block it, in simple words."""
    team, task = config.load(root), tasks.load(root, task_id)
    measured = context(root, team, task)
    gate = [role for role in measured.approval_roles if role not in task.approvals]
    if gate and task.workcopy and task.status == "open":      # the real changes raised the risk after the specification
        blocked = ["risk_approvals"]
    else:
        blocked = stages.advance(task, team.workflows[task.workflow], measured)
    if not blocked and task.stage == "build" and not task.workcopy:
        _open_workcopy(root, team, task)
    if task.status == "done" and task.workcopy:
        try:
            workcopy.remove(root, task)
        except RuntimeError:
            pass                                      # the next request tries again
    _publish(root, task)
    return [_explain(root, name, gate, task) for name in blocked]


def _explain(root: Path, name: str, gate: list[str], task: Task) -> str:
    if name == "risk_approvals":
        return f"a {' and a '.join(gate)} must approve the {task.risk} risk level"
    if name == "infra_ready":                         # the examination of this advance names the real cause
        problems = github.readiness(root)["problems"]
        return f"the server rules are not on: {problems[0]}" if problems else stages.EXPLAIN[name]
    return stages.EXPLAIN.get(name, name)


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


def impact(root: Path, task_id: str, values: dict[str, str], map_note: str = "",
           changes: tuple[str, str] | None = None) -> tuple[Task, str]:
    """Record the impact analysis of the agent engine.

    `changes` names an earlier task whose accepted behavior this task changes. Akasha tells its requester on its
    issue. Nobody waits for an answer: the requester reacts with a new request when necessary."""
    task = tasks.load(root, task_id)
    task.impact.update({key: text.strip() for key, text in values.items() if text and text.strip()})
    task.map_note = map_note.strip() or task.map_note
    told = ""
    if changes:
        other_id, what = changes
        other = _find(root, other_id)
        if other is None or not other.board:
            told = f"Akasha cannot find the task {other_id} on the shared task board. Tell its requester yourself."
        else:
            person = f"@{other.requester.lstrip('@')} " if other.requester else ""
            if board.comment(root, other.board, f"{person}Akasha: the task {task.id} ({task.title}) of "
                             f"{task.requester or 'another requester'} changes behavior that you accepted: {what}"):
                task.notes.append(f"told {other.requester or 'the requester'} of {other_id} about a change of "
                                  f"accepted behavior: {what}")
                told = f"Akasha told {other.requester or 'the requester'} on {other.board}."
            else:
                told = f"Akasha cannot write on {other.board}. Tell the requester of {other_id} yourself."
    _publish(root, task)
    return task, told


def brief(root: Path, task_id: str, text: str) -> list[str]:
    """Examine and record the briefing that the agent engine wrote. Return the problems; no problem means saved."""
    problems = briefing_rules.examine(text)
    if not problems:
        task = tasks.load(root, task_id)
        task.briefing = text.strip()
        _publish(root, task)
    return problems


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
    """Run the required checks in the work copy. Each failure counts as one failed repair.

    When all checks pass, Akasha saves the work as a commit and pushes the task branch. Thus the task branch on the
    server always passed the checks, and other tasks can build on it. Akasha saves nothing while the work copy has
    files outside the scope, for example files that a test made."""
    team, task = config.load(root), tasks.load(root, task_id)
    if not task.workcopy:
        raise ValueError("the task has no work copy — advance it to the build stage first")
    result = runner.run(team, Path(task.workcopy), workcopy.changed_files(task))
    task.checks = result.status
    failed = [name for name, status in result.status.items() if status == "FAIL"]
    if failed:
        stages.record_failure(task, "the check " + ", ".join(failed) + " failed")
    elif result.status and all(status == "PASS" for status in result.status.values()) and not _strays(task):
        tree = Path(task.workcopy)
        _commit(tree, task.title)
        workcopy.git(tree, "push", "-q", "-u", "origin", task.branch)      # without a server, the push fails quietly
    _publish(root, task)
    return result


def _strays(task: Task) -> tuple[str, ...]:
    """Files in the work copy that the scope does not permit. They must not go into a commit."""
    return outside_scope(task, workcopy.changed_files(task))


def ci_check(root: Path, config_path: Path | None, base: str) -> runner.Result:
    """The server check: the rules come from config_path, which CI takes from the default branch."""
    team = config.load(root, config_path)
    changed = workcopy.names(root, "diff", "--name-only", "--no-renames", f"{base}...HEAD")
    status, detail = runner.prepare(team, root)
    if status != "PASS":
        return runner.Result({"setup": status}, {"setup": detail})
    return runner.run(team, root, changed)


def _commit(tree: Path, title: str) -> None:
    if workcopy.git(tree, "status", "--porcelain").stdout.strip():
        workcopy.git(tree, "add", "-A")
        done = workcopy.git(tree, "commit", "-m", title)
        if done.returncode:
            raise RuntimeError(f"git commit failed: {done.stderr.strip()[:300]}")


def _examine_base(root: Path, task: Task) -> None:
    """A task that builds on an earlier task hands over only after the earlier task merged.

    Else its pull request also carries the changes of the earlier task before the requester of that task accepted
    them."""
    if not task.builds_on:
        return
    listed = gh(root, "pr", "list", "--head", f"{workcopy.BRANCH_PREFIX}{task.builds_on}", "--state", "merged",
                "--json", "number", "--jq", "length")
    if listed.returncode or listed.stdout.strip() in ("", "0"):
        raise RuntimeError(f"the task builds on {task.builds_on}, which did not merge yet. Hand over after it merges")


def handover(root: Path, task_id: str) -> tuple[str, list[str]]:
    """Check the change again on the latest default branch, open the pull request, and turn on auto-merge.

    The pull request merges as one squash commit when the required check passes: by GitHub auto-merge, or by the
    merge workflow of Akasha where GitHub has none. The commit body is the briefing, so a person who must revert the
    change later finds it fast. Return the pull request address and the reasons that keep the task at the handover
    stage."""
    task = tasks.load(root, task_id)
    if task.stage != "handover" or task.status != "open":
        raise ValueError(f"the task is {task.status} at the {task.stage} stage — the handover needs an open task "
                         "at the handover stage")
    if not task.briefing:
        raise ValueError("the task has no briefing — write it, then record it with brief")
    _examine_base(root, task)
    found = github.repository(root)
    if found is None:
        raise RuntimeError("the handover needs a GitHub repository — make sure that gh is installed and logged in")
    _slug, branch = found
    known = github.pull_request(root, task.pull_request or task.branch)     # also one that an earlier run did not record
    if known.get("state") == "MERGED":
        task.pull_request = known["url"]
        _publish(root, task)
        advance(root, task_id)
        raise ValueError("the pull request of this task merged — make a new request for more changes")
    task.pull_request = known["url"] if known.get("state") == "OPEN" else ""
    tasks.save(root, task)
    strays = _strays(task)
    if strays:
        raise RuntimeError(f"the work copy has files outside the scope: {', '.join(strays[:5])}. Remove them, add them "
                           "to .gitignore, or widen the scope with specify --scope. Then do the handover again")
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
    task = tasks.load(root, task_id)
    task.base = workcopy.git(tree, "rev-parse", f"origin/{branch}").stdout.strip() or task.base
    tasks.save(root, task)                            # from now on, the changed files are the changes of this task
    result = check(root, task_id)
    if any(status != "PASS" for status in result.status.values()):
        raise RuntimeError("a required check did not pass on the latest default branch: " + str(result.status))
    task = tasks.load(root, task_id)
    pushed = workcopy.git(tree, "push", "-u", "origin", task.branch)
    if pushed.returncode:
        raise RuntimeError(f"git push failed: {pushed.stderr.strip()[:300]}")
    team = config.load(root)
    helped = team.server_rules == "akasha"            # the merge workflow of Akasha merges a pull request with the label
    if not task.pull_request:                         # a second handover only pushes the new commits
        created = gh(root, "pr", "create", "--base", branch, "--head", task.branch, "--title", task.title,
                     "--body", handover_document.pull_request_body(task, branch, team.commands),
                     *(["--label", server.MERGE_LABEL] if helped else []))
        if created.returncode:
            raise RuntimeError(f"gh pr create failed: {created.stderr.strip()[:300]}")
        task.pull_request = created.stdout.strip().splitlines()[-1]
        _publish(root, task)
    elif helped and server.MERGE_LABEL not in {label.get("name") for label in known.get("labels", [])}:
        gh(root, "pr", "edit", task.pull_request, "--add-label", server.MERGE_LABEL)
    if not helped and not known.get("autoMergeRequest"):
        number = task.pull_request.rstrip("/").rsplit("/", 1)[-1]
        queued = github.auto_merge(root, task.pull_request, f"{task.title} (#{number})",
                                   handover_document.commit_body(task, branch, team.commands))
        if queued.returncode:
            raise RuntimeError(f"the pull request is open, but GitHub did not turn on auto-merge: "
                               f"{queued.stderr.strip()[:300]}. An administrator must correct the GitHub settings")
    return task.pull_request, advance(root, task_id)
