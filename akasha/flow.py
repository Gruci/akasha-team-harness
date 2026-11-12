"""The steps of a task before the landing: start, preview, plan review, checks, and the review of the result. Also
the steps between people: resume, hand off, cancel, and ask an administrator for what only they can do."""

from __future__ import annotations

import html
import os
import sys
import time
import webbrowser
from pathlib import Path

from collections.abc import Iterable

from akasha import (agent, approval, archive, board, checks, codemap, config, consistency, core, definitions, evidence,
                    forms, guard, pr, product, quick, repo, review, screen, sheets, spec, trace, version, work)
from akasha.config import Team
from akasha.task import (PLAN, PREVIEW, SUMMARY, TASK_ID, Task, all_local, digest, forget, load, new_id,
                         own_records, record, records, replaced, save)
from akasha.task import outside as task_outside

STUCK = 3                      # failed checks in a row before Akasha suggests to ask an administrator
DECISIONS = 'id="akasha-decisions"'       # the box of the questions and the answers of the person, in the preview
QUICK = "quick"                            # the check that the change of a quick task is a quick change
DATA = "data"                              # the check that a change of data has the values of its preview defined
GATE = "gate"                              # the check that the person approved and the plan passed its review


def rules(root: Path) -> Team:
    """The team rules on the default branch as git fetched it last."""
    return config.shared(root, repo.default_branch(root))


def gate(task: Task) -> str:
    """What the task still needs before its code can change, or "" when it is ready to build. A quick task changes
    its code first: its review and its approval come after the change (quick.missing). An agent task has no preview:
    the request of the person decides what to make, and the person approves the result before the merge (agent.py).
    A task without a screen has no preview either: the person approves its plan after the review (screen.py)."""
    if agent.is_agent(task):
        if not record(task, agent.REQUEST).is_file():
            return (f"The request of the person is missing: {records(task)}/{agent.REQUEST}. Cancel the task, and "
                    "start it again right after the prompt of the request.")
        return _unreviewed(task)
    if quick.is_quick(task):
        return ""
    if screen.is_no_screen(task):
        return _plan_step(task)
    if task.status == "preview" or not task.approval:
        return (f"The person did not approve its preview yet. Write the preview at {records(task)}/{PREVIEW}, "
                f"show it with `akasha preview {task.id}`, and ask the person in the chat. When their own message "
                f"approves it, run `akasha approve {task.id}` (an answer in a choice tool such as AskUserQuestion is "
                "not a message of the person).")
    if digest(record(task, PREVIEW)) != task.approval.get("preview_sha"):
        return f"The preview changed after the approval. Show it again with `akasha preview {task.id}`."
    return _unreviewed(task)


def _unreviewed(task: Task) -> str:
    """What the plan of the task still needs from the akasha-reviewer agent, or ""."""
    if review.passed(task):
        return ""
    return (f"The plan did not pass the review. Write {records(task)}/{PLAN} (the approach, and the work as steps), "
            f"ask the akasha-reviewer agent to review the plan of task {task.id}, and repair the plan until it "
            "passes." + review.told(task))


def _plan_step(task: Task) -> str:
    """What a task without a screen still needs before the build, or "": the review of its plan, then the approval
    of that plan by the person. A change of the plan after the approval needs both again."""
    missing = _unreviewed(task)
    if missing:
        return missing
    now = review.plan_digest(task)
    if task.approval.get("plan_sha") == now:
        return ""
    if task.status != "preview" or not task.shown_at or task.preview_sha != now:
        return (f"The person did not approve this plan yet. Show it with `akasha preview {task.id}`, then ask the "
                "person in the chat.")
    if time.time() - task.shown_at > approval.MAX_AGE:
        return f"The person saw the plan more than a day ago. Show it again: `akasha preview {task.id}`."
    return (f"Wait for the message of the person. When it approves the plan, run `akasha approve {task.id}`; else "
            "change the plan as the person tells, and ask the akasha-reviewer agent again.")


def next_step(task: Task) -> str:
    """The next step of the task, for the agent engine."""
    if task.status == "merged" and task.checks.get("merge"):
        return f"Wait for the deployment: `akasha land {task.id} --wait 540` (shell timeout 600000 ms)."
    if task.status in ("merged", "closed"):
        return f"The task is {task.status}."
    if task.status == "landing":
        return _agent_landing(task) if agent.is_agent(task) else \
            f"Wait for the merge: `akasha land {task.id} --wait 540` (shell timeout 600000 ms)."
    if quick.is_quick(task):
        return _quick_step(task)
    if screen.is_no_screen(task) and (waits := _plan_step(task)):
        return waits
    if task.status == "preview":
        if not forms.written(record(task, PREVIEW)):
            return (f"Ask the person only what changes the result and what you cannot decide. Then write the preview "
                    f"at {records(task)}/{PREVIEW}: the decisions, the look (an HTML mockup of the screen, or a diagram "
                    "of the flow and the data), the values from data with their source and formula, and the rules "
                    "with an example each (akasha-build step 2).")
        if not task.shown_at or digest(record(task, PREVIEW)) != task.preview_sha:
            return f"Show the preview: `akasha preview {task.id}`."
        if time.time() - task.shown_at > approval.MAX_AGE:
            return f"The person saw the preview more than a day ago. Show it again: `akasha preview {task.id}`."
        return (f"Wait for the message of the person. When it approves the preview, run `akasha approve {task.id}`; "
                "else change the preview as the person tells.")
    missing = gate(task)
    if missing:
        return missing
    waiting = pending(task)
    if waiting:
        listed = ", ".join(f"{part['name']} ({part['workcopy']})" for part in waiting)
        return (f"The workers build in the parts: {listed}. When each one is done, run `akasha join {task.id}`, then "
                f"`akasha check {task.id}`.")
    tree = Path(task.workcopy)
    if work.dirty(tree) or task.checks.get("commit") != work.head(tree):
        return f"Build the change in {task.workcopy}, then run `akasha check {task.id}`." + _steps_line(task)
    if review.result_needed(task) and not review.result_passed(task):
        return (f"Ask the akasha-reviewer agent, in a new context, to review the result of task {task.id} (result "
                f"digest {review.result_digest(task)}): it reads the change against the preview and the plan. Repair "
                f"what it finds, run `akasha check {task.id}`, and ask again until it passes."
                + review.result_told(task))
    if not record(task, SUMMARY).is_file():
        what = ("the problem, the cause, what changed, what other areas it reaches, and how to undo it when a revert "
                "is not enough" if agent.is_agent(task) else
                "why, what changed, how to undo it when a revert is not enough")
        return (f"Write {records(task)}/{SUMMARY} ({what}), run `akasha check {task.id}` again, then `akasha land "
                f"{task.id}`.")
    return f"Land the task: `akasha land {task.id} --wait 540` (shell timeout 600000 ms)."


