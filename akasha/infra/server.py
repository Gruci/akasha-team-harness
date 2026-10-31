"""The helper workflows of Akasha run these functions on GitHub.

`merge` runs after each passed check and after each approval. Where GitHub has no auto-merge, for example a private
repository on GitHub Free, it merges a pull request with the label akasha-merge, as strict branch protection with
code owner reviews does. `watch` runs after each push to the default branch. Where GitHub has no branch protection, it
undoes each change that went around the check. GitHub protection stops a change before it merges. The watch undoes
it right after it arrives.

In each repository, also where GitHub protects the default branch, the helpers bring each pull request with the label
up to date when the default branch moves (`update`), because GitHub does not do it. They also tell the holder of a
task when its check fails (`failed`). Only a token that starts workflows, for example the token of the GitHub app of
Akasha, brings a pull request up to date: after an update with the workflow token, the check waits until a person
approves its run.

When GitHub does not answer, the helpers do nothing and stop with an error, so that the run is red. No answer is not
an empty answer, for example "no merged pull request".
"""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
from collections.abc import Iterable
from fnmatch import fnmatchcase
from pathlib import Path

from akasha import config
from akasha.coordinator import board
from akasha.core.handover import TASK_MARK
from akasha.core.risk import matches
from akasha.core.task import Task, active
from akasha.core.workcopy import fetch, git, names
from akasha.infra import desired
from akasha.repo import gh

MERGE_LABEL = "akasha-merge"
LABEL_OPTIONS = ("--color", "0e8a16", "--description", "Akasha brings this pull request up to date and merges it")
UNDO_MARK = "Akasha undid"                             # the first words of each revert commit of the watch
_UNDONE = re.compile(rf"^{UNDO_MARK} ([0-9a-f]{{7,40}}):")
_CLOSES = re.compile(r"(?m)^Closes #(\d+)")            # the issue of the task in the body of its pull request
_HTTP = re.compile(r"\(HTTP (\d{3})\)")                # the status that gh api tells after a failure
FAILED = {"failure", "timed_out"}                      # the conclusions of a check that failed
PUSH_TRIES = 3                                         # the watch fetches and undoes again after a refused push
_IDENTITY = ("-c", "user.name=akasha", "-c", "user.email=akasha@users.noreply.github.com")
_EMPTY = "0" * 40


class ServerError(RuntimeError):
    """GitHub or git did not answer. The helper stops, and its run fails."""


def _failure(done: subprocess.CompletedProcess) -> tuple[int, str]:
    """The HTTP status and the message of a failed gh call. The status is 0 when gh does not tell it."""
    status = _HTTP.search(done.stderr or "")
    try:
        message = str(json.loads(done.stdout).get("message") or "")
    except (ValueError, TypeError, AttributeError):
        message = ""
    return (int(status.group(1)) if status else 0), (message or " ".join((done.stderr or "").split()))[:300]


def _api(root: Path, path: str):
    """One answer of the GitHub API."""
    read = gh(root, "api", path)
    if read.returncode:
        raise ServerError(f"GitHub did not answer {path}: {_failure(read)[1]}")
    return json.loads(read.stdout or "null")


def _pages(root: Path, path: str) -> list:
    """All items of a list of the GitHub API. gh writes each page as one JSON array."""
    read = gh(root, "api", "--paginate", path)
    if read.returncode:
        raise ServerError(f"GitHub did not answer {path}: {_failure(read)[1]}")
    decoder, rest, items = json.JSONDecoder(), read.stdout.strip(), []
    while rest:
        page, end = decoder.raw_decode(rest)
        items += page if isinstance(page, list) else [page]
        rest = rest[end:].lstrip()
    return items


def _protected(root: Path, slug: str, branch: str) -> bool:
    """True when GitHub protects the branch. Then GitHub enforces the rules, and the helpers do not merge or undo."""
    return bool((_api(root, f"repos/{slug}/branches/{branch}") or {}).get("protected"))


def commit_body(text: str) -> str:
    """The briefing and Verification from a pull request body, without the closing line and the task marker."""
    cut = min((position for mark in ("\nCloses #", TASK_MARK) if (position := text.find(mark)) != -1),
              default=len(text))
    return text[:cut].strip() + "\n"


def _open_pull(root: Path, slug: str, head_sha: str) -> dict | None:
    """The open pull request whose head is the commit, or None."""
    return next((pull for pull in _api(root, f"repos/{slug}/commits/{head_sha}/pulls") or []
                 if pull.get("state") == "open" and pull["head"]["sha"] == head_sha), None)


