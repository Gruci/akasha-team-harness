"""The work procedure: request, advance, check, accept, handover, handoff, and takeover. The command line and the
hooks use it.

With GitHub, the issue of each task holds its state, and one person in one copy of the repository holds each task:
the holder. Only the holder changes the task. The holder hands off the task, and another person takes it over on
another computer."""

from __future__ import annotations

from pathlib import Path

from akasha import config, repo
from akasha.config import RISK_LEVELS, Team
from akasha.coordinator import board, overlap
from akasha.core import handover as handover_document, risk, stages, workcopy
from akasha.core import task as tasks
from akasha.core.task import Task
from akasha.infra import github, server
from akasha.repo import gh
from akasha.validators import briefing as briefing_rules, runner

CONTEXT_PREFIX = config.TEAM_CONTEXT.as_posix() + "/"
OLD_SETUP_NOTE = "the setup command failed in the work copy: "     # Akasha 1.0.0 wrote the output after it


class HolderError(RuntimeError):
    """Another person or another computer holds the task, or changed it after this command read it."""


def _who(root: Path) -> tuple[str, str]:
    """The GitHub name of this person and the mark of this copy of the repository.

    Without GitHub, both are empty: nobody holds a task, and each command changes each task on this computer, as in
    Akasha 1.0.0."""
    if not board.available(root):
        return "", ""
    name = repo.me(root)
    if not name:
        raise board.BoardError("Akasha cannot read your GitHub name. Make sure that gh is installed and logged in: "
                               "gh auth status")
    return name, repo.host(root)


def _publish(root: Path, task: Task) -> None:
    """Raise the revision, save the task on this computer, then write it on its issue.

    Akasha reads the issue again before it writes. When another computer wrote the issue after this command read the
    task, the command stops and does not write over the newer state. A body without the format has no revision:
    Akasha 1.0.0 or a person wrote it, and the task file here has the whole task, so Akasha writes over it. When the
    board write fails, the task stays saved here with the higher revision, and the next command for the task puts it
    on the board. The error names the task, so that the person does not record a second task."""
    task.revision, task.format = task.revision + 1, tasks.FORMAT
    tasks.save(root, task)
    try:
        current = board.find(root, task.id) if task.board and board.available(root) else None
        if current is not None and current.format >= tasks.FORMAT and current.revision != task.synced:
            raise HolderError(f"another computer or another command changed the task {task.id} after this command "
                              "read it. Do the step again: Akasha reads the new state first")
        published = board.publish(root, task)
    except board.BoardError as error:
        raise board.BoardError(f"{error}. Akasha saved the task {task.id} on this computer. When gh works again, "
                               f"run `akasha specify {task.id}` to put it on the board. Do not record the task "
                               "again") from error
    if published:
        task.synced = task.revision
        tasks.save(root, task)


def load(root: Path, task_id: str, write: bool = True) -> Task:
    """The latest state of the task. LookupError when no computer and no issue has it.

    With GitHub, the issue holds the state, and Akasha takes only the fields of this computer (LOCAL_FIELDS) from the
    task file. When the task file has changes that the issue did not get, for example after a failed board write,
    and nobody wrote the issue since, the task file is newer. A task of Akasha 1.0.0 is in its task file on one
    computer, and so is a task that has no issue, because this computer recorded it before origin was on GitHub or
    its first board write failed. With `write`, such a task goes to the person on that computer (_adopt), and Akasha
    puts a newer task file on the issue. A task file that knows an issue that Akasha cannot read does not go to this
    person: another person can hold that task. The approvals and the inspection results come from the issue body.
    Without GitHub, Akasha reads the task file."""
    try:
        local = tasks.load(root, task_id)
    except LookupError:
        local = None
    on_github = local is not None and board.available(root)
    shared = board.find(root, task_id) if local is None or on_github else None
    if shared is None and local is None:
        raise LookupError(f"no task {task_id} on this computer or on the shared task board")
    if shared is None:
        task = local
    elif local is not None and (shared.format < tasks.FORMAT
                                or (shared.revision == local.synced and local.revision > shared.revision)):
        task = local
        task.board = task.board or shared.board
    else:
        task = shared
        for name in tasks.LOCAL_FIELDS if local is not None else ():
            setattr(task, name, getattr(local, name))
        task.synced = task.revision
        return task
    first = not task.board if shared is None else shared.format < tasks.FORMAT
    if write and on_github and first:
        _adopt(root, task)                            # the first issue of the task in the new format
    if write and shared is not None:
        _publish(root, task)
    return task