def _steps_line(task: Task) -> str:
    """How far the build is, and its next step, from the steps of the plan and the change (steps.py). "" without
    steps."""
    from akasha import steps
    tree = Path(task.workcopy)
    try:
        found = steps.parse(_text(record(task, PLAN)))
        said = steps.line(found, tree, checks.changed_files(tree, quick.base(tree))) if found else ""
    except (RuntimeError, OSError):
        said = ""
    return f" {said[0].upper()}{said[1:]}." if said else ""


def _agent_landing(task: Task) -> str:
    """The next step of an agent task in its landing: the merge waits for the approval of the result."""
    now = agent.digest(task)
    land_again = f"`akasha land {task.id} --wait 540` (shell timeout 600000 ms)"
    if not agent.missing(task):
        return f"Land the task: {land_again}."
    if task.shown_at and task.preview_sha == now:
        return (f"Wait for the message of the person: the relay gives it as the next prompt. When it approves the "
                f"result, run `akasha approve {task.id}`, then {land_again}; else change the work as the person tells.")
    return (f"Wait for the checks and the merge: {land_again}. When it says ASK, run `akasha result {task.id}`, give "
            "its text as your whole answer, and end the turn.")


def _quick_step(task: Task) -> str:
    tree = Path(task.workcopy)
    if not quick.changes(tree, quick.base(tree), own_records(task)):
        return (f"Make the change in {task.workcopy}. A quick change only changes existing files that no other area "
                "uses.")
    now = quick.digest(task)
    if not now:
        return (f"Write {records(task)}/{quick.IMPACT}: each changed file, which screens use it, and why no other "
                "screen changes.")
    if not quick.reviewed(task, now):
        return (f"Ask the akasha-reviewer agent to review the change of the quick task {task.id} (change digest "
                f"{now}), and repair the change until it passes." + review.told(task))
    if not task.approval or task.approval.get("change_sha") != now:
        if task.status == "preview" and task.shown_at and quick.shown_change(task) == now:
            return (f"Wait for the message of the person. When it approves the change, run `akasha approve "
                    f"{task.id}`; else change it as the person tells.")
        return f"Show the change to the person: `akasha preview {task.id}`, and ask in the chat."
    if work.dirty(tree) or task.checks.get("commit") != work.head(tree):
        return f"Run `akasha check {task.id}`."
    if not record(task, SUMMARY).is_file():
        return (f"Write {records(task)}/{SUMMARY} (why, what changed, how to undo it when a revert is not enough), "
                f"run `akasha check {task.id}` again, then `akasha land {task.id}`.")
    return f"Land the task: `akasha land {task.id} --wait 540` (shell timeout 600000 ms)."


def _name_taken(root: Path, task: Task, branch: str, entries: list[board.Entry], online: bool) -> bool:
    """True when the name of the task is in use by a task that is open: on this computer, on the board, or on the
    server. A merged task of the same name does not hold the name: its records are in the archive under their date,
    and Akasha does not read the archive to find a name."""
    if any(other.id == task.id for other in all_local(root)) or \
            repo.git(root, "rev-parse", "-q", "--verify", f"refs/heads/{task.branch}").returncode == 0:
        return True
    if any(entry.task.id == task.id or entry.branch == task.branch for entry in entries):
        return True
    return online and repo.git(root, "ls-remote", "--exit-code", "origin",
                               f"refs/heads/{task.branch}").returncode == 0


def start(root: Path, title: str, name: str = "", scope: tuple[str, ...] = (),
          fast: bool = False, no_screen: bool = False) -> tuple[Task, list[str]]:
    """Record a new task: a work copy on a new branch from the latest default branch, and a draft pull request on
    the board. Return the task and the other tasks that plan the same files. `fast` makes a quick task, and
    `no_screen` a task without a screen of an administrator, whose plan the person approves (screen.py). An agent
    account always makes an agent task, from the last prompt of its session (agent.py)."""
    branch = repo.default_branch(root)
    online = board.available(root)
    if online and repo.fetch(root, branch).returncode:
        raise RuntimeError(f"git cannot fetch {branch} from origin. Examine the network and the GitHub login of git")
    team = rules(root)                                 # the rules after the fetch: a raise of the version counts now
    old = version.mismatch(team.version, root=root)    # an Akasha of another version runs other rules than the server
    if old:
        raise ValueError(old)
    owner = (repo.me(root) if online else "") or repo.person(root, kept=False)
    patterns = [config.pattern(item) for item in scope]
    if no_screen:
        if fast:
            raise ValueError("a quick task has no plan: start a task without a screen without --quick")
        problem = screen.start_problem(team, owner, patterns, repo.paths(root, team.record_roots))
        if problem:
            raise ValueError(problem)
    request = _request(root, team, owner, fast)
    task = Task(id=new_id(title, name), title=title.strip(), scope=patterns, records_dir=team.records_dir,
                kind="agent" if request else "quick" if fast else screen.KIND if no_screen else "full")
    task.branch = team.branch_prefix + task.id
    task.records_name = task.id
    entries = board.read(root) if online else []
    if entries is None:
        raise RuntimeError("gh cannot read the board. Log in to GitHub: gh auth login. Then do the step again")
    if _name_taken(root, task, branch, entries, online):
        raise ValueError(f"the name {task.id} is in use by another task, now or before. Give another name with --name")
    task.owner = owner
    if request:
        task.status = "approved"                      # no preview: the request decides what to make
    path = root / team.work_dir / task.id
    work.exclude(root, team.work_dir)
    work.leave_out(root, team.archive_dir)            # the main checkout holds no archive either, where git allows
    task.base = work.create(root, path, task.branch, f"origin/{branch}" if online else "HEAD",
                            archive=team.archive_dir)
    task.workcopy = str(path)
    record(task, PREVIEW).parent.mkdir(parents=True, exist_ok=True)
    if request:
        agent.write_request(task, request)
    save(root, task)
    notes = [f"overlap — {line}" for line in board.overlaps(task, [], entries, team.record_roots)]
    locked = checks.touches(task.scope, checks.locked(team, task.owner))
    if locked:
        notes.append(f"admin only — the task plans {', '.join(locked[:3])}, which only an administrator changes. "
                     f"Plan without it, or ask an administrator: `akasha help {task.id} \"<what the task needs>\"`")
    # A quick task holds for each person: the core of an administrator is no quick change either
    planned = core.planned(team, path, task.scope) if fast or not core.exempt(team, task.owner) else {}
    if planned and fast:
        notes.append(f"not quick — {', '.join(f'{name} ({why})' for name, why in planned.items())}. Other areas use "
                     f"these files: run `akasha upgrade {task.id}` for a full task with a preview and a plan")
    elif planned:
        notes.append(f"core — {', '.join(f'{name} ({why})' for name, why in planned.items())}. Other areas use "
                     "these files: use what they have, and extend them when the task needs it. A change of their "
                     "existing lines waits for an approval of an administrator. Do not copy their code into a new "
                     "function to go around it")
    planned_data = [] if request or fast else checks.touches(task.scope, team.data_paths)
    if planned_data and no_screen:
        notes.append(f"data — the task plans {', '.join(planned_data[:3])}, which make data that people see. Define "
                     "each value in plan.md: its source, formula, value now, and check")
    elif planned_data:
        notes.append(f"data — the task plans {', '.join(planned_data[:3])}, which make data that people see. Mark each "
                     "value of the preview and define its source, formula, value, and check (akasha-build step 2)")
    _forms(team, task)
    task.session, task.active_at = approval.session(root, sure=True), time.time()     # the session that starts it
    save(root, task)
    try:                                              # what the repository has, before the AI plans new code
        notes += codemap.start_lines(team, path, root, task.scope, task.title)
    except (RuntimeError, OSError) as error:
        notes.append(f"map — Akasha could not read the code ({error}). `akasha map` shows it")
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