def _labeled(pull: dict) -> bool:
    return MERGE_LABEL in {label.get("name") for label in pull.get("labels") or []}


def _conclusions(root: Path, slug: str, sha: str) -> set[str]:
    """The conclusions of the latest runs of the check akasha on a commit, for example success or failure. A run that
    did not finish has no conclusion yet: ""."""
    runs = _api(root, f"repos/{slug}/commits/{sha}/check-runs?check_name={desired.CHECK_NAME}") or {}
    return {run.get("conclusion") or "" for run in runs.get("check_runs", [])}


def _behind(root: Path, slug: str, base: str, head: str) -> int:
    """How many commits of the base branch the head does not have. GitHub always tells it; else Akasha counts 1."""
    return int((_api(root, f"repos/{slug}/compare/{base}...{head}") or {}).get("behind_by", 1))


def _task(root: Path, slug: str, pull: dict) -> tuple[str, Task | None]:
    """The issue number of the task of a pull request, and the task on that issue. ("", None) when the pull request
    closes no issue."""
    found = _CLOSES.search(pull.get("body") or "")
    if not found:
        return "", None
    issue = _api(root, f"repos/{slug}/issues/{found.group(1)}") or {}
    return found.group(1), board.parse(issue.get("body") or "")


def _mention(task: Task | None, pull: dict) -> str:
    """The holder of the task with @, else the author of the pull request."""
    name = (task.holder if task is not None else "") or (pull.get("user") or {}).get("login") or ""
    return f"@{name.lstrip('@')} " if name else ""


def _tell(root: Path, slug: str, numbers: Iterable[str | int], mark: str, text: str) -> None:
    """Write the text on each pull request or issue, once: Akasha skips a pull request or an issue where a comment has
    the mark already."""
    for number in numbers:
        if not number or any(mark in (item.get("body") or "")
                             for item in _pages(root, f"repos/{slug}/issues/{number}/comments?per_page=100")):
            continue
        done = gh(root, "api", "--method", "POST", f"repos/{slug}/issues/{number}/comments", "--input", "-",
                  payload={"body": f"{text}\n\n{mark}"})
        if done.returncode:
            raise ServerError(f"Akasha cannot write on #{number}: {_failure(done)[1]}")


def _bring_up_to_date(root: Path, slug: str, pull: dict) -> str:
    """Ask GitHub to merge the base branch into the pull request. GitHub does it soon after, and the check runs again
    on the new head. Return what occurred.

    A conflict goes to the people of the task, once for each head. A new commit on the pull request is not a
    problem: it starts the check itself. Other failures, for example a limit of the API, are only in the result."""
    number, head, base = pull["number"], pull["head"]["sha"], pull["base"]["ref"]
    done = gh(root, "api", "--method", "PUT", f"repos/{slug}/pulls/{number}/update-branch", "--input", "-",
              payload={"expected_head_sha": head})
    if done.returncode == 0:
        return f"pull request #{number} comes up to date with {base}"
    status, message = _failure(done)
    if status == 422 and "expected head sha" in message.lower():
        return f"pull request #{number} got a new commit, so Akasha did not change it"
    if status == 422 and "conflict" in message.lower():
        issue, task = _task(root, slug, pull)
        again = f"akasha handover {task.id}" if task is not None and task.id else "the handover"
        _tell(root, slug, (number, issue), f"<!-- akasha-conflict: {head} -->",
              f"{_mention(task, pull)}Akasha: pull request #{number} conflicts with the latest {base}, so Akasha "
              f"cannot bring it up to date. Do the handover again (`{again}`): it merges {base} into the work copy "
              "and tells the files that conflict.")
        return f"pull request #{number} conflicts with {base}"
    return f"GitHub did not bring pull request #{number} up to date (HTTP {status or 'unknown'}): {message}"


def _update_one(root: Path, slug: str, pull: dict) -> str:
    number, head, base = pull["number"], pull["head"]["sha"], pull["base"]["ref"]
    if _conclusions(root, slug, head) & FAILED:
        return f"pull request #{number}: the check {desired.CHECK_NAME} failed on its head"
    _issue_number, task = _task(root, slug, pull)
    if task is not None and not active(task):
        return f"pull request #{number}: its task is {task.status}"
    if not _behind(root, slug, base, head):
        return f"pull request #{number} is up to date with {base}"
    return _bring_up_to_date(root, slug, pull)


