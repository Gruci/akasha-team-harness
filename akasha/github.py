"""The GitHub side of the team: branch protection, the repository settings, the labels, and the workflow files of
Akasha. Only an administrator of the repository changes them."""

from __future__ import annotations

import json
import re
from pathlib import Path

from akasha import SOURCE, config, repo
from akasha.config import CONFIG_FILE, HELP_LABEL, LABEL, Team

TEMPLATES = Path(__file__).parent / "templates"
NO_PLAN = "Upgrade to GitHub Pro"            # GitHub Free has no branch protection for a private repository
CHECK_FILE = ".github/workflows/akasha.yml"
WATCH_FILE = ".github/workflows/akasha-watch.yml"
RUNS_ON_MARK, PYTHON_MARK, SOURCE_MARK = "@@AKASHA_RUNS_ON@@", "@@AKASHA_PYTHON@@", "@@AKASHA_SOURCE@@"
PLAIN_LABEL = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9.]+)+")
LABELS = {LABEL: ("6d28d9", "A task of Akasha"), HELP_LABEL: ("d93f0b", "Waits for an administrator")}


def protection(team: Team) -> dict:
    """The branch protection of the default branch: each change comes through a pull request, the checks of the team
    pass on an up-to-date branch, and nobody forces a push or deletes the branch. No person reviews a task."""
    return {
        "required_status_checks": {"strict": True, "contexts": list(team.status_checks)},
        "enforce_admins": False,
        "required_pull_request_reviews": {"required_approving_review_count": 0},
        "restrictions": None,
        "allow_force_pushes": False,
        "allow_deletions": False,
    }


def runs_on(labels: tuple[str, ...]) -> str:
    if len(labels) == 1 and PLAIN_LABEL.fullmatch(labels[0]):
        return labels[0]
    quoted = [json.dumps(label) for label in labels]
    return quoted[0] if len(quoted) == 1 else f"[{', '.join(quoted)}]"


def _template(name: str, team: Team) -> str:
    text = (TEMPLATES / name).read_text(encoding="utf-8")
    for mark, value in ((RUNS_ON_MARK, runs_on(team.runs_on)), (PYTHON_MARK, team.python), (SOURCE_MARK, SOURCE)):
        text = text.replace(mark, value)
    return text


def workflows(team: Team) -> dict[str, str]:
    """The workflow files that the team needs: the check of Akasha when the team has no CI of its own, and the watch
    where GitHub cannot protect the default branch."""
    files = {}
    if not team.ci_required:
        files[CHECK_FILE] = _template("akasha.yml", team)
    if team.server_rules == "akasha":
        files[WATCH_FILE] = _template("akasha-watch.yml", team)
    return files


def leftovers(team: Team) -> list[str]:
    """The workflow files of Akasha that the team does not need now."""
    return [path for path in (CHECK_FILE, WATCH_FILE) if path not in workflows(team)]


def _server_file(root: Path, branch: str, path: str) -> str | None:
    shown = repo.git(root, "show", f"origin/{branch}:{path}")
    return shown.stdout.replace("\r\n", "\n") if shown.returncode == 0 else None


def repository(root: Path) -> dict:
    slug = repo.origin(root)
    return (repo.gh_json(root, "api", f"repos/{slug}") or {}) if slug else {}


def is_admin(root: Path) -> bool:
    return bool((repository(root).get("permissions") or {}).get("admin"))


def guards_checks(branch: dict, team: Team) -> bool:
    """True when the protection of a branch (as `repos/{slug}/branches/{name}` tells it) requires each check of the
    team: only then GitHub stops a merge before the checks pass."""
    required = ((branch.get("protection") or {}).get("required_status_checks") or {}) if branch.get("protected") else {}
    names = set(required.get("contexts") or []) | {item.get("context") for item in required.get("checks") or []}
    return bool(required) and set(team.status_checks) <= names


def protected(root: Path, team: Team) -> bool | None:
    """True when GitHub protects the default branch now with the checks of the team, None when GitHub does not
    answer. Any collaborator can ask."""
    found = repo.gh_json(root, "api", f"repos/{repo.origin(root)}/branches/{repo.default_branch(root)}")
    return guards_checks(found, team) if isinstance(found, dict) else None


def _protection(root: Path, slug: str, branch: str) -> dict | None:
    done = repo.gh(root, "api", f"repos/{slug}/branches/{branch}/protection")
    if done.returncode == 0:
        return json.loads(done.stdout)
    if NO_PLAN in done.stdout + done.stderr:
        return {"unavailable": True}
    return None


def status(root: Path) -> list[str]:
    """What is not as the team config on the default branch needs. Empty when the server side is ready."""
    slug = repo.origin(root)
    if not slug:
        return ["origin is not a GitHub repository"]
    branch = repo.default_branch(root)
    repo.fetch(root, branch)
    if not config.on_server(root, branch):
        return [f"{branch} on the server has no {CONFIG_FILE} yet: merge the setup pull request"]
    team = config.shared(root, branch)
    problems = []
    for path, text in workflows(team).items():
        if _server_file(root, branch, path) != text:
            problems.append(f"{path} on {branch} is missing or old: an administrator runs `akasha setup` and merges it")
    if team.server_rules == "github":
        found = _protection(root, slug, branch)
        if found is None and is_admin(root):
            problems.append(f"{branch} has no branch protection: an administrator runs `akasha setup --apply`")
        elif found and found.get("unavailable"):
            problems.append("GitHub cannot protect the branch on this plan: an administrator runs `akasha setup "
                            "--apply`, which records the server rules of Akasha")
    return problems


def apply(root: Path) -> tuple[str, list[str]]:
    """Change the GitHub settings as the team config in this checkout needs. Return the server rules of this plan
    and the problems. The GitHub account of this computer must administer the repository."""
    slug, branch = repo.origin(root), repo.default_branch(root)
    if not slug:
        raise RuntimeError("origin is not a GitHub repository")
    team = config.load(root)
    me = repo.me(root)
    if team.admins and me not in team.admins:
        raise PermissionError(f"{me or 'this account'} is not in [team] admins of {CONFIG_FILE}")
    if not is_admin(root):
        raise PermissionError(f"the GitHub account {me or '?'} does not administer {slug}. Ask an administrator of "
                              "the repository to run `akasha setup --apply` on their computer")
    problems, rules = [], "github"
    done = repo.gh(root, "api", "--method", "PUT", f"repos/{slug}/branches/{branch}/protection", "--input", "-",
                   payload=protection(team))
    if done.returncode and NO_PLAN in done.stdout + done.stderr:
        rules = "akasha"
    elif done.returncode:
        problems.append(f"GitHub refused the branch protection: {done.stderr.strip()[:300]}")
    config.set_server_rules(root, rules)
    settings = {"allow_squash_merge": True, "delete_branch_on_merge": True}
    if rules == "github":
        settings["allow_auto_merge"] = True
    changed = repo.gh(root, "api", "--method", "PATCH", f"repos/{slug}", "--input", "-", payload=settings)
    if changed.returncode:
        problems.append(f"GitHub refused the repository settings: {changed.stderr.strip()[:300]}")
    for name, (color, text) in LABELS.items():
        repo.gh(root, "label", "create", name, "--color", color, "--description", text, "--force")
    return rules, problems