def _setup_note(task: Task) -> str:
    """The note of a failed setup command. The output stays on this computer, because it can show paths and secrets."""
    return (f"the setup command failed in the work copy. `akasha show {task.id}` on the computer of the work copy "
            "shows the output")


def _adopt(root: Path, task: Task) -> None:
    """Prepare a task for its first issue in the new format: a task of Akasha 1.0.0, or a task without an issue. The
    person here holds it. Akasha 1.0.0 wrote the output of a failed setup in a note, and that output stays on this
    computer."""
    if not task.holder:
        task.holder, task.holder_host = _who(root)
    for number, note in enumerate(task.notes):
        if note.startswith(OLD_SETUP_NOTE):
            task.setup_output = note.removeprefix(OLD_SETUP_NOTE)
            task.notes[number] = _setup_note(task)


def _examine_holder(root: Path, task: Task) -> None:
    """With GitHub, only the holder changes a task: the same GitHub name in the same copy of the repository."""
    name, host = _who(root)
    if not name or not task.board or (task.holder, task.holder_host) == (name, host):
        return
    if not task.holder:
        problem = f"nobody holds the task {task.id}. Take it over first: akasha takeover {task.id}"
    elif task.holder == name:
        problem = (f"you hold the task {task.id} in another copy of the repository. Hand it off there with akasha "
                   f"handoff {task.id}, then take it over here with akasha takeover {task.id}")
    else:
        problem = (f"{task.holder} holds the task {task.id}. Ask {task.holder} to hand it off with akasha handoff "
                   f"{task.id}, then take it over with akasha takeover {task.id}")
    if task.workcopy and Path(task.workcopy).is_dir():
        problem += (f". This computer still has a work copy of the task in {task.workcopy}. Examine it and save what "
                    f"you need, then remove it: git worktree remove --force {task.workcopy}")
    raise HolderError(problem)


def _held(root: Path, task_id: str) -> Task:
    """The task, when this person in this copy of the repository holds it. Each command that changes a task reads
    the task here."""
    task = load(root, task_id)
    _examine_holder(root, task)
    return task


def _find(root: Path, task_id: str) -> Task | None:
    """The task on the shared task board or on this computer, or None. It reads and does not write."""
    try:
        return load(root, task_id, write=False)
    except LookupError:
        return None


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
    if names and person.lstrip("@").lower() not in {name.lstrip("@").lower() for name in names}:
        raise ValueError(f"{person} is not a {role} in {config.CONFIG_FILE} — use {', '.join(names)}")


def _tidy(root: Path) -> None:
    """Finish the tasks of this computer whose pull request merged, and remove the work copies of finished tasks.

    With GitHub, Akasha skips the tasks that another person or computer holds, and the tasks that this computer
    handed off. A task of Akasha 1.0.0 (revision 0) has no holder yet, and this computer finishes it."""
    who = _who(root)
    for task in tasks.all_tasks(root):
        if who[0] and task.revision and (task.holder, task.holder_host) != who:
            continue
        if task.status == "open" and task.stage == "handover" and task.pull_request:
            try:
                advance(root, task.id)                # the task is done when GitHub merged the pull request
            except (board.BoardError, HolderError):
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
    return _default_ref(root)


def _default_ref(root: Path) -> str:
    """The latest default branch from the server, for example origin/main. Without a server, the current commit."""
    found = workcopy.git(root, "rev-parse", "--abbrev-ref", "origin/HEAD")
    default = found.stdout.strip() if found.returncode == 0 else ""
    if default.startswith("origin/") and default != "origin/HEAD":
        workcopy.git(root, "fetch", "-q", "origin", default.removeprefix("origin/"))
        return default
    return "HEAD"


