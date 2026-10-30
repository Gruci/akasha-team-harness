"""Branch protection and auto-merge for a repository where GitHub has none, for example a private repository on
GitHub Free. GitHub Actions run these functions on the server: `merge` after each passed check, and `watch` after
each push to the default branch.

GitHub protection stops a change before it merges. The watch undoes a change right after it arrives.
"""

from __future__ import annotations

import json
import tempfile
from fnmatch import fnmatchcase
from pathlib import Path

from akasha import config
from akasha.core.risk import matches
from akasha.core.workcopy import git
from akasha.infra import desired
from akasha.repo import gh

MERGE_LABEL = "akasha-merge"
UNDO_MARK = "Akasha undid"                             # the first words of each revert commit of the watch
_IDENTITY = ("-c", "user.name=akasha", "-c", "user.email=akasha@users.noreply.github.com")
_EMPTY = "0" * 40


def _api(root: Path, path: str):
    read = gh(root, "api", path)
    return json.loads(read.stdout) if read.returncode == 0 else None


def _protected(root: Path, slug: str, branch: str) -> bool:
    """True when GitHub protects the branch. Then GitHub enforces the rules, and these helpers do nothing."""
    return bool((_api(root, f"repos/{slug}/branches/{branch}") or {}).get("protected"))


def commit_body(text: str) -> str:
    """The briefing and Verification from a pull request body, without the closing line and the task marker."""
    cut = min((position for mark in ("\nCloses #", "<!-- akasha-task:") if (position := text.find(mark)) != -1),
              default=len(text))
    return text[:cut].strip() + "\n"


def merge(root: Path, slug: str, head_sha: str) -> str:
    """Merge the pull request whose check passed on head_sha, when Akasha marked it for auto-merge.

    Like strict branch protection, Akasha does not merge a branch that is behind the default branch."""
    for pull in _api(root, f"repos/{slug}/commits/{head_sha}/pulls") or []:
        if pull.get("state") != "open" or pull["head"]["sha"] != head_sha:
            continue
        number = str(pull["number"])
        if MERGE_LABEL not in {label["name"] for label in pull.get("labels", [])}:
            return f"pull request #{number} has no {MERGE_LABEL} label"
        if _protected(root, slug, pull["base"]["ref"]):
            return f"GitHub protects {pull['base']['ref']}, so GitHub merges pull request #{number}"
        compared = _api(root, f"repos/{slug}/compare/{pull['base']['ref']}...{head_sha}") or {}
        if compared.get("behind_by", 1):
            gh(root, "pr", "comment", number, "--repo", slug, "--body", "Akasha: the default branch moved after the "
               "check. Do the handover again, so that the check runs on the latest branch.")
            return f"pull request #{number} is behind {pull['base']['ref']}"
        done = gh(root, "pr", "merge", number, "--repo", slug, "--squash", "--match-head-commit", head_sha,
                  "--subject", f"{pull['title']} (#{number})", "--body", commit_body(pull.get("body") or ""))
        return f"merged #{number}" if done.returncode == 0 else f"GitHub refused the merge: {done.stderr.strip()[:300]}"
    return "no open pull request has this commit as its head"


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


def _reason(root: Path, slug: str, team: config.Team, sha: str) -> str:
    """Why a commit on the default branch is not in order, or "" when it is in order."""
    if git(root, "log", "-1", "--format=%s", sha).stdout.startswith(UNDO_MARK):
        return ""
    pulls = [pull for pull in _api(root, f"repos/{slug}/commits/{sha}/pulls") or [] if pull.get("merged_at")]
    if not pulls:
        return "it did not come from a merged pull request"
    pull = _api(root, f"repos/{slug}/pulls/{pulls[0]['number']}") or pulls[0]
    runs = _api(root, f"repos/{slug}/commits/{pull['head']['sha']}/check-runs?check_name={desired.CHECK_NAME}") or {}
    if not any(run.get("conclusion") == "success" for run in runs.get("check_runs", [])):
        return f"pull request #{pull['number']} merged without a passed check {desired.CHECK_NAME}"
    administrators = {person.lstrip("@") for person in team.administrators}
    if ((pull.get("merged_by") or {}).get("login") or "") in administrators:
        return ""                                     # an administrator can merge around a code owner review
    reviews = _api(root, f"repos/{slug}/pulls/{pull['number']}/reviews") or []
    approved = {review["user"]["login"] for review in reviews if review.get("state") == "APPROVED"}
    changed = git(root, "diff", "--name-only", f"{sha}^1", sha).stdout.split()
    missing = [path for path in changed if (owners := _owners(team, path)) and not owners & approved]
    return f"pull request #{pull['number']} changed {missing[0]} without the approval of its owner" if missing else ""


def _issue(root: Path, slug: str, title: str, text: str) -> None:
    gh(root, "label", "create", "akasha", "--repo", slug, "--color", "6d28d9", "--force")
    gh(root, "issue", "create", "--repo", slug, "--label", "akasha", "--title", f"[akasha] {title}", "--body", text)


def watch(root: Path, slug: str, branch: str, before: str, after: str, forced: bool, pusher: str) -> str:
    """Undo each change on the default branch that went around Akasha, and open an issue. Return what occurred.

    A force push and a push of an administrator are reported, not undone."""
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
    if pusher in {person.lstrip("@") for person in team.administrators}:
        _issue(root, slug, "An administrator changed the default branch around the check", listing)
        return f"reported {len(wrong)} change(s) of an administrator"
    for sha, _text in reversed(wrong):
        parents = git(root, "rev-list", "--parents", "-n", "1", sha).stdout.split()
        undone = git(root, *_IDENTITY, "revert", "--no-edit", *(["-m", "1"] if len(parents) > 2 else []), sha)
        if undone.returncode:
            git(root, "revert", "--abort")
            _issue(root, slug, "A change went around the check, and Akasha cannot undo it", listing)
            return "reported changes that Akasha cannot undo"
        git(root, *_IDENTITY, "commit", "--amend", "-m", f"{UNDO_MARK} {sha[:12]}: it went around the check")
    pushed = git(root, "push", "origin", f"HEAD:{branch}")
    if pushed.returncode:
        _issue(root, slug, "A change went around the check, and Akasha cannot undo it", listing)
        return f"git push failed: {pushed.stderr.strip()[:300]}"
    _issue(root, slug, "Akasha undid changes that went around the check", listing)
    return f"undid {len(wrong)} change(s)"
