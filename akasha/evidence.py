"""The evidence of a task: the approval of the person and the verdict of the review, in the records of the task.

The records go into git with the change, so the server reads the same evidence as the computer of the person:

- approval.json: `akasha approve` writes it. It holds what the person approved (the preview, the plan of a task
  without a screen, or the change of a quick task) by its digest, who, and when. Never the words of the person.
- review.md: the answer of the reviewer about the plan, with the verdict, the row of each item, and the digest of
  what it read.
- result.md: the answer of the reviewer about the result, with the digest of the change that it read.

The check `evidence` of the server (checks.ci) fails a pull request that changes product files without them, or with
evidence of an older version: a preview that changed after the approval, a plan or a preview that changed after the
review, or code that changed after the review of the result. The watch reads the same records from a merge commit.
This check stops evidence that is missing or old. It does not prove who the person was: an AI can write a file.

An agent task has no approval in its records: the person approves its result after the checks of the server passed,
and a commit for it would start them again. The landing and the watch examine that approval (agent.py)."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path

from akasha import checks, config, quick, review, screen
from akasha.config import Team
from akasha.repo import git, names
from akasha.task import PLAN, PREVIEW, Task, digest_of, outside, record, record_folders

CHECK = "evidence"
APPROVAL = "approval.json"
REQUEST = "request.md"
# A file that tells the kind of a task. A pull request that adds one to a new folder names its records
KIND_FILES = (PREVIEW, PLAN, quick.IMPACT, REQUEST)
SUBJECTS = {"full": "preview", "no-screen": "plan", "quick": "change"}
Read = Callable[[str], "bytes | None"]


def keep(task: Task) -> None:
    """Write the approval of the person into the records. An agent task has none there."""
    subject = SUBJECTS.get(task.kind)
    if not subject or not task.workcopy or not task.approval:
        return
    sha = task.approval.get({"preview": "preview_sha", "plan": "plan_sha", "change": "change_sha"}[subject], "")
    path = record(task, APPROVAL)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"schema": 1, "task": task.id, "kind": task.kind, "subject": subject, "digest": sha,
                                "by": task.approval.get("by", ""), "at": task.approval.get("at", ""),
                                "source": task.approval.get("source", "")}, ensure_ascii=False) + "\n",
                    encoding="utf-8")


def forget(task: Task) -> None:
    """The approval does not hold any more: the preview or the plan changed."""
    if task.workcopy:
        record(task, APPROVAL).unlink(missing_ok=True)


@dataclass
class Facts:
    """What the records of a task tell."""
    task: str
    kind: str = ""                     # full, no-screen, quick, agent, or "" when no file tells it
    approval: dict = field(default_factory=dict)
    review: dict = field(default_factory=dict)
    preview: str = ""                  # the digest of preview.html
    plan: str = ""                     # the digest of plan.md
    inputs: dict = field(default_factory=dict)    # the digest of each file that the review reads
    change: str = ""                   # the digest of the change of a quick task
    text_only: bool = False            # a quick task of only text for people: no review
    result: dict = field(default_factory=dict)    # what result.md tells: the review of the result
    result_now: str = ""               # the digest of the change as the pull request has it
    result_approved: bool = True       # an agent task that merged: the person approved its result


def _kind(found: set[str]) -> str:
    if quick.IMPACT in found:
        return "quick"
    if REQUEST in found:
        return "agent"
    return "full" if PREVIEW in found else "no-screen" if PLAN in found else ""


def from_records(read: Read, task: str, change: Callable[[str], str] | None = None, text_only: bool = False,
                 result_approved: bool = True, result_now: str = "") -> Facts:
    """The facts of a task from its records. `read` gives the bytes of a record: from the checkout (the server
    check), or from a commit (the watch). `change` gives the digest of the change of a quick task from its
    impact.md. `result_now`: the digest of the lines that the change adds and removes (review.change_digest)."""
    kind = _kind({name for name in KIND_FILES if read(name) is not None})
    try:
        approval = json.loads((read(APPROVAL) or b"").decode("utf-8", errors="replace") or "{}")
    except ValueError:
        approval = {}
    said = review.parse((read(review.REVIEW) or b"").decode("utf-8", errors="replace"))
    impact = (read(quick.IMPACT) or b"").decode("utf-8", errors="replace")
    return Facts(task=task, kind=kind, approval=approval if isinstance(approval, dict) else {}, review=said,
                 preview=digest_of(read(PREVIEW) or b"") if read(PREVIEW) is not None else "",
                 plan=digest_of(read(PLAN) or b"") if read(PLAN) is not None else "",
                 inputs=review.input_digests(kind, read) if kind in review.INPUTS else {},
                 change=change(impact) if kind == "quick" and change else "",
                 text_only=text_only, result_approved=result_approved,
                 result=review.parse((read(review.RESULT) or b"").decode("utf-8", errors="replace")),
                 result_now=result_now)


def problem(team: Team, facts: Facts, merged: bool = False, author: str = "") -> str:
    """Why the task lacks its evidence, or "". `merged`: the watch examines a merged pull request, where an agent
    task also needs its approved result. `author`: the account of the pull request, or "" when the run does not tell
    it; then only the rules that need no author hold."""
    task, kind = facts.task, facts.kind
    if not kind:
        return (f"the records of task {task} hold no {', '.join(KIND_FILES)}: nothing tells what the person approved")
    if kind == "agent":
        if merged and not facts.result_approved:
            return f"the person did not approve the result of the agent task {task}"
    else:
        subject = SUBJECTS[kind]
        now = {"preview": facts.preview, "plan": facts.plan, "change": facts.change}[subject]
        said = facts.approval
        again = f"show it with `akasha preview {task}`, and run `akasha approve {task}` after the person approved it"
        if not said or said.get("subject") != subject or said.get("task") != task:
            return f"the records hold no approval of the {subject} by the person ({APPROVAL}): {again}"
        if not now or said.get("digest") != now:
            return f"the {subject} changed after the person approved it: {again}"
        if kind == "no-screen" and author and not screen.allowed(team, author):
            return f"a task without a screen is a task of an administrator, and @{author} is not one"
    if kind == "quick" and facts.text_only:
        return ""                                     # only text for people: the person read all of it
    said = facts.review
    what = "change" if kind == "quick" else "plan"
    ask = f"ask the akasha-reviewer agent to review the {what} of task {task} again"
    if kind == "quick":
        now = facts.change
    else:
        missing = [name for name, sha in facts.inputs.items() if not sha]
        if missing:
            return f"the records lack {', '.join(missing)}, which the review reads: write it, then {ask}"
        now = review.combined(facts.inputs)
    if said.get("verdict") != "PASS":
        return f"the records hold no review that passed ({review.REVIEW}): {ask}"
    if said.get("digest") != now:
        files = "the change or impact.md" if kind == "quick" else ", ".join(facts.inputs)
        return f"{files} changed after the review: {ask}"
    if said.get("source") != "self":                  # the agent engine itself gives no row for each item
        why = review.problem_of(review.ITEMS["quick" if kind == "quick" else "plan"], said.get("rows") or {})
        if why:
            return f"the review in {review.REVIEW} did not pass each item ({why}): {ask}"
    if kind in review.RESULT_KINDS:
        said = facts.result
        ask = f"ask the akasha-reviewer agent to review the result of task {task} again"
        if said.get("verdict") != "PASS":
            return f"the records hold no review of the result that passed ({review.RESULT}): {ask}"
        if not facts.result_now or said.get("digest") != facts.result_now:
            return f"the code changed after the review of the result: {ask}"
        if said.get("source") != "self":
            why = review.problem_of(review.ITEMS["result"], said.get("rows") or {})
            if why:
                return f"the review in {review.RESULT} did not pass each item ({why}): {ask}"
    return ""


def own_of(team: Team, task: str, folder: str) -> tuple[str, ...]:
    """The two places of the records of a task: in work, and the folder of the archive that was chosen."""
    return tuple(dict.fromkeys((f"{team.records_dir.rstrip('/')}/{task}", folder)))


def choose(team: Team, changed: Iterable[str], branch: str, at_base: Callable[[str], bool],
           added: Iterable[str]) -> tuple[str, str, str]:
    """The records folder of the task of a pull request: (folder, task, problem). A closed rule on the paths that
    the pull request changed; it never reads the archive.

    The branch names the task. Its folder is `<records>/<task>`, or a folder of the archive whose name without the
    date is the task. Without a task branch, the folder is one where the pull request adds a file that tells the
    kind. A folder that the base has already is the folder of an earlier task: no evidence. No folder is ("", task,
    ""); more than one is a problem, and Akasha does not pick one."""
    groups = record_folders(team, changed)
    task = branch[len(team.branch_prefix):] if team.branch_prefix and branch.startswith(team.branch_prefix) else ""
    if task:
        found = [folder for folder, (name, _files) in groups.items() if name == task]
    else:
        new = set(added)
        found = [folder for folder in groups if any(f"{folder}/{name}" in new for name in KIND_FILES)]
    found = [folder for folder in sorted(found) if not at_base(folder)]
    if len(found) > 1:
        return "", task, (f"the pull request has more than one records folder of a task: {', '.join(found)}. One "
                          "pull request is one task")
    return (found[0], task or groups[found[0]][0], "") if found else ("", task, "")


def plan_of(team: Team, root: Path, base: str, changed: list[str], head: str = "") -> tuple[str | None, bool]:
    """The plan of the task of a pull request for the consistency check, from its records in the checkout: (the
    text of plan.md, or None for a quick task; True when the pull request is a task). A pull request without the
    records of a task is no task: it has no plan where an answer could be."""
    added = names(root, "diff", "--name-only", "--no-renames", "--diff-filter=A", f"{base}...HEAD")
    folder, _task, why = choose(team, changed, head, lambda path: _at(root, base, path), added)
    if why or not folder:
        return "", False
    if (root / folder / quick.IMPACT).is_file():
        return None, True
    try:
        return (root / folder / PLAN).read_text(encoding="utf-8", errors="replace"), True
    except OSError:
        return "", True


def preview_of(team: Team, root: Path, base: str, changed: list[str], head: str = "") \
        -> tuple[str | None, tuple[str, ...]]:
    """The preview of the task of a pull request, from its records in the checkout, and the folders of those records:
    (the text of preview.html, or None for a task without one; the records). The checks of the product read them."""
    from akasha import forms
    added = names(root, "diff", "--name-only", "--no-renames", "--diff-filter=A", f"{base}...HEAD")
    folder, task, why = choose(team, changed, head, lambda path: _at(root, base, path), added)
    if why or not folder:
        return None, ()
    page = root / folder / PREVIEW
    try:
        text = page.read_text(encoding="utf-8", errors="replace") if forms.written(page) else None
    except OSError:
        text = None
    return text, own_of(team, task, folder)


def _at(root: Path, commit: str, path: str) -> bool:
    return git(root, "cat-file", "-e", f"{commit}:{path}").returncode == 0


def server(team: Team, root: Path, base: str, changed: list[str], author: str = "", head: str = "") -> tuple[str, str]:
    """The evidence check of the server: PASS, FAIL and what to do, or NOT_NEEDED and why."""
    if git(root, "rev-parse", "-q", "--verify", f"{base}^{{commit}}").returncode:
        return "FAIL", f"git cannot read {base}, so Akasha cannot tell what the pull request changes"
    if config.shown(root, base) is None:
        return "NOT_NEEDED", "the pull request brings Akasha into the repository"
    added = names(root, "diff", "--name-only", "--no-renames", "--diff-filter=A", f"{base}...HEAD")
    folder, task, why = choose(team, changed, head, lambda path: _at(root, base, path), added)
    if why:
        return "FAIL", why
    own = own_of(team, task, folder) if folder else ()
    if not [path for path in changed if outside(path, own)]:
        return "NOT_NEEDED", "the pull request changes only the records of its task"
    author = author.lower()
    if author and author in team.own_procedure and not (team.branch_prefix and head.startswith(team.branch_prefix)):
        return "NOT_NEEDED", f"@{author} keeps the own procedure of the repository ([team] own_procedure)"
    if not folder or not (root / folder).is_dir():
        return "FAIL", ("this pull request changes files and is no task of Akasha: it has no records of a task. Make "
                        "the change in a task: `akasha start \"<what you want>\"`")

    def read(name: str) -> bytes | None:
        try:
            return (root / folder / name).read_bytes()
        except OSError:
            return None

    start = git(root, "merge-base", base, "HEAD").stdout.strip()
    facts = from_records(read, task, lambda impact: quick.change_digest(root, start, own, impact) if start else "",
                         quick.text_only(changed, own),
                         result_now=review.change_digest(root, start, own, "HEAD") if start else "")
    found = problem(team, facts, author=author)
    if found:
        return "FAIL", found
    locked = checks.locked_files(team, author, changed, own) if author else []
    if locked:
        return "FAIL", f"@{author} changed {locked[0]}, which only an administrator changes"
    return "PASS", ""


def merged(team: Team, root: Path, commit: str, changed: list[str], task: Task, author: str) -> str:
    """Why the task of a merge commit lacks its evidence, or "": the watch. The records come from the commit; the
    path in the block of the pull request can be old."""
    if git(root, "rev-parse", "-q", "--verify", f"{commit}^{{commit}}").returncode:
        return f"git cannot read the commit {commit[:12]}"
    branch = f"{team.branch_prefix}{task.id}"
    added = names(root, "diff", "--name-only", "--no-renames", "--diff-filter=A", f"{commit}^1", commit)
    folder, name, why = choose(team, changed, branch, lambda path: _at(root, f"{commit}^1", path), added)
    if why:
        return why
    if not folder:
        return f"the merge holds no records of task {task.id}"
    own = own_of(team, name, folder)

    def read(record_name: str) -> bytes | None:
        shown = git(root, "show", f"{commit}:{folder}/{record_name}")
        return shown.stdout.encode("utf-8") if shown.returncode == 0 else None

    facts = from_records(read, name, lambda impact: quick.change_digest(root, f"{commit}^1", own, impact, commit),
                         quick.text_only(changed, own), task.approval.get("source") == "result",
                         review.change_digest(root, f"{commit}^1", own, commit))
    return problem(team, facts, merged=True, author=author)