def _open_workcopy(root: Path, team: Team, task: Task, start: str = "") -> None:
    """Make the work copy from `start`, else from _start_ref, and run the setup command of the team in it. A failed
    setup becomes a note. The caller puts the task on the board.

    A task that continues from `start`, for example the work of another computer, keeps its base: its changes stay
    the changes since that base. The output of a failed setup stays on this computer, because it can show paths and
    secrets."""
    kept = task.base if start else ""
    workcopy.create(root, task, start or _start_ref(root, task))
    task.base = kept or task.base
    task.revision += 1          # a stop during the setup command must not lose the work copy, the branch, or the base:
    tasks.save(root, task)      # the next command finds this newer state on this computer and puts it on the issue
    status, detail = runner.prepare(team, Path(task.workcopy))
    task.setup_output = detail[-3000:] if status != "PASS" else ""
    if status != "PASS":
        task.notes.append(_setup_note(task))


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
    """Record a new task, put it on the shared board, and compare it with the active tasks of all requesters.

    The task goes on the board before the comparison, so that two tasks that start at the same time see each other.
    The work copy comes after the comparison. Akasha finds its start commit before it records the task, so that a
    missing branch of the earlier task stops the request before the task exists. The person who records the task
    holds it in this copy of the repository."""
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
    task.holder, task.holder_host = _who(root)
    _raise_risk(task, task.scope, team)
    begin = _start_ref(root, task) if task.stage == "build" else ""
    _publish(root, task)
    try:
        found = _compare(root, task)
    except board.BoardError as error:
        raise board.BoardError(f"{error}. Akasha recorded the task {task.id}: continue with it, and do not record "
                               "the task again. When gh works again, `akasha board` shows the other tasks") from error
    if begin:
        try:
            _open_workcopy(root, team, task, begin)
        except RuntimeError as error:
            raise RuntimeError(f"{error}. Akasha recorded the task {task.id}: continue with it, and do not record the "
                               f"task again. When the cause is repaired, run `akasha advance {task.id}`: it makes the "
                               "work copy") from error
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
    team, task = config.load(root), _held(root, task_id)
    measured = context(root, team, task)
    gate = [role for role in measured.approval_roles if role not in task.approvals]
    if gate and task.workcopy and task.status == "open":      # the real changes raised the risk after the specification
        blocked = ["risk_approvals"]
    else:
        blocked = stages.advance(task, team.workflows[task.workflow], measured)
    if task.status == "open" and task.stage == "build" and not task.branch:      # also after a failed creation
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
            scope: list[str] | None = None, builds_on: str | None = None) -> tuple[Task, list[overlap.Overlap]]:
    """Add completion conditions, open questions, or file patterns of the scope. `builds_on=""` stops building on
    the earlier task.

    A wider scope can raise the risk level and touch other tasks, so Akasha compares it with the open tasks again."""
    task = _held(root, task_id)
    task.conditions += [item for item in conditions if item not in task.conditions]
    task.open_questions = [] if clear_questions else task.open_questions + questions
    if builds_on is not None:
        _unstack(root, task, builds_on)
    added = [pattern for pattern in scope or [] if pattern not in task.scope]
    found = []
    if added:
        task.scope += added
        _raise_risk(task, added, config.load(root))
        found = _compare(root, task)
    _publish(root, task)
    return task, found


def _unstack(root: Path, task: Task, builds_on: str) -> None:
    """Stop building on the earlier task, for example after its requester cancelled it.

    The base goes back to the default branch. Thus the changes of the earlier task that the work copy has become
    changes of this task, and the checks, the scope, and the pull request show them."""
    if builds_on:
        raise ValueError('specify accepts only --builds-on "", which stops building on the earlier task. To build on '
                         "another task, record a new request with --builds-on")
    if not task.builds_on:
        return
    if task.workcopy and Path(task.workcopy).is_dir():
        found = workcopy.git(root, "merge-base", _default_ref(root), task.branch)
        task.base = found.stdout.strip() or task.base
        task.notes.append(f"the task does not build on {task.builds_on} now. The changes of {task.builds_on} in the "
                          "work copy are changes of this task: remove the ones that this task does not need")
    else:
        task.notes.append(f"the task does not build on {task.builds_on} now")
    task.builds_on = ""


def impact(root: Path, task_id: str, values: dict[str, str], map_note: str = "",
           changes: tuple[str, str] | None = None) -> tuple[Task, str]:
    """Record the impact analysis of the agent engine.

    `changes` names an earlier task whose accepted behavior this task changes. Akasha tells its requester on its
    issue. Nobody waits for an answer: the requester reacts with a new request when necessary."""
    task = _held(root, task_id)
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
        task = _held(root, task_id)
        task.briefing = text.strip()
        _publish(root, task)
    return problems


def approve(root: Path, task_id: str, role: str, person: str) -> Task:
    if role not in config.ROLES:
        raise ValueError(f"unknown role {role} — use {', '.join(config.ROLES)}")
    _examine_role(config.load(root), role, person)
    task = _held(root, task_id)
    task.approvals[role] = person
    _publish(root, task)
    return task


