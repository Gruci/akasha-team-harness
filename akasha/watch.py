"""The watch: where GitHub cannot protect the default branch, a workflow examines each new commit after a push and
reports each problem to the administrators. It changes no code: a revert would start a deployment that nobody asked
for, and the administrators decide."""

from __future__ import annotations

import json
from pathlib import Path

from akasha import config, repo
from akasha.checks import matches
from akasha.config import HELP_LABEL, Team

EMPTY = "0" * 40


def _api(root: Path, path: str):
    found = repo.gh_json(root, "api", path)
    if found is None:
        raise RuntimeError(f"GitHub did not answer {path}")
    return found


def _team_at(root: Path, commit: str) -> Team:
    """The team rules before the push, as branch protection uses them."""
    shown = repo.git(root, "show", f"{commit}:{config.CONFIG_FILE}")
    return config.parse(shown.stdout) if shown.returncode == 0 else config.load(root)


def _passed(root: Path, slug: str, sha: str, names: tuple[str, ...]) -> list[str]:
    """The required checks that did not pass on the commit."""
    runs = (_api(root, f"repos/{slug}/commits/{sha}/check-runs?per_page=100") or {}).get("check_runs") or []
    statuses = (_api(root, f"repos/{slug}/commits/{sha}/status") or {}).get("statuses") or []
    good = {run.get("name") for run in runs if run.get("conclusion") in ("success", "neutral", "skipped")}
    good |= {item.get("context") for item in statuses if item.get("state") == "success"}
    return [name for name in names if name not in good]


def _reason(root: Path, slug: str, team: Team, sha: str) -> str:
    """Why a commit on the default branch is not in order, or ""."""
    pulls = [pull for pull in _api(root, f"repos/{slug}/commits/{sha}/pulls") or [] if pull.get("merged_at")]
    if not pulls:
        return "it did not come from a merged pull request"
    pull = pulls[0]
    missing = _passed(root, slug, pull["head"]["sha"], team.status_checks)
    if missing:
        return f"pull request #{pull['number']} merged before {', '.join(missing)} passed"
    if not (team.risk_paths and team.reviewers):
        return ""
    changed = repo.names(root, "diff", "--name-only", "--no-renames", f"{sha}^1", sha)
    risky = [path for path in changed if any(matches(path, item) for item in team.risk_paths)]
    if not risky:
        return ""
    reviews = _api(root, f"repos/{slug}/pulls/{pull['number']}/reviews?per_page=100") or []
    approved = {(item.get("user") or {}).get("login", "").lower() for item in reviews if item.get("state") == "APPROVED"}
    if approved & set(team.reviewers):
        return ""
    return f"pull request #{pull['number']} changed {risky[0]} without the review of a reviewer"


def _issue(root: Path, slug: str, team: Team, title: str, text: str) -> None:
    people = " ".join(f"@{name}" for name in team.admins)
    repo.gh(root, "label", "create", HELP_LABEL, "--repo", slug, "--color", "d93f0b", "--force")
    repo.gh(root, "issue", "create", "--repo", slug, "--label", HELP_LABEL, "--title", f"[akasha] {title}",
            "--body", f"{people}\n\n{text}".strip())


def watch(root: Path, slug: str, branch: str, before: str, after: str, forced: bool, pusher: str) -> str:
    if (_api(root, f"repos/{slug}/branches/{branch}") or {}).get("protected"):
        return f"GitHub protects {branch}, so the watch does nothing"
    team = _team_at(root, before) if before and before != EMPTY else config.load(root)
    if forced:
        _issue(root, slug, team, "A force push changed the default branch",
               f"{pusher} replaced the history of {branch} from {before[:12]} to {after[:12]}.")
        return "reported a force push"
    if not before or before == EMPTY:
        return "a new branch"
    commits = repo.git(root, "rev-list", "--first-parent", "--reverse", f"{before}..{after}").stdout.split()
    wrong = [(sha, reason) for sha in commits if (reason := _reason(root, slug, team, sha))]
    if not wrong:
        return f"all {len(commits)} change(s) are in order"
    listing = "\n".join(f"- {sha[:12]}: {reason}" for sha, reason in wrong)
    _issue(root, slug, team, "A change went around the rules of the team",
           f"{pusher} pushed to {branch}. Examine each change and undo it if necessary:\n\n{listing}")
    return f"reported {len(wrong)} change(s): " + json.dumps([sha[:12] for sha, _reason in wrong])