def update(root: Path, slug: str, branch: str) -> str:
    """Bring each open pull request with the label akasha-merge on the branch up to date, so that its check runs on
    the latest branch. Skip a draft, a pull request whose check failed on its head, and a pull request whose task is
    not active. Return one line for each pull request.

    A failure of GitHub for one pull request does not stop the others: it goes into its line."""
    lines = []
    for pull in _pages(root, f"repos/{slug}/pulls?state=open&base={branch}&per_page=100"):
        if not _labeled(pull) or pull.get("draft"):
            continue
        try:
            lines.append(_update_one(root, slug, pull))
        except ServerError as error:
            lines.append(f"pull request #{pull['number']}: {error}")
    return "\n".join(lines) or f"no open pull request with the label {MERGE_LABEL} on {branch}"


def failed(root: Path, slug: str, head_sha: str) -> str:
    """Tell the people of a task on its pull request and on its issue that the check failed with the latest default
    branch. Once for each head commit."""
    pull = _open_pull(root, slug, head_sha)
    if pull is None:
        return "no open pull request has this commit as its head"
    number, base = pull["number"], pull["base"]["ref"]
    if not _labeled(pull):
        return f"pull request #{number} has no {MERGE_LABEL} label"
    issue, task = _task(root, slug, pull)
    again = f"akasha handover {task.id}" if task is not None and task.id else "the handover"
    _tell(root, slug, (number, issue), f"<!-- akasha-failed: {head_sha} -->",
          f"{_mention(task, pull)}Akasha: the check {desired.CHECK_NAME} failed on pull request #{number} with the "
          f"latest {base} (commit {head_sha[:12]}). Repair the change in the work copy of the task, then do the "
          f"handover again (`{again}`).")
    return f"told the people of pull request #{number} that its check failed"


def _approvers(reviews: list) -> set[str]:
    """The accounts whose last review approved, in lower case. A later comment does not take an approval back, as on
    GitHub. A request for changes and a dismissal do."""
    last = {}
    for review in reviews:                            # the oldest review first
        if review.get("state") in ("APPROVED", "CHANGES_REQUESTED", "DISMISSED"):
            last[((review.get("user") or {}).get("login") or "").lower()] = review["state"]
    return {login for login, state in last.items() if state == "APPROVED"}


def _unapproved(team: config.Team, paths: Iterable[str], approved: set[str]) -> dict[str, set[str]]:
    """Each changed file with owners that no owner approved, with its owners."""
    return {path: owners for path in paths
            if (owners := _owners(team, path)) and not {owner.lower() for owner in owners} & approved}


def _waiting(root: Path, slug: str, pull: dict) -> str:
    """"" when the owners of the changed files approved the pull request. Else Akasha asks the owners on the pull
    request once, and tells why it waits. The rules come from the team config on the base branch, and they are the
    rules of the watch (_reason), so that the watch does not undo a merge of the helper."""
    number, base = pull["number"], pull["base"]["ref"]
    team = _team_at(root, f"origin/{base}")
    files = _pages(root, f"repos/{slug}/pulls/{number}/files?per_page=100")
    paths = sorted({path for item in files for path in (item.get("filename"), item.get("previous_filename")) if path})
    missing = _unapproved(team, paths, _approvers(_pages(root, f"repos/{slug}/pulls/{number}/reviews?per_page=100")))
    if not missing:
        return ""
    owners = sorted({owner for found in missing.values() for owner in found})
    named = " ".join(owner if "@" in owner else f"@{owner}" for owner in owners)
    _tell(root, slug, (number,), f"<!-- akasha-owners: {' '.join(owners)} -->",
          f"Akasha: pull request #{number} changes {next(iter(missing))}, so it waits for the approval of {named}. "
          "After the approval, Akasha merges it.")
    return f"pull request #{number} waits for the approval of {named}"