def resume(root: Path, task_id: str, developer: str) -> Task:
    """A developer examined a stopped task. Open it again with a new count of failed repairs."""
    _examine_role(config.load(root), "developer", developer)
    task = _held(root, task_id)
    if task.status != "stopped":
        raise ValueError(f"the task is {task.status}, not stopped")
    task.status, task.failures = "open", 0
    task.notes.append(f"{developer} examined the problem and opened the task again")
    _publish(root, task)
    return task


def cancel(root: Path, task_id: str, person: str) -> Task:
    """Stop a task for good, for example when the requester withdraws the request. The work copy stays."""
    task = _held(root, task_id)
    if not tasks.active(task):
        raise ValueError(f"the task is {task.status}")
    task.status = "cancelled"
    task.notes.append(f"{person} cancelled the task")
    _drop_wip(root, task)
    _publish(root, task)
    return task


def accept(root: Path, task_id: str, condition: str | None, result: bool) -> Task:
    """Record the inspection of one completion condition, or of all conditions when condition is None."""
    task = _held(root, task_id)
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
    team, task = config.load(root), _held(root, task_id)
    tree = _tree(task)
    result = runner.run(team, tree, workcopy.changed_files(task))
    task.checks = result.status
    failed = [name for name, status in result.status.items() if status == "FAIL"]
    if failed:
        stages.record_failure(task, "the check " + ", ".join(failed) + " failed")
    elif result.status and all(status == "PASS" for status in result.status.values()) and not _strays(task):
        _commit(tree, task.title)
        workcopy.git(tree, "push", "-q", "-u", "origin", task.branch)      # without a server, the push fails quietly
    _publish(root, task)
    return result


def _on_branch(tree: Path, branch: str) -> bool:
    """True when git in the folder is on the branch. In a folder that is not a work copy, for example an empty folder
    that a failed removal left, git works on the main checkout."""
    return workcopy.git(tree, "symbolic-ref", "-q", "HEAD").stdout.strip() == f"refs/heads/{branch}"


