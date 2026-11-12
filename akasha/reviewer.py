"""The reviewer command of a team: a review of a plan by another process, for an agent engine without a reviewer
agent of its own.

akasha.toml names it:

    [review]
    command = "…"      # it takes the request on its standard input, and prints the answer of the reviewer
    files = []         # the files of the repository that the command needs; none: only installed programs
    timeout = 900

`akasha review <task>` (without --verdict) runs it. The request is JSON on the standard input: an id, the task, its
kind, the subject (`plan` or `change`), the digest, the absolute paths of the work copy and of the records, the
Akasha command, the path of the instruction of the reviewer, and the base commit. Nothing of the task goes into the
text of the command.

The command runs in a new empty folder. The files of `files` come from the base commit that the request names, not
from the work copy and not from the main checkout: both can hold changes. The reviewer reads the product code at
the path of the work copy in the request.

The answer is the whole standard output: the table of the items and the mark, read by the same reader as the
answer of the akasha-reviewer agent. The mark must name the task and the digest of the request, and the digest must
still be the same when Akasha records it. A timeout, an exit code that is not zero, a missing row, or a wrong mark is
a failure: it never becomes a PASS of the agent engine itself. A team with this command takes no `akasha review
--verdict`."""

from __future__ import annotations

import json
import secrets
import subprocess
import tempfile
from pathlib import Path

from akasha import quick, repo, review
from akasha.config import Team
from akasha.flow import rules
from akasha.task import Task, load, record, records

INSTRUCTION = Path(__file__).parent / "templates" / "reviewer.md"


def request(root: Path, team: Team, task: Task, base: str, command: str) -> dict:
    """What the command gets on its standard input."""
    result = _of_result(task)
    return {"id": secrets.token_hex(8), "task": task.id, "kind": task.kind,
            "subject": "change" if quick.is_quick(task) else "result" if result else "plan",
            "digest": review.result_digest(task) if result else review.subject_digest(task),
            "workcopy": str(Path(task.workcopy).resolve()),
            "records": str((Path(task.workcopy) / records(task)).resolve()),
            "akasha": command, "instruction": str(INSTRUCTION.resolve()), "base": base}


def _of_result(task: Task) -> bool:
    """True when the review that the task needs now is of its result: the plan passed, and the checks passed on the
    work as it is."""
    from akasha import work
    if not review.result_needed(task) or not review.passed(task) or not task.workcopy:
        return False
    tree = Path(task.workcopy)
    return task.checks.get("commit") == work.head(tree) and not work.dirty(tree)


def _files(root: Path, team: Team, base: str, folder: Path) -> None:
    """Put the files of [review] files into the folder, as the base commit has them."""
    if not team.review_files:
        return
    from akasha.checks import matches
    for path in repo.paths_at(root, base):
        if any(matches(path, item) for item in team.review_files):
            shown = subprocess.run(["git", "show", f"{base}:{path}"], cwd=root, capture_output=True)
            if shown.returncode == 0:
                target = folder / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(shown.stdout)


def run(root: Path, task_id: str) -> Task:
    """Ask the reviewer command of the team, and record its verdict. ValueError when the command fails or its answer
    does not hold for the task as it is now: then nothing is recorded as a pass."""
    team, task = rules(root), load(root, task_id)
    if not team.review_command:
        raise ValueError("the team has no reviewer command ([review] command). In Claude Code, ask the akasha-reviewer "
                         "agent. Else review it yourself: `akasha review <task> --verdict pass|changes`")
    of_result = _of_result(task)
    sha = review.result_digest(task) if of_result else review.subject_digest(task)
    if not sha:
        raise ValueError(f"the records of task {task.id} are not complete yet: the review reads "
                         f"{', '.join(review.INPUTS.get(task.kind, review.INPUTS['full']))} in {records(task)}/")
    base = repo.git(root, "rev-parse", f"origin/{repo.default_branch(root)}").stdout.strip() or \
        repo.git(root, "rev-parse", "HEAD").stdout.strip()
    from akasha import hooks
    asked = request(root, team, task, base, hooks.command())
    with tempfile.TemporaryDirectory(prefix="akasha-review-") as folder:
        _files(root, team, base, Path(folder))
        try:
            done = subprocess.run(team.review_command, shell=True, cwd=folder, input=json.dumps(asked),
                                  capture_output=True, text=True, encoding="utf-8", errors="replace",
                                  timeout=team.review_timeout)
        except subprocess.TimeoutExpired:
            raise ValueError(f"the reviewer command did not answer in {team.review_timeout} seconds. Nothing is "
                             "recorded: run it again, or ask an administrator") from None
    if done.returncode:
        raise ValueError(f"the reviewer command failed (exit code {done.returncode}): "
                         f"{(done.stderr or done.stdout).strip()[-500:]}. Nothing is recorded")
    answer = done.stdout                              # all of it: the table of the items can be long
    marks = [(name.lower(), digest.lower(), verdict.upper()) for name, digest, verdict in review.MARK.findall(answer)]
    mine = [mark for mark in marks if mark[0] == task.id and mark[1] == sha]
    if not mine:
        raise ValueError(f"the answer of the reviewer command has no mark for task {task.id} and the digest {sha} "
                         "(AKASHA-REVIEW: <task> <digest> PASS or CHANGES). Nothing is recorded")
    task = load(root, task_id)
    if (review.result_digest(task) if of_result else review.subject_digest(task)) != sha:
        raise ValueError("the plan or the code changed while the reviewer read it. Nothing is recorded: run "
                         f"`akasha review {task.id}` again")
    verdict = mine[-1][2]
    if of_result:
        review.take_result(root, task, verdict, sha, "command",
                           f"The reviewer command of the team ([review] command) ran with the files of the commit "
                           f"{base}, request {asked['id']}.\n\n{answer}")
        return load(root, task_id)
    rows = review.carry(task, review.answer_rows(answer))
    found = {item: row["verdict"] for item, row in rows.items()}
    why = review.problem(task, found) if verdict == "PASS" else ""
    plan = None if quick.is_quick(task) else record(task, "plan.md").read_text(encoding="utf-8", errors="replace")
    review.note(root, task, "CHANGES" if why else verdict, sha, "command", found, why, rows, plan,
                None if quick.is_quick(task) else review.inputs(task))
    review.keep(task, task.review["verdict"], sha,
                f"The reviewer command of the team ([review] command) ran with the files of the commit {base}, "
                f"request {asked['id']}.\n\n{answer}")
    return load(root, task_id)