def _request(root: Path, team: Team, owner: str, fast: bool) -> str:
    """The request of the person for an agent account, or "" for a person. A person cannot make an agent task, and
    an agent account cannot make a task with a preview or a quick task: the GitHub name decides."""
    if not agent.account(team, owner):
        return ""
    if fast:
        raise ValueError("an agent account makes agent tasks only: start it without --quick")
    request = agent.kept_request(root, approval.session(root))
    if not request:
        raise ValueError("an agent task starts from the request of a person: the last prompt of this session, in the "
                         "last ten minutes. Akasha found none. Start the task right after the prompt of the request")
    return request


def _prepare(team: Team, path: Path) -> list[str]:
    """Run the setup command of the team in a new work copy, for example npm ci."""
    if not team.setup:
        return []
    status, detail = checks.shell(team.setup, path)
    return [] if status == "PASS" else [f"note — the setup command failed in the work copy: {detail[-300:]}"]


def _simple_preview(title: str, text: str) -> str:
    lines = "".join(f"<p>{html.escape(line)}</p>" for line in text.splitlines() if line.strip())
    return (f'<!doctype html><html><meta charset="utf-8"><title>{html.escape(title)}</title>'
            f'<body style="font-family:sans-serif;max-width:720px;margin:40px auto;line-height:1.6">'
            f'<h1>{html.escape(title)}</h1><section id="akasha-decisions">{lines}</section></body></html>\n')


def _quick_preview(root: Path, task: Task) -> None:
    """Make the preview of a quick task from its change. The change must be a quick one, with impact.md and a review
    that passed, or of only text for people (quick.needs_review)."""
    tree = Path(task.workcopy)
    found = quick.problems(rules(root), tree, quick.base(tree), own=own_records(task))
    if found:
        raise ValueError("this is not a quick change: " + "; ".join(found[:5]) + f". Run `akasha upgrade {task.id}`")
    now = quick.digest(task)
    if not now:
        raise ValueError(f"write {records(task)}/{quick.IMPACT} first: each changed file, which screens use it, and "
                         "why no other screen changes")
    if not quick.reviewed(task, now):
        raise ValueError(f"the akasha-reviewer agent did not pass this version of the change (digest {now}) yet")
    path = record(task, PREVIEW)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(quick.preview_text(task), encoding="utf-8")


def preview(root: Path, task_id: str, text: str = "", show: bool = True) -> tuple[Task, str]:
    """Show the preview to the person and wait for the approval. A preview that changed after an approval needs a new
    approval. `text` makes a plain preview for a change without a screen, when the file is not there."""
    task = load(root, task_id)
    holder = taken(root, task)
    if holder:
        raise ValueError(f"@{holder} holds task {task.id} now. Run `akasha tidy` to remove the copy on this computer")
    if screen.is_no_screen(task):
        return _show_plan(root, task)
    path = record(task, PREVIEW)
    if quick.is_quick(task):
        _quick_preview(root, task)
    if text and not forms.written(path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_simple_preview(task.title, text), encoding="utf-8")
    if not forms.written(path):
        raise ValueError(f"write the preview first: {path}" + (" (fill the form, and delete its first line)"
                                                              if path.is_file() else ""))
    _examine_preview(root, task, path)
    sha = digest(path)
    changed = bool(task.approval) and task.approval.get("preview_sha") != sha
    if changed:
        task.approval, task.status = {}, "preview"
        evidence.forget(task)
    # Claude Code gives its commands the session: only a message of that session, after now, approves this preview
    task.preview_sha, task.shown_at, task.shown_in = sha, time.time(), approval.session(root)
    task.heard = {}
    save(root, task)
    if board.available(root) and task.number:
        # Only a record: no run of the CI. The push of the checks and the push of the landing run it
        work.commit(Path(task.workcopy), f"akasha: preview of {task.title} [skip ci]")
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


def preview_check(root: Path, task_id: str) -> str:
    """`akasha preview <task> --check`: examine the preview as `akasha preview` does, and change nothing: no state
    of the task, no commit, no push, and nothing is shown. A step in a new context uses it; the main session then
    runs `akasha preview`, which examines it again and shows it to the person."""
    task = load(root, task_id)
    if quick.is_quick(task) or screen.is_no_screen(task) or agent.is_agent(task):
        raise ValueError(f"task {task.id} has no preview to write: {next_step(task)}")
    path = record(task, PREVIEW)
    if not forms.written(path):
        raise ValueError(f"write the preview first: {path}" + (" (fill the form, and delete its first line)"
                                                              if path.is_file() else ""))
    _examine_preview(root, task, path)
    return (f"The preview {path} passes its check. The main session shows it to the person: `akasha preview "
            f"{task.id}`.")


def brief(root: Path, task_id: str) -> str:
    """`akasha status <task> --brief`: one screen for a step in a new context and for the main session that leads
    the steps. The kind, the paths, the next step, the digest of the input of the review, what stops the task, and
    the guides of the team. Long texts stay in the records: it names their path."""
    task, team = load(root, task_id), rules(root)
    sha = review.subject_digest(task)
    lines = [f"{task.id} · {task.title} · {task.kind} · {task.status}" + (f" · {task.pr}" if task.pr else ""),
             f"work copy: {task.workcopy}", f"records: {Path(task.workcopy) / records(task)}",
             f"next: {next_step(task)}"]
    if sha:
        said = task.review.get("verdict") if task.review.get("plan_sha") == sha else "no review of this version"
        lines.append(f"review: {said} · digest {sha}"
                     + (f" · the answer is in {record(task, review.REVIEW)}" if task.review else ""))
    stops = "" if task.status in ("merged", "closed", "landing") else gate(task)
    if stops:
        lines.append(f"stops: {stops}")
    failed = [name for name, status in (task.checks.get("status") or {}).items() if status == "FAIL"]
    if failed:
        lines.append(f"failed checks: {', '.join(failed)} (run `akasha check {task.id}` for the text)")
    if task.status not in ("merged", "closed", "landing", "preview") and not stops:
        said = _steps_line(task).strip()
        if said:
            lines.append(said[0].lower() + said[1:].rstrip("."))
        if review.result_needed(task) and task.result:
            now = review.result_digest(task)
            said = task.result.get("verdict") if task.result.get("sha") == now else "no review of this code"
            lines.append(f"result: {said} · digest {now} · the answer is in {record(task, review.RESULT)}")
    names = {"preview": "before the preview", "plan": "before the plan", "build": "while you build",
             "review": "for the reviewer"}
    lines += [f"guides {names[step]}: {', '.join(files)}" for step, files in team.guides.items() if step in names]
    if team.models:
        lines.append("models — " + " · ".join(f"{step}: {name}" for step, name in team.models.items())
                     + " (start the agent of that step with this model)")
    waits = task.status == approval._wanted(task) and bool(task.shown_at)
    if not waits and task.status not in ("merged", "closed"):
        # A session that holds the whole talk can start again here: the records and this status hold the task
        lines.append(f"safe point: a new session loses nothing here. It continues with `akasha status {task.id} "
                     "--resume`")
    return "\n".join(lines)