def _tree(task: Task) -> Path:
    """The work copy of the task on this computer. A folder that is not on the task branch is not the work copy:
    Akasha never commits or pushes there."""
    if not task.workcopy or not Path(task.workcopy).is_dir():
        raise ValueError("the task has no work copy on this computer — " + (
            f"make it from the work on the server with akasha takeover {task.id}" if task.branch
            else "advance it to the build stage first"))
    if not _on_branch(Path(task.workcopy), task.branch):
        raise RuntimeError(f"git in {task.workcopy} is not on the branch {task.branch}, so the folder is not the work "
                           f"copy of the task. Check out {task.branch} there. Or examine the folder, save what you "
                           f"need, remove it, and make the work copy again with akasha takeover {task.id}")
    return Path(task.workcopy)


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
    them. When the requester of the earlier task cancelled it, it never merges: the task must stop building on it."""
    if not task.builds_on:
        return
    earlier = _find(root, task.builds_on)
    if earlier is not None and earlier.status == "cancelled":
        raise RuntimeError(f"the earlier task {task.builds_on} was cancelled, so it never merges. Stop building on it: "
                           f"akasha specify {task.id} --builds-on \"\". Then remove the changes of {task.builds_on} "
                           "that this task does not need, and do the handover again")
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
    task = _held(root, task_id)
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
    _publish(root, task)
    tree = _tree(task)
    strays = _strays(task)
    if strays:
        raise RuntimeError(f"the work copy has files outside the scope: {', '.join(strays[:5])}. Remove them, add them "
                           "to .gitignore, or widen the scope with specify --scope. Then do the handover again")
    _commit(tree, task.title)
    fetched = workcopy.git(tree, "fetch", "origin", branch)
    if fetched.returncode:
        raise RuntimeError(f"git fetch failed: {fetched.stderr.strip()[:300]}")
    merged = workcopy.git(tree, "merge", "--no-edit", f"origin/{branch}")
    if merged.returncode:
        workcopy.git(tree, "merge", "--abort")
        raise RuntimeError(f"the change conflicts with the latest {branch}. In {tree}, run git merge origin/{branch}, "
                           "repair the conflict, and commit. Then do the handover again")
    task.base = workcopy.git(tree, "rev-parse", f"origin/{branch}").stdout.strip() or task.base
    _publish(root, task)                              # from now on, the changed files are the changes of this task
    result = check(root, task_id)
    if any(status != "PASS" for status in result.status.values()):
        raise RuntimeError("a required check did not pass on the latest default branch: " + str(result.status))
    task = load(root, task_id)
    pushed = workcopy.git(tree, "push", "-u", "origin", task.branch)
    if pushed.returncode:
        raise RuntimeError(f"git push failed: {pushed.stderr.strip()[:300]}")
    if task.wip:                                      # the task branch has the work of the last handoff now
        _drop_wip(root, task)
        _publish(root, task)
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


def _drop_wip(root: Path, task: Task) -> None:
    """Delete the branch of the last handoff on the server. A failure does not matter: the branch only waits there."""
    if task.wip:
        workcopy.git(root, "push", "-q", "origin", "--delete", f"{workcopy.WIP_PREFIX}{task.id}")
        task.wip = ""


def handoff(root: Path, task_id: str) -> Task:
    """Save the work so far on the server and free the task, so that another person can take it over.

    The work goes to the wip branch, not to the task branch: the task branch on the server always passed the checks,
    and later tasks build on it. Akasha does not force the push, so a copy that is behind the server cannot write
    over newer work. The issue gets the work and the free task before the work copy and the local branch go away,
    so that a later takeover on this computer starts from the server. On Windows, nobody can remove a folder that a
    program works in, so the handoff does not run from inside the work copy."""
    if not board.available(root):
        raise RuntimeError("the handoff needs the shared task board on GitHub")
    task = _held(root, task_id)
    if not tasks.active(task):
        raise ValueError(f"the task is {task.status} — only an open or stopped task can go to another person")
    tree = _tree(task) if task.workcopy and Path(task.workcopy).is_dir() else None
    if tree is not None and Path.cwd().resolve().is_relative_to(tree.resolve()):
        raise RuntimeError(f"run the handoff in the main checkout {root}, not in the work copy: the handoff removes "
                           "the work copy, and a program cannot remove the folder that it works in")
    if tree is not None:
        changed = workcopy.changed_files(task)
        status, hits = runner.secrets_status(tree, changed)
        if status == "FAIL":
            raise RuntimeError(f"the work copy has secret keys: {'; '.join(hits.splitlines())}. Remove them, then do "
                               "the handoff again")
        strays = outside_scope(task, changed)
        if strays:
            raise RuntimeError(f"the work copy has files outside the scope: {', '.join(strays[:5])}. Remove them, add "
                               "them to .gitignore, or widen the scope with specify --scope. Then do the handoff again")
        _commit(tree, f"wip: {task.title}")
        pushed = workcopy.git(tree, "push", "-q", "origin", f"HEAD:refs/heads/{workcopy.WIP_PREFIX}{task.id}")
        if pushed.returncode:
            raise RuntimeError(f"git push failed: {pushed.stderr.strip()[:300]}. Akasha never forces this push: when "
                               "the server has newer work of this task, this work copy is behind it")
        task.wip = workcopy.git(tree, "rev-parse", "HEAD").stdout.strip()
    task.holder = task.holder_host = ""
    _publish(root, task)
    if tree is not None:
        try:
            workcopy.remove(root, task)
        except RuntimeError as error:
            raise RuntimeError(f"Akasha handed off the task {task.id}: its work is on the server, and nobody holds it. "
                               f"But {error}. Close each program that uses {tree}, then remove the folder") from error
        workcopy.git(root, "branch", "-D", task.branch)
        tasks.save(root, task)                        # only the work copy of this computer changed
    return task


def _contains(tree: Path, ref: str, commit: str) -> bool:
    """True when `ref` has the commit in its history."""
    return workcopy.git(tree, "merge-base", "--is-ancestor", commit, ref).returncode == 0


def _work_on_server(root: Path, task: Task) -> str:
    """Where the work copy of a task from another computer starts: the work of the last handoff, else the task branch
    on the server. A work copy or a branch of the task that this computer still has must go forward to it, so that
    no old work of this computer replaces the newer work of another person."""
    wip, found = f"{workcopy.WIP_PREFIX}{task.id}", set()
    for branch in (wip, task.branch):
        fetched = workcopy.git(root, "fetch", "-q", "origin", f"+refs/heads/{branch}:refs/remotes/origin/{branch}")
        if fetched.returncode == 0:
            found.add(branch)
    start = f"origin/{task.branch}" if task.branch in found else ""
    handed = wip in found and workcopy.git(root, "rev-parse", f"origin/{wip}").stdout.strip() == task.wip
    if task.wip and handed and not (start and _contains(root, start, task.wip)):
        start = f"origin/{wip}"
    if not start:
        raise RuntimeError(f"the work of the task {task.id} is not on the server: no branch {wip} and no branch "
                           f"{task.branch}. Ask {task.holder or 'the last holder'} to hand it off with akasha handoff "
                           f"{task.id}")
    workcopy.git(root, "worktree", "prune")          # forget the work copies whose folders a person removed
    tree = Path(task.workcopy) if task.workcopy else root / workcopy.WORK_DIR / task.id
    if tree.is_dir():
        if not _on_branch(tree, task.branch) or workcopy.git(tree, "status", "--porcelain").stdout.strip() \
                or not _contains(tree, start, "HEAD"):
            raise RuntimeError(f"this computer has a work copy of the task in {tree} that cannot go forward to the "
                               "work on the server: it has other work, or it is not on the branch of the task. "
                               f"Examine it and save what you need, remove it with git worktree remove --force {tree}, "
                               "then do the takeover again")
        moved = workcopy.git(tree, "merge", "--ff-only", "-q", start)
    elif workcopy.git(root, "rev-parse", "--verify", "-q", f"refs/heads/{task.branch}").returncode == 0:
        if not _contains(root, start, task.branch):
            raise RuntimeError(f"the branch {task.branch} on this computer cannot go forward to the work on the server: "
                               f"it has other commits. Examine them, then delete the branch with git branch -D "
                               f"{task.branch}, and do the takeover again")
        moved = workcopy.git(root, "branch", "-f", task.branch, start)
    else:
        return start
    if moved.returncode:
        raise RuntimeError(f"git cannot move {task.branch} to the work on the server: {moved.stderr.strip()[:300]}")
    return start


def takeover(root: Path, task_id: str) -> Task:
    """Hold a task that another person handed off, and continue it in this copy of the repository.

    The work copy starts from the work of the last handoff, or from the task branch on the server, and keeps the base
    of the task. The holder is a person in one copy of the repository: when the same person holds the task in another
    copy, that copy must hand it off first, else its work that is not on the server stays there. A developer can also
    take over a stopped task that its holder did not hand off. Then Akasha tells the old holder on the issue."""
    if not board.available(root):
        raise RuntimeError("the takeover needs the shared task board on GitHub")
    team, task = config.load(root), load(root, task_id)
    if not tasks.active(task):
        raise ValueError(f"the task is {task.status} — only an open or stopped task can go to another person")
    if task.format < tasks.FORMAT:
        raise RuntimeError(f"Akasha 1.0.0 recorded the task {task.id} on another computer. Ask the person on that "
                           f"computer to update Akasha and hand it off with akasha handoff {task.id}")
    name, host = _who(root)
    present = bool(task.workcopy) and Path(task.workcopy).is_dir() and _on_branch(Path(task.workcopy), task.branch)
    if (task.holder, task.holder_host) == (name, host) and (present or not task.branch):
        return task                                   # this copy holds the task already
    previous = task.holder
    forced = bool(previous) and (previous, task.holder_host) != (name, host)
    if forced and task.status != "stopped":
        if previous == name:
            raise HolderError(f"you hold the task {task.id} in another copy of the repository. Hand it off there with "
                              f"akasha handoff {task.id}, then take it over here")
        raise HolderError(f"{previous} holds the task {task.id}. Ask {previous} to hand it off with akasha handoff "
                          f"{task.id}")
    if forced:
        _examine_role(team, "developer", name)        # a stopped task waits for a developer
    start = _work_on_server(root, task) if task.branch else ""
    if start and not task.base:                       # a task of Akasha 1.0.0 can have no base
        task.base = workcopy.git(root, "merge-base", _default_ref(root), start).stdout.strip()
    task.holder, task.holder_host = name, host
    if start:
        _open_workcopy(root, team, task, start)
    _publish(root, task)
    if forced:
        board.comment(root, task.board, f"@{previous} Akasha: {name} took over the stopped task {task.id} "
                                        f"({task.title}). A work copy of the task on your computer stays there: "
                                        "examine it, then remove it.")
    return task