def merge(root: Path, slug: str, head_sha: str, update_branch: bool = False) -> str:
    """Merge the pull request with the head head_sha when Akasha marked it, its check passed on that head, it is up to
    date, and the owners of its files approved. Return what occurred.

    Like strict branch protection, Akasha does not merge a branch that is behind the default branch. With
    `update_branch`, the token starts workflows: in each repository, Akasha brings such a pull request up to date,
    and the pass of the check on the new head merges it. After a merge, the other pull requests with the label also
    come up to date. Without `update_branch`, as in Akasha 1.0.0, a comment asks for the handover again where GitHub
    does not protect the branch."""
    pull = _open_pull(root, slug, head_sha)
    if pull is None:
        return "no open pull request has this commit as its head"
    number, base = str(pull["number"]), pull["base"]["ref"]
    if not _labeled(pull):
        return f"pull request #{number} has no {MERGE_LABEL} label"
    if "success" not in _conclusions(root, slug, head_sha):     # an approval can come before the check passes
        return f"the check {desired.CHECK_NAME} did not pass on the head of pull request #{number}"
    behind = _behind(root, slug, base, head_sha)
    if behind and update_branch:
        return _bring_up_to_date(root, slug, pull)
    if _protected(root, slug, base):
        return f"GitHub protects {base}, so GitHub merges pull request #{number}"
    if behind:
        gh(root, "pr", "comment", number, "--repo", slug, "--body", "Akasha: the default branch moved after the "
           "check. Do the handover again, so that the check runs on the latest branch.")
        return f"pull request #{number} is behind {base}"
    waiting = _waiting(root, slug, pull)
    if waiting:
        return waiting
    done = gh(root, "pr", "merge", number, "--repo", slug, "--squash", "--match-head-commit", head_sha,
              "--subject", f"{pull['title']} (#{number})", "--body", commit_body(pull.get("body") or ""))
    if done.returncode:
        return f"GitHub refused the merge: {done.stderr.strip()[:300]}"
    # GitHub does not close the linked issues after a merge with the workflow token, so Akasha closes them. With the
    # token of the app, GitHub can close them first, and gh leaves a closed issue as it is.
    for issue in _CLOSES.findall(pull.get("body") or ""):
        gh(root, "issue", "close", issue, "--repo", slug, "--reason", "completed",
           "--comment", f"Akasha merged pull request #{number}.")
    if not update_branch:
        return f"merged #{number}"
    try:
        return f"merged #{number}\n{update(root, slug, base)}"
    except ServerError as error:                      # the merge stays; the next push to the branch updates them
        return f"merged #{number}\nAkasha did not bring the other pull requests up to date: {error}"


def _team_at(root: Path, commit: str) -> config.Team:
    """The team config of a commit: the rules that applied before a change, as branch protection does."""
    shown = git(root, "show", f"{commit}:{config.CONFIG_FILE}")
    if shown.returncode:
        return config.load(root)
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / config.CONFIG_FILE
        path.write_text(shown.stdout, encoding="utf-8")
        return config.load(root, path)


def _owned(path: str, pattern: str) -> bool:
    """CODEOWNERS matching for the patterns that Akasha writes."""
    if pattern.startswith("/"):
        anchored = pattern[1:]
        return path.startswith(anchored) if anchored.endswith("/") else fnmatchcase(path, anchored)
    return matches(path, pattern)


def _owners(team: config.Team, path: str) -> set[str]:
    """The owners of a file from the Akasha block of CODEOWNERS. The last matching line wins."""
    found: set[str] = set()
    for line in desired.codeowners(team).splitlines():
        if line and not line.startswith("#"):
            pattern, *people = line.split()
            if _owned(path, pattern):
                found = {person.lstrip("@") for person in people}
    return found


def _patch_id(root: Path, old: str, new: str) -> str:
    """The patch id of the change from old to new, or "" for no change. Without context lines: an undo on a later
    commit has other lines around the change."""
    diff = git(root, "diff", "-U0", "--binary", "--no-renames", old, new)
    if diff.returncode or not diff.stdout:
        return ""
    found = subprocess.run(["git", "patch-id", "--stable"], cwd=root, input=diff.stdout, capture_output=True,
                           text=True, encoding="utf-8", errors="replace")
    return (found.stdout.split() or [""])[0] if found.returncode == 0 else ""


def _true_undo(root: Path, slug: str, team: config.Team, sha: str) -> bool:
    """True when the commit is an undo of the watch: its subject names an earlier commit on the branch, it makes
    exactly the reverse change of that commit, and that commit is not in order.

    Each person can copy the subject. The exact reverse change stops other changes, and the last condition stops the
    undo of a change that the team accepted."""
    named = _UNDONE.match(git(root, "log", "-1", "--format=%s", sha).stdout)
    target = git(root, "rev-parse", "-q", "--verify", f"{named.group(1)}^{{commit}}").stdout.strip() if named else ""
    if not target or git(root, "merge-base", "--is-ancestor", target, f"{sha}^1").returncode:
        return False
    change = _patch_id(root, f"{sha}^1", sha)
    return bool(change) and change == _patch_id(root, target, f"{target}^1") and bool(_reason(root, slug, team, target))