def _examine_preview(root: Path, task: Task, path: Path) -> None:
    """The check of a preview before the person sees it: the box of the decisions, the specification (the rules,
    the values, the definitions), and the check of the team. ValueError with what to repair."""
    shown = path.read_text(encoding="utf-8", errors="replace")
    if DECISIONS not in shown:
        raise ValueError(f'the preview has no box of the decisions. At the top of {path}, add <section '
                         f'id="akasha-decisions"> with each question that you asked and the answer of the person')
    if not quick.is_quick(task):
        team = rules(root)
        found = spec.problems(shown, data_required=bool(checks.touches(task.scope, team.data_paths)))
        if found:
            raise ValueError(f"the preview {path} does not specify the change yet: " + "; ".join(found[:5]))
        if team.definitions_on:                       # each value of the screen names its definition, or is local
            found = definitions.preview_problems(shown, _definition_keys(Path(task.workcopy)))
            if found:
                raise ValueError(f"the preview {path} does not name the definition of each value: "
                                 + "; ".join(found[:5]))
        if team.preview_check:                        # the check of the team, once, before the person sees the preview
            status, detail = checks.shell(f'{team.preview_check} "{path}"', Path(task.workcopy))
            if status != "PASS":
                raise ValueError(f"the check of the preview ([preview] check) did not pass:\n{detail}")


def _show_plan(root: Path, task: Task) -> tuple[Task, str]:
    """Show the plan of a task without a screen to the person, after the akasha-reviewer agent passed it. A plan
    that changed after an approval needs a new approval."""
    if not review.passed(task):
        raise ValueError("the akasha-reviewer agent did not pass this version of the plan yet. " + _unreviewed(task))
    sha = review.plan_digest(task)
    changed = bool(task.approval) and task.approval.get("plan_sha") != sha
    if changed or not task.approval:
        task.approval, task.status = {}, "preview"
        evidence.forget(task)
    task.preview_sha, task.shown_at, task.shown_in = sha, time.time(), approval.session(root)
    task.heard = {}
    save(root, task)
    if board.available(root) and task.number:
        work.commit(Path(task.workcopy), f"akasha: plan of {task.title} [skip ci]")
        try:
            work.push(Path(task.workcopy), task.branch)
        except RuntimeError:
            pass                                      # the next push sends it
        pr.update(root, task)
    again = " The plan changed after the approval, so the person approves it again." if changed else ""
    return task, (f"The plan {record(task, PLAN)} passed the review.{again} Show it to the person in the chat: the "
                  "approach, each step with its files and its tests, the risks, and how to undo it when a revert "
                  "is not enough, with the path of plan.md. Then ask in plain chat whether to build it like this, or "
                  "what to change. "
                  f"When their own message approves it, run `akasha approve {task.id}`. Do not ask with "
                  "AskUserQuestion or another choice tool: only a message that the person types counts.")


def _subject(task: Task) -> tuple[str, Path, str]:
    """What the person approves now: its kind, its file, and its digest."""
    if quick.is_quick(task):
        return "the change", record(task, PREVIEW), quick.digest(task)
    if agent.is_agent(task):
        return "the result", record(task, SUMMARY), agent.digest(task)
    if screen.is_no_screen(task):
        return "the plan", record(task, PLAN), review.plan_digest(task)
    return "the preview", record(task, PREVIEW), digest(record(task, PREVIEW))


def confirm_here(task: Task, ask=input, shown=print, terminal=None) -> None:
    """The approval of a person in their own terminal, where the agent engine has no hook for their message:
    show what they approve, and take the name of the task that they type. ValueError when this is no terminal,
    the name is another one, the input ends, or the subject changed while the person read: then nothing is
    written. It sees only that a terminal is there. It does not prove that a person typed."""
    is_terminal = sys.stdin.isatty() if terminal is None else terminal
    if not is_terminal:
        raise ValueError("`akasha approve <task> --here` is for the person, in their own terminal. The shell of an "
                         "agent engine is no terminal: ask the person to run it")
    what, path, before = _subject(task)
    if not before:
        raise ValueError(f"{what} of task {task.id} is not there yet")
    shown(f"Task: {task.title} ({task.id})\nWork copy: {Path(task.workcopy).resolve()}\nBranch: {task.branch}\n"
          f"You approve {what}: {path.resolve()}\nDigest: {before}\n"
          f"To approve it as it is, type the name of the task ({task.id}) and press Enter. Anything else "
          "approves nothing.")
    try:
        typed = ask("> ").strip()
    except (EOFError, KeyboardInterrupt):
        raise ValueError("nothing was typed: no approval") from None
    if typed != task.id:
        raise ValueError(f"the name of the task is {task.id}: no approval")
    if _subject(task)[2] != before:
        raise ValueError(f"{what} changed while you read it: no approval. Look at it again")


