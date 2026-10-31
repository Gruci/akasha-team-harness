"""The watch: where GitHub cannot protect the default branch, a workflow examines each new commit after a push and
reports each problem to the administrators: a commit that no merged pull request brought, a merge before the required
checks passed, a pull request that was not an Akasha task or had no approved preview or no passed plan review, and a
change of a risky path or of the rules of the team without the review of its owners. It changes no code: a revert
would start a deployment that nobody asked for, and the administrators decide."""

from __future__ import annotations

import json
from pathlib import Path

from akasha import config, github, repo
from akasha.config import HELP_LABEL, Team
from akasha.task import parse_block

EMPTY = "0" * 40


def _api(root: Path, path: str):
    found = repo.gh_json(root, "api", path)
    if found is None:
        raise RuntimeError(f"GitHub did not answer {path}")
    return found


def _team_at(root: Path, commit: str) -> Team:
    """The team rules before the push, as branch protection uses them."""
    text = config.shown(root, commit)
    return config.parse(text) if text is not None else config.load(root)


def _passed(root: Path, slug: str, sha: str, names: tuple[str, ...]) -> list[str]:
    """The required checks that did not pass on the commit. As in the landing, the latest run of a check that did not
    skip decides: a skipped run alone is the draft, not a pass."""
    runs = (_api(root, f"repos/{slug}/commits/{sha}/check-runs?per_page=100") or {}).get("check_runs") or []
    statuses = (_api(root, f"repos/{slug}/commits/{sha}/status") or {}).get("statuses") or []
    latest = {}
    for run in sorted(runs, key=lambda item: str(item.get("started_at") or "")):
        if run.get("conclusion") != "skipped":
            latest[run.get("name")] = run.get("conclusion")
    good = {name for name, conclusion in latest.items() if conclusion in ("success", "neutral")}
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
    if config.shown(root, f"{sha}^1") is None:
        return ""                                     # the setup of Akasha itself: no task yet
    author = str((pull.get("user") or {}).get("login") or "").lower()
    if author in team.own_procedure and not str((pull.get("head") or {}).get("ref") or "").startswith(
            team.branch_prefix):
        return ""                                     # the own procedure of the repository, of a person who keeps it
    task = parse_block(pull.get("body") or "")
    if task is None:
        return f"pull request #{pull['number']} was not an Akasha task"
    if not task.approval:
        return f"pull request #{pull['number']} merged without an approved preview"
    if task.review.get("verdict") != "PASS":
        return f"pull request #{pull['number']} merged without a passed plan review"
    changed = repo.names(root, "diff", "--name-only", "--no-renames", f"{sha}^1", sha)
    needs = github.reviews_needed(team, changed, {author})
    if not needs:
        return ""
    states = github.review_states(_api(root, f"repos/{slug}/pulls/{pull['number']}/reviews?per_page=100"))
    for path, people, patterns in needs:
        if not github.approved(root, states, people, patterns, str(pull["head"]["sha"])):
            return f"pull request #{pull['number']} changed {path} without the review of one of {sorted(people)}"
    return ""


def _issue(root: Path, slug: str, team: Team, title: str, text: str) -> None:
    people = " ".join(f"@{name}" for name in team.admins)
    repo.gh(root, "label", "create", HELP_LABEL, "--repo", slug, "--color", "d93f0b", "--force")
    repo.gh(root, "issue", "create", "--repo", slug, "--label", HELP_LABEL, "--title", f"[akasha] {title}",
            "--body", f"{people}\n\n{text}".strip())


def watch(root: Path, slug: str, branch: str, before: str, after: str, forced: bool, pusher: str) -> str:
    team = _team_at(root, before) if before and before != EMPTY else config.load(root)
    if github.guards_checks(_api(root, f"repos/{slug}/branches/{branch}") or {}, team):
        return f"GitHub protects {branch} with the checks of the team, so the watch does nothing"
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