def _reason(root: Path, slug: str, team: config.Team, sha: str) -> str:
    """Why a commit on the default branch is not in order, or "" when it is in order."""
    if _true_undo(root, slug, team, sha):
        return ""
    pulls = [pull for pull in _api(root, f"repos/{slug}/commits/{sha}/pulls") or [] if pull.get("merged_at")]
    if not pulls:
        return "it did not come from a merged pull request"
    pull = _api(root, f"repos/{slug}/pulls/{pulls[0]['number']}") or pulls[0]
    if "success" not in _conclusions(root, slug, pull["head"]["sha"]):
        return f"pull request #{pull['number']} merged without a passed check {desired.CHECK_NAME}"
    administrators = {person.lstrip("@").lower() for person in team.administrators}
    if ((pull.get("merged_by") or {}).get("login") or "").lower() in administrators:
        return ""                                     # an administrator can merge around a code owner review
    approved = _approvers(_pages(root, f"repos/{slug}/pulls/{pull['number']}/reviews?per_page=100"))
    missing = _unapproved(team, names(root, "diff", "--name-only", "--no-renames", f"{sha}^1", sha), approved)
    if not missing:
        return ""
    return f"pull request #{pull['number']} changed {next(iter(missing))} without the approval of its owner"


def _issue(root: Path, slug: str, title: str, text: str) -> None:
    gh(root, "label", "create", "akasha", "--repo", slug, "--color", "6d28d9", "--force")
    made = gh(root, "issue", "create", "--repo", slug, "--label", "akasha", "--title", f"[akasha] {title}",
              "--body", text)
    if made.returncode:
        raise ServerError(f"Akasha cannot open the issue \"{title}\": {_failure(made)[1]}")


def _undo(root: Path, slug: str, branch: str, wrong: list[tuple[str, str]], listing: str) -> str:
    """Undo the commits on the latest branch of the server, the newest first. When the server refuses the push,
    because another push came first, Akasha fetches and undoes again, PUSH_TRIES times at most."""
    pushed = None
    for _attempt in range(PUSH_TRIES):
        fetched = fetch(root, branch)
        latest = git(root, "checkout", "-q", "--detach", f"origin/{branch}") if fetched.returncode == 0 else fetched
        if latest.returncode:
            raise ServerError(f"git cannot take the latest {branch}: {latest.stderr.strip()[:300]}")
        for sha, _text in reversed(wrong):
            parents = git(root, "rev-list", "--parents", "-n", "1", sha).stdout.split()
            undone = git(root, *_IDENTITY, "revert", "--no-edit", *(["-m", "1"] if len(parents) > 2 else []), sha)
            if undone.returncode:
                git(root, "revert", "--abort")
                _issue(root, slug, "A change went around the check, and Akasha cannot undo it", listing)
                return "reported changes that Akasha cannot undo"
            git(root, *_IDENTITY, "commit", "--amend", "-m", f"{UNDO_MARK} {sha[:12]}: it went around the check")
        pushed = git(root, "push", "origin", f"HEAD:{branch}")
        if pushed.returncode == 0:
            _issue(root, slug, "Akasha undid changes that went around the check", listing)
            return f"undid {len(wrong)} change(s)"
    _issue(root, slug, "A change went around the check, and Akasha cannot undo it", listing)
    return f"git push failed: {pushed.stderr.strip()[:300] if pushed is not None else ''}"


def watch(root: Path, slug: str, branch: str, before: str, after: str, forced: bool, pusher: str) -> str:
    """Undo each change on the default branch that went around Akasha, and open an issue. Return what occurred.

    A force push and a push of an administrator are reported, not undone. When GitHub does not answer, the watch
    undoes nothing and stops with an error."""
    if _protected(root, slug, branch):
        return f"GitHub protects {branch}, so the watch does nothing"
    if forced:
        _issue(root, slug, "A force push changed the default branch",
               f"{pusher} replaced history from {before[:12]} to {after[:12]}. An administrator must examine it.")
        return "reported a force push"
    if before == _EMPTY:
        return "a new branch"
    team = _team_at(root, before)
    commits = git(root, "rev-list", "--first-parent", "--reverse", f"{before}..{after}").stdout.split()
    wrong = [(sha, reason) for sha in commits if (reason := _reason(root, slug, team, sha))]
    if not wrong:
        return "all changes are in order"
    listing = "\n".join(f"- {sha[:12]}: {reason}" for sha, reason in wrong)
    if pusher.lower() in {person.lstrip("@").lower() for person in team.administrators}:
        _issue(root, slug, "An administrator changed the default branch around the check", listing)
        return f"reported {len(wrong)} change(s) of an administrator"
    return _undo(root, slug, branch, wrong, listing)