def approve(root: Path, task_id: str, here: bool = False, **terminal) -> tuple[Task, str]:
    """Record the approval of the person from their last message after the preview, in this session. `here`: the
    person approves in their own terminal (confirm_here), for an agent engine without a hook for their words."""
    task = load(root, task_id)
    if here:
        confirm_here(task, **terminal)
    change = quick.digest(task) if quick.is_quick(task) else ""
    if quick.is_quick(task) and (not change or quick.shown_change(task) != change):
        raise ValueError(f"the change moved after the person saw it. Show it again with `akasha preview {task.id}` "
                         "and ask again")
    outcome = agent.digest(task) if agent.is_agent(task) else ""
    if screen.is_no_screen(task):
        if not review.passed(task):
            raise ValueError("the plan changed after its review. " + _unreviewed(task))
        outcome = review.plan_digest(task)
    problem = approval.approve(root, task, approval.session(root), outcome, typed=here)
    if problem:
        raise ValueError(problem)
    if change:
        task.approval["change_sha"] = change
        save(root, task)
    evidence.keep(task)                               # the server reads the approval from the records
    if task.kind == "full":                           # the frame of the next step: the plan
        forms.put(record(task, PLAN), forms.PLAN)
    if board.available(root) and task.number:
        pr.update(root, task)
    if screen.is_no_screen(task):
        return task, (f"Recorded the approval of the plan by {task.approval['by']}: \"{task.approval['words']}\". "
                      "Next, without stopping: build each step of the plan, run `akasha check`, ask the "
                      "akasha-reviewer agent to review the result, write summary.md, and run `akasha land`. A change "
                      "of the plan after now needs a new review and a new approval.")
    if outcome:
        return task, (f"Recorded the approval of {task.approval['by']}: \"{task.approval['words']}\". Next, without "
                      f"stopping: run `akasha land {task.id} --wait 540` (shell timeout 600000 ms). A change of the "
                      "code or of summary.md after now needs a new approval.")
    if change:
        return task, (f"Recorded the approval of {task.approval['by']}: \"{task.approval['words']}\". Next, without "
                      f"stopping: run `akasha check {task.id}`, write summary.md, check again, and run `akasha land`. "
                      "A change of the code after now needs a new review and a new approval.")
    return task, (f"Recorded the approval of {task.approval['by']}: \"{task.approval['words']}\". Do not ask the person "
                  "anything more unless the plan must change what they approved. Next, without stopping: write "
                  "plan.md in the records folder of the task (the work as steps), ask the akasha-reviewer agent to "
                  "review the plan until it passes, build each step, run `akasha check`, ask the akasha-reviewer "
                  "agent to review the result, write summary.md, and run `akasha land`.")


def result(root: Path, task_id: str) -> str:
    """The text of the result of an agent task for the person, when the landing asked for it (ASK): the checks of
    GitHub passed on this work. Only a message of this session, after now, approves it."""
    task = load(root, task_id)
    if not agent.is_agent(task):
        raise ValueError(f"task {task.id} is not an agent task: its person approves a preview (`akasha preview "
                         f"{task.id}`)")
    tree = Path(task.workcopy)
    if task.status != "landing" or task.checks.get("asked") != work.head(tree) or work.dirty(tree):
        raise ValueError(f"the landing did not ask for this work yet. Run `akasha land {task.id} --wait 540`: it asks "
                         "when the checks of GitHub passed")
    text = agent.show(root, task, approval.session(root))
    save(root, task)
    if board.available(root) and task.number:
        pr.update(root, task)
    return text


def self_review(root: Path, task_id: str, verdict: str) -> Task:
    """Record a review that the agent engine did itself, where the agent engine has no reviewer agent. The pull
    request tells that it was not the reviewer agent."""
    if os.environ.get("CLAUDECODE") == "1":
        raise ValueError("Claude Code has the akasha-reviewer agent: ask it to review the plan")
    if rules(root).review_command:
        raise ValueError("the team has a reviewer command ([review] command): run `akasha review <task>` without "
                         "--verdict. A review of the agent engine itself does not count here")
    task = load(root, task_id)
    if review.result_needed(task) and review.passed(task) and task.checks.get("commit") == work.head(
            Path(task.workcopy)) and not work.dirty(Path(task.workcopy)):
        # The plan passed and the checks passed on this work: the review is of the result
        sha = review.result_digest(task)
        if task.result.get("source") == "reviewer" and task.result.get("sha") == sha:
            raise ValueError("the reviewer agent already judged this result: repair it")
        review.note_result(root, task, verdict, sha, "self")
        review.keep_result(task, "The agent engine reviewed the result itself: it has no reviewer agent.")
        return task
    sha = review.subject_digest(task)
    if not sha:
        raise ValueError(f"write {record(task, quick.IMPACT)} first" if quick.is_quick(task) else
                         f"write {', '.join(review.INPUTS.get(task.kind, review.INPUTS['full']))} in "
                         f"{records(task)}/ first: the review reads each of them")
    if task.review.get("source") == "reviewer" and task.review.get("plan_sha") == sha:
        raise ValueError("the reviewer agent already judged this version: repair it")
    review.note(root, task, verdict, sha, "self", read=None if quick.is_quick(task) else review.inputs(task))
    review.keep(task, task.review["verdict"], sha, "The agent engine reviewed it itself: it has no reviewer agent.")
    return task


