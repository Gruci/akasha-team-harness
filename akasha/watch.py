"""The watch: where GitHub cannot protect the default branch, a workflow examines each new commit after a push and
reports each problem to the administrators: a commit that no merged pull request brought, a merge before the required
checks passed, a pull request that was not an Akasha task or had no approved preview or no passed plan review (a
quick task of only text for people needs no review, as on the local side: quick.text_only), an agent task of a
person or without an approved result, a task without a screen of a person who is not an administrator, without an
approved plan, or with a change of a screen file, and a change by a teammate or an agent account of a file that only
an administrator changes, or of existing lines of core code without an approval of an administrator. It changes no
code: a revert would start a deployment that nobody asked for, and the administrators decide."""

from __future__ import annotations

import json
from pathlib import Path

from akasha import checks, config, github, repo, quick, screen, version
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
    """The required checks that did not pass on the commit. As in the landing, the latest run of a check that ended and
    did not skip decides: a skipped run alone is the draft, not a pass, and a run that still runs on the same commit,
    for example after the draft got ready, does not hide a run that passed."""
    runs = (_api(root, f"repos/{slug}/commits/{sha}/check-runs?per_page=100") or {}).get("check_runs") or []
    statuses = (_api(root, f"repos/{slug}/commits/{sha}/status") or {}).get("statuses") or []
    latest = {}
    for run in sorted(runs, key=lambda item: str(item.get("started_at") or "")):
        if run.get("conclusion") not in (None, "skipped"):      # a run that still runs has no conclusion yet
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
    if task.kind == "agent" and author not in team.agents:
        return f"pull request #{pull['number']} is marked as an agent task, but @{author} is not an agent account"
    if author in team.agents and task.kind != "agent":
        return f"pull request #{pull['number']} of the agent account @{author} was not an agent task"
    if task.kind == "agent" and task.approval.get("source") != "result":
        return f"pull request #{pull['number']} merged without an approved result"
    changed = repo.names(root, "diff", "--name-only", "--no-renames", f"{sha}^1", sha)
    if screen.is_no_screen(task):
        found = screen.problems(team, changed, task.records_dir)
        if not screen.allowed(team, author):
            return (f"pull request #{pull['number']} is marked as a task without a screen, but @{author} is not an "
                    "administrator")
        if task.approval.get("source") != "plan":
            return f"pull request #{pull['number']} merged without an approved plan"
        if found:
            return f"pull request #{pull['number']} is a task without a screen, but {found[0]}"
    if not task.approval:
        return f"pull request #{pull['number']} merged without an approved preview"
    text_only = task.kind == "quick" and quick.text_only(changed, team.records_dir)
    if task.review.get("verdict") != "PASS" and not text_only:
        return f"pull request #{pull['number']} merged without a passed plan review"
    locked = checks.touches(changed, checks.locked(team, author))
    if locked:
        return f"pull request #{pull['number']} of @{author} changed {locked[0]}, which only an administrator changes"
    found = task.checks.get("core") or {}
    if found and not task.checks.get("core_approved_by") and author not in team.admins + team.own_procedure:
        return (f"pull request #{pull['number']} of @{author} changed existing lines of {next(iter(found))}, which "
                "other areas use, without an approval of an administrator")
    return ""


def _issue(root: Path, slug: str, team: Team, title: str, text: str) -> None:
    people = " ".join(f"@{name}" for name in team.admins)
    repo.gh(root, "label", "create", HELP_LABEL, "--repo", slug, "--color", "d93f0b", "--force")
    repo.gh(root, "issue", "create", "--repo", slug, "--label", HELP_LABEL, "--title", f"[akasha] {title}",
            "--body", f"{people}\n\n{text}".strip())


def version_problem(root: Path) -> str:
    """Why the run of the watch fails after its examination: the Akasha that runs is not the version in akasha.toml
    of the pushed commit, as in the server check (checks.ci). The run fails, and opens no issue for each push."""
    try:
        return version.server_problem((config.load(root).version,))
    except config.ConfigError:
        return ""


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