def check(root: Path, task_id: str, only: tuple[str, ...] = ()) -> tuple[checks.Result, list[str]]:
    """Run the checks of the team in the work copy. When each check passes, save the work as a commit and push it.
    A task that is not ready to build gets no commit: where no hook stops an edit, this is the first place that asks
    for the approval of the person and the review of the plan. One check alone (`only`) makes no commit, and runs."""
    team, task = rules(root), load(root, task_id)
    # Before the commit: a task of another session stops here too, where no hook stops an edit
    taken_by = "" if only else guard.other_session(task, approval.session(root)) if task.session else ""
    missing = archive.sync(root, team, task) or taken_by or ("" if only else gate(task))
    if missing:
        return checks.Result({GATE: "FAIL"}, {GATE: missing}), []
    tree = Path(task.workcopy)
    work.add_all(tree)                   # some checks list the files with git ls-files: new files must be in the index
    if not only and _only_records(task, tree):
        # The checks passed on this code, and only the records changed since (summary.md, the answer of a review):
        # no check of the team runs again, here or on the server: the push of the landing runs the CI
        work.commit(tree, f"akasha: records of {task.title} [skip ci]")
        task.checks = {**task.checks, "commit": work.head(tree), "at": time.strftime("%Y-%m-%d %H:%M")}
        notes = ["note — only the records of the task changed since the checks passed: Akasha saved them, and ran "
                 "no check again"]
        if board.available(root) and task.number and not taken(root, task):
            try:
                work.push(tree, task.branch)
            except RuntimeError as error:
                notes.append(f"note — {error}. The landing pushes again")
            pr.update(root, task)
        save(root, task)
        return checks.Result(dict(task.checks.get("status") or {}), {}), notes
    before = set(work.untracked(tree))
    # The changes of the task only: after a merge of the default branch, its newer files are not changes of the task
    base = repo.git(tree, "merge-base", "HEAD", f"origin/{repo.default_branch(root)}").stdout.strip() or task.base
    changed = checks.changed_files(tree, base)
    result = checks.run(team, tree, changed, only)
    advice: list[str] = []
    maps = codemap.Pair(tree, team, root, base)       # the code now and before: each check of the product reads them
    admin = core.exempt(team, repo.me(root, kept=True))
    plan = None if quick.is_quick(task) else _text(record(task, PLAN))
    if not only or consistency.CHECK in only:         # before the commit: new code that the repository has already
        held = consistency.Found([], [])
        try:
            found = consistency.examine(team, tree, base, root, plan, admin=admin, found_out=held, maps=maps)
            if not only:                              # the board tells the other tasks which definitions it holds
                task.defs = {key: value for key, value in (("adds", held.added), ("changes", held.changed)) if value}
        except (RuntimeError, OSError) as error:
            found = ("FAIL", f"Akasha could not compare the code: {error}", [])
        result.status[consistency.CHECK], result.details[consistency.CHECK], advice = found
    page = record(task, PREVIEW)
    shown = _text(page) if task.kind == "full" and forms.written(page) else None
    status, details, found_notes = product.run(product.Change(team, tree, base, changed, maps, admin, plan, shown,
                                                              own_records(task)), only)
    result.status.update(status)
    result.details.update(details)
    advice += found_notes
    if not only:
        real, why = product.integration(team, changed, result.status)
        if real != "NOT_NEEDED":
            result.status[product.INTEGRATION], result.details[product.INTEGRATION] = real, why
    me = repo.me(root, kept=True)
    locked = checks.locked_files(team, me, changed, own_records(task))
    moved = "" if only else checks.folders_problem(team, tree, f"origin/{repo.default_branch(root)}")
    if moved:
        result.status[checks.FOLDERS], result.details[checks.FOLDERS] = "FAIL", moved
    if quick.is_quick(task) and not only:
        found = quick.problems(team, tree, base, own=own_records(task))
        result.status[QUICK] = "FAIL" if found else "PASS"
        result.details[QUICK] = ("this is not a quick change: " + "; ".join(found[:5]) + f". Run `akasha upgrade "
                                 f"{task.id}` for a full task with a preview and a plan") if found else ""
    if screen.is_no_screen(task) and not only:
        found = screen.problems(team, changed, own_records(task))
        result.status[screen.CHECK] = "FAIL" if found else "PASS"
        result.details[screen.CHECK] = ("a task without a screen changes no file that makes a screen: "
                                        + "; ".join(found[:5]) + f". Undo these changes, or cancel task {task.id} and "
                                        "start it again with a preview") if found else ""
    # The plan of a task without a screen defines its values, and the reviewer judges them (screen.py)
    touched = [] if only or quick.is_quick(task) or agent.is_agent(task) or screen.is_no_screen(task) else \
        checks.touches(changed, team.data_paths)
    if touched:
        page = record(task, PREVIEW)
        found = spec.value_problems(page.read_text(encoding="utf-8", errors="replace") if page.is_file() else "", True)
        result.status[DATA] = "FAIL" if found else "PASS"
        result.details[DATA] = (f"the change touches {', '.join(touched[:5])}, which make data: "
                                + "; ".join(found[:5]) + f". Repair the preview, show it again with `akasha preview "
                                f"{task.id}`, and ask the person again") if found else ""
    if locked:
        result.status[checks.ADMIN_ONLY] = "FAIL"
        result.details[checks.ADMIN_ONLY] = (
            f"only an administrator changes {', '.join(locked[:5])}. Undo these changes in the task, or ask an "
            f"administrator: `akasha help {task.id} \"<what the task needs there>\"`")
    notes = list(advice)
    first = "" if only else _first_area(team, tree, base)
    if first:
        notes.append(first)
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
            notes.append(f"{task.failures} failed checks in a row. Read the first failure again: its message tells "
                         "what to change. When you cannot repair it, tell the person in simple words what blocks the "
                         "task. An administrator takes only what is theirs: when the check itself is broken for each "
                         f"task, `akasha help {task.id} \"<which check, and how it fails>\"`")
    elif checks.passed(result.status) and not only:
        work.commit(tree, task.title)
        task.failures = 0
        found = {} if core.exempt(team, me) else {**core.changed(team, tree, base), **sheets.changed(team, tree, base)}
        task.checks = {"status": result.status, "commit": work.head(tree), "at": time.strftime("%Y-%m-%d %H:%M"),
                       **({"core": found} if found else {}), **({"first_area": first} if first else {})}
        if found:
            notes.append(f"core — the task changes {', '.join(found)}: existing lines of code that other areas use, "
                         "or the map of the product. The landing waits for an approval of an administrator, and "
                         "Akasha asks for it. Do not copy the code into a new function to go around the approval")
        holder = taken(root, task)
        if holder:
            notes.append(f"note — @{holder} holds task {task.id} now, so Akasha did not push. Run `akasha tidy`")
        elif board.available(root) and task.number:
            try:
                work.push(tree, task.branch)
            except RuntimeError as error:
                notes.append(f"note — {error}. The landing pushes again")
            pr.update(root, task)
    save(root, task)
    return result, notes


def _only_records(task: Task, tree: Path) -> bool:
    """True when the checks passed on a commit of the task, and the work copy differs from that commit only in the
    records of the task."""
    passed = str(task.checks.get("commit") or "")
    if not passed or not checks.passed(task.checks.get("status") or {}) or \
            repo.git(tree, "cat-file", "-e", f"{passed}^{{commit}}").returncode:
        return False
    try:
        moved = checks.changed_files(tree, passed)
    except RuntimeError:
        return False
    own = own_records(task)
    return bool(moved) and all(not task_outside(path, own) for path in moved)


def touch(root: Path, tasks: list[Task], session: str, paths: Iterable[Path] = (), line: str = "") -> None:
    """The session of a task was active: it edited the work copy, or named the task in a command of Akasha. Only
    the session that holds the task counts: another one never becomes its session this way. A subagent has the
    session of the main agent (measured with Claude Code 2.1.322: the same session_id, with an agent_id), so its
    work counts as the work of the session."""
    words = line.split()
    for task in tasks:
        if task.session != session or not task.workcopy:
            continue
        if task.id in words or any(repo.inside(path, Path(task.workcopy)) for path in paths):
            task.active_at = time.time()
            try:
                save(root, task)
            except (RuntimeError, OSError):
                pass


def take(root: Path, task_id: str, here: bool = False, terminal: bool | None = None) -> tuple[Task, str]:
    """`akasha status <task> --resume`: this session works on the task from now on. The session that held it
    before is stopped at its next edit. `here`: the person runs it in their own terminal, for an agent engine
    without hooks: the terminal is the session.

    A preview (or a result) that another session showed waits for the words of the person in that session: this
    one shows it again, else the approval of the person here would not be recorded."""
    task = load(root, task_id)
    if here:
        if not (sys.stdin.isatty() if terminal is None else terminal):
            raise ValueError("`akasha status <task> --resume --here` is for the person, in their own terminal")
        mine = f"terminal-{os.getpid()}-{int(time.time())}"
    else:
        mine = approval.session(root, sure=True)
        if not mine:
            raise ValueError("Akasha cannot tell which session this is (the agent engine named none, or two sessions "
                             "ran this command at the same moment). Run it again; without hooks, the person runs "
                             f"`akasha status {task.id} --resume --here` in their own terminal")
    return _link(root, task, mine)


def _link(root: Path, task: Task, session: str) -> tuple[Task, str]:
    """Tie the task to a session. The resume from another computer uses it too."""
    was = task.session
    task.session, task.active_at = session, time.time()
    again = ""
    if task.status == approval._wanted(task) and task.shown_at and task.shown_in != session:
        task.shown_at, task.shown_in, task.heard = 0.0, "", {}
        what, command = approval.shown(task)
        again = (f" The {what} was shown in another session: show it here with `{command}`, then ask the person. "
                 "Only then their words approve it.")
    save(root, task)
    moved = " The session that held it before is stopped at its next edit." if was and was != session else ""
    return task, f"Task {task.id} continues in this session.{moved}{again} next: {next_step(task)}"


def _forms(team: Team, task: Task) -> None:
    """Write the frames of the first records of a new task, by its kind (forms.py)."""
    if quick.is_quick(task):
        forms.put(record(task, quick.IMPACT), forms.IMPACT)
    elif task.kind == "full":
        words = []
        if team.definitions_on:
            try:
                listed = definitions.parse(_text(definitions.place(Path(task.workcopy))))
            except ValueError:
                listed = []
            words = [(item.label, item.aliases) for item in
                     definitions.touching(listed, task.scope, task.title, checks.matches)]
        forms.put(record(task, PREVIEW), forms.preview(task.title, task.id, team.definitions_on, words))
    else:                                             # a task without a screen, an agent task: no preview
        forms.put(record(task, PLAN), forms.PLAN)


def _first_area(team: Team, tree: Path, base: str) -> str:
    """The notice of the task that makes the first area of the repository: its code is what the next tasks read,
    and it is no example of the team until an administrator names it."""
    try:
        areas, _folders, first = consistency.structure(team, tree, base)
    except RuntimeError:
        return ""
    if not first:
        return ""
    guide = next(iter(team.guides.get("plan", ())), "the structure guide of the team")
    return (f"note — first area ({', '.join(areas)}): the next tasks will read it. It is not an example of the team "
            f"yet. An administrator names it in {guide} after a check of its code")


def _definition_keys(tree: Path) -> list[str]:
    """The keys of the definitions in a work copy, with the ones that the task adds. [] for a file that Akasha
    cannot read: `akasha check` tells why."""
    try:
        return [item.key for item in definitions.parse(_text(definitions.place(tree)))]
    except ValueError:
        return []


def _text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


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
    if replaced(root, task):
        return ""                              # a new task took the name: its work copy and its branch stay
    tree = Path(task.workcopy)
    if any(repo.inside(Path.cwd(), Path(part["workcopy"])) for part in task.parts):
        return "the session works in a part of the task: leave that folder, then run `akasha tidy`"
    problem = _drop_parts(root, task, force and not server)
    if problem:
        return problem
    if task.workcopy and tree.is_dir():
        if repo.inside(Path.cwd(), tree):
            return f"the session works in {tree}: leave that folder, then run `akasha tidy`"
        if server and (work.unsaved(tree) or not work.contains(tree, server, task.number)):
            return (f"the work copy {tree} has changes that are not on GitHub. They stay there: start a new task for "
                    f"them, or drop them with `akasha cancel {task.id} --force`")
    problem = work.remove(root, tree, task.branch, force=force or bool(server)) if task.workcopy else ""
    if not problem:
        forget(root, task.id, task.number)
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
    repo.fetch(root, repo.default_branch(root))
    old = version.mismatch(rules(root).version, root=root)    # taking over a task is starting it on this computer
    if old:
        raise ValueError(old)
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
    # The landing of another computer can have moved the records into the archive: the work copy takes in that one
    # folder of the archive, which the branch itself names, and the task keeps it
    own = archive.of_branch(root, team, task.id, task.branch)
    work.create(root, path, task.branch, f"origin/{task.branch}", new=False, archive=team.archive_dir, own=own)
    if own:
        task.records_dir, task.records_name = team.archive_dir, own[0][len(team.archive_dir.rstrip("/")) + 1:]
    task.workcopy = str(path)
    # The session that brought the task to this computer works on it: else its first edit would stop. A session
    # that Akasha cannot tell gets no task
    mine = approval.session(root, sure=True)
    if mine:
        task.session, task.active_at = mine, time.time()
    save(root, task)
    notes = _prepare(team, path)
    if not mine:
        notes.append(f"note — Akasha cannot tell which session this is. Before the first edit: `akasha status "
                     f"{task.id} --resume`")
    pr.update(root, task)
    board.forget(root)
    return task, notes


def upgrade(root: Path, task_id: str) -> Task:
    """Make a quick task a full task: the person approves a preview of the result, and the reviewer passes a plan.
    The change so far stays in the work copy."""
    task = load(root, task_id)
    if not quick.is_quick(task):
        raise ValueError(f"task {task.id} is a full task already")
    if task.status not in ("preview", "approved"):
        raise ValueError(f"task {task.id} is {task.status}: it cannot change now")
    task.kind, task.status = "full", "preview"
    task.approval, task.review, task.checks = {}, {}, {}
    task.preview_sha, task.shown_at, task.shown_in, task.heard = "", 0.0, "", {}
    record(task, PREVIEW).unlink(missing_ok=True)               # Akasha made it from the change: not a preview
    evidence.forget(task)
    save(root, task)
    trace.note(root, "upgraded", task=task.id)
    if board.available(root) and task.number:
        pr.update(root, task)
    return task


def _overlap(one: list[str], other: list[str], files: list[str]) -> bool:
    """True when two scopes can hold the same file: a file of the work copy matches both, or a pattern matches the
    other pattern (web/** and web/new/**)."""
    if any(checks.matches(a, b) or checks.matches(b, a) for a in one for b in other):
        return True
    return any(any(checks.matches(path, a) for a in one) and any(checks.matches(path, b) for b in other)
               for path in files)


def split(root: Path, task_id: str, name: str, scope: tuple[str, ...]) -> tuple[dict, list[str]]:
    """Make a part of the task for a worker that builds at the same time as others: a work copy on this computer, on a
    local branch from the branch of the task. The part changes only the files of its scope, and no two parts have the
    same file. The person approved one preview and the reviewer passed one plan for the whole task."""
    team, task = rules(root), load(root, task_id)
    if quick.is_quick(task):
        raise ValueError("a quick task is small: build it in its work copy, without parts")
    if task.status != "approved":
        raise ValueError(f"task {task.id} is {task.status}: only a task that is ready to build has parts")
    missing = gate(task)
    if missing:
        raise ValueError(missing)
    name = name.strip().lower()
    if not TASK_ID.fullmatch(name):
        raise ValueError(f"the part name {name!r} can have only a to z, 0 to 9, and -, up to 60 characters")
    if any(part["name"] == name for part in task.parts):
        raise ValueError(f"task {task.id} already has a part {name}")
    patterns = [config.pattern(item) for item in scope if item.strip()]
    if not patterns:
        raise ValueError("give the files of the part with --scope, for example --scope \"server/**\": the parts must "
                         "not change the same files")
    tree = Path(task.workcopy)
    files = repo.paths(tree, team.record_roots)
    for part in task.parts:
        if _overlap(patterns, part["scope"], files):
            raise ValueError(f"the scope {', '.join(patterns)} has files of the part {part['name']} "
                             f"({', '.join(part['scope'])}). Give each part other files")
    branch, path = f"{task.branch}--{name}", root / team.work_dir / f"{task.id}--{name}"
    if path.exists() or repo.git(root, "rev-parse", "-q", "--verify", f"refs/heads/{branch}").returncode == 0:
        raise ValueError(f"{path} or the branch {branch} is in use. Give another name")
    work.commit(tree, f"{task.title} (before the parts)")       # the parts start from each change of the task so far
    work.create(root, path, branch, work.head(tree), archive=team.archive_dir)
    part = {"name": name, "branch": branch, "scope": patterns, "workcopy": str(path)}
    task.parts.append(part)
    save(root, task)
    trace.note(root, "split", task=task.id, part=name)
    return part, _prepare(team, path)


def _part_head(task: Task, part: dict) -> str:
    """The newest commit of the branch of a part, or "" when the branch is gone."""
    return repo.git(Path(task.workcopy), "rev-parse", "-q", "--verify", part["branch"]).stdout.strip()


def pending(task: Task) -> list[dict]:
    """The parts whose work did not join the task yet. A part that joined with `--keep` stays in `parts` with the
    commit that joined; a newer commit on its branch makes it pending again."""
    if not task.parts or not task.workcopy:
        return []
    return [part for part in task.parts if (head := _part_head(task, part)) and part.get("joined") != head]


def join(root: Path, task_id: str, keep: bool = False) -> list[str]:
    """Merge each part with new work into the work copy of the task, then remove the part (`keep` leaves it). It
    gives the parts that it merged. A conflict stops the join with the files, and the work copy stays as it was before
    that part. A part that joined earlier and stayed has no new work: it is only removed, unless `keep`."""
    task = load(root, task_id)
    if not task.parts:
        raise ValueError(f"task {task.id} has no parts")
    tree, told = Path(task.workcopy), []
    work.commit(tree, task.title)
    for part in list(task.parts):
        copy = Path(part["workcopy"])
        if copy.is_dir():
            work.commit(copy, f"{task.title} — {part['name']}")
        new = part in pending(task)
        if new:
            merged = repo.git(tree, "merge", "--no-ff", "--no-edit", "-m", f"akasha: join {part['name']}",
                              part["branch"])
            if merged.returncode:
                files = repo.names(tree, "diff", "--name-only", "--diff-filter=U")
                repo.git(tree, "merge", "--abort")
                work.restore(tree)
                save(root, task)
                trace.note(root, "join_conflict", task=task.id, part=part["name"], files=files[:10])
                raise ValueError(f"the part {part['name']} conflicts with the work copy of the task in "
                                 f"{', '.join(files) or 'some files'}. Repair it in {copy} (merge the branch "
                                 f"{task.branch} there), then run `akasha join {task.id}` again"
                                 + (f". Joined before it: {', '.join(told)}" if told else ""))
            told.append(part["name"])
        task.parts = [item for item in task.parts if item["name"] != part["name"]]
        if keep:
            part["joined"] = _part_head(task, part)       # a newer commit of the part makes it pending again
            task.parts.append(part)
        else:
            problem = work.remove(root, copy, part["branch"])
            if problem and new:
                told[-1] += f" ({problem})"
        save(root, task)
        if new:
            trace.note(root, "joined", task=task.id, part=part["name"])
    return told


def _drop_parts(root: Path, task: Task, force: bool) -> str:
    """Remove the parts of the task. A part with work that did not join stays, unless `force`."""
    for part in list(task.parts):
        copy = Path(part["workcopy"])
        joined = copy.is_dir() and not work.dirty(copy) and work.contains(copy, work.head(Path(task.workcopy)))
        if not force and copy.is_dir() and not joined:
            return (f"the part {part['name']} has work that did not join the task: run `akasha join {task.id}`, or "
                    f"drop it with `akasha cancel {task.id} --force`")
        problem = work.remove(root, copy, part["branch"], force=True)
        if problem:
            return problem
        task.parts = [item for item in task.parts if item["name"] != part["name"]]
        save(root, task)
    return ""


def _outside(task: Task) -> None:
    if task.workcopy and repo.inside(Path.cwd(), Path(task.workcopy)):
        raise ValueError(f"the session works in {task.workcopy}: leave that folder first (ExitWorktree, or cd to the "
                         "main checkout), then run the command again")


def handoff(root: Path, task_id: str) -> str:
    """Save the work on the server and free the task, so that another person or computer continues it."""
    task = load(root, task_id)
    _outside(task)
    if task.parts:
        raise ValueError(f"task {task.id} has parts on this computer: run `akasha join {task.id}` first")
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
    if tree.is_dir() and work.unsaved(tree) and not force:
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
    """Ask the administrators on the pull request of the task. GitHub tells them. An administrator keeps the rules
    and is no reviewer and no answerer: the call is for a file that only they change, for a check or a deployment
    that is broken for each task, and for a step on the server. A question about the business goes to the person
    who asked for the change."""
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
            # The branch of a merged or closed task leaves the server, so that a new task can take the name and
            # no branch piles up. GitHub does it where the repository deletes branches on a merge; an auto-merge
            # of gh does not, and a closed pull request never. GitHub keeps the commits of a closed pull request
            # with the pull request, and can restore its branch
            kept = work.delete_remote(root, task.branch, head)
            problem = drop(root, task, server=head)
            lines.append(problem or f"task {task.id} {state.lower()}: its work copy is removed")
            lines += [kept] if kept else []
        elif state == "OPEN" and (holder := _holder(root, found)):
            problem = drop(root, task, server=head)
            lines.append(problem or f"@{holder} holds task {task.id} now: the copy on this computer is removed")
    return lines


def review_names(root: Path, task: Task) -> str:
    """For the reviewer (R10): the rules for names of this task, what the names of nearby code tell, and the commands
    that show what the repository has."""
    from akasha import naming
    lines = []
    try:
        team = rules(root)
        found = codemap.Map(Path(task.workcopy), team, root)
        files = [path for path in found.files if any(checks.matches(path, item) for item in task.scope)]
        lines += naming.lines(files + list(task.scope))
        for area in codemap._areas_of(found, task.scope):
            lines += [f"names — {line}" for line in codemap.usual_words(found, area)]
        tree = Path(task.workcopy)
        start = repo.git(tree, "merge-base", "HEAD", f"origin/{repo.default_branch(root)}").stdout.strip() or task.base
        areas, folders, _first = consistency.structure(team, tree, start)
        if areas or folders:                              # a fact for R7: the machine judges nothing of it
            made = " · ".join([*(f"area {area}" for area in areas), *(f"folder {name}/" for name in folders)])
            lines.append(f"new structure: {made} (the first in the repository): judge it with the structure guide "
                         "(R7)")
    except (RuntimeError, OSError, config.ConfigError):
        lines += naming.lines(list(task.scope))
    lines.append("existing code — `akasha map <folder>` shows each public name of a folder, and `akasha find <words>` "
                 "searches names and descriptions: use them for R10 before you accept new code")
    return "\n".join(lines)
