"""The GitHub side of the team: branch protection, the repository settings, the labels, the Akasha block of
CODEOWNERS, and the workflow files of Akasha. Only an administrator of the repository changes them."""

from __future__ import annotations

import json
import re
from pathlib import Path

from akasha import SOURCE, config, repo
from akasha.checks import matches
from akasha.config import CONFIG_FILE, HELP_LABEL, LABEL, Team

TEMPLATES = Path(__file__).parent / "templates"
CODEOWNERS_FILES = (".github/CODEOWNERS", "CODEOWNERS", "docs/CODEOWNERS")
ADMIN_PATHS = (CONFIG_FILE, ".github/**") + CODEOWNERS_FILES       # the rules of the team and the GitHub files
START, END = "# akasha:start", "# akasha:end"
NO_PLAN = "Upgrade to GitHub Pro"            # GitHub Free has no branch protection for a private repository
CHECK_FILE = ".github/workflows/akasha.yml"
WATCH_FILE = ".github/workflows/akasha-watch.yml"
RUNS_ON_MARK, PYTHON_MARK, SOURCE_MARK = "@@AKASHA_RUNS_ON@@", "@@AKASHA_PYTHON@@", "@@AKASHA_SOURCE@@"
PLAIN_LABEL = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9.]+)+")
LABELS = {LABEL: ("6d28d9", "A task of Akasha"), HELP_LABEL: ("d93f0b", "Waits for an administrator")}


def protection(team: Team) -> dict:
    """The branch protection of the default branch: the checks of the team pass on an up-to-date branch, the code
    owners approve a change of their files, and nobody forces a push or deletes the branch."""
    return {
        "required_status_checks": {"strict": True, "contexts": list(team.status_checks)},
        "enforce_admins": False,
        "required_pull_request_reviews": {"required_approving_review_count": 0,
                                          "require_code_owner_reviews": bool(team.reviewers or team.admins)},
        "restrictions": None,
        "allow_force_pushes": False,
        "allow_deletions": False,
    }


def codeowners(team: Team) -> str:
    """The Akasha block of CODEOWNERS: the reviewers own the risky paths, and the administrators own the team rules
    and the GitHub files."""
    lines = [START, f"# Akasha writes this block from {CONFIG_FILE}. Change {CONFIG_FILE}, then run akasha setup."]
    reviewers = " ".join(f"@{name}" for name in team.reviewers)
    if reviewers:
        lines += [f"{item} {reviewers}" for item in team.risk_paths]
    admins = " ".join(f"@{name}" for name in team.admins)
    if admins:
        lines += [f"/{path} {admins}" for path in (CONFIG_FILE, ".github/", "CODEOWNERS")]
    return "\n".join(lines + [END]) + "\n"


def reviews_needed(team: Team, files: list[str], authors: set[str]) -> list[tuple[str, set[str], tuple[str, ...]]]:
    """For each kind of file of a change that needs a review: the first such file, the people of whom one must approve
    it, and the patterns of that kind. The administrators own the rules of the team: akasha.toml, the GitHub files, and
    the guides that each AI follows ([guides]). The reviewers own the risky paths. When none of the owners is free,
    because they made the change or the team named none, the other group reviews. The same rule holds where GitHub
    cannot enforce CODEOWNERS (a private repository on GitHub Free)."""
    rules = ADMIN_PATHS + tuple(name for names in team.guides.values() for name in names)
    needs = []
    for patterns, owners, others in ((rules, team.admins, team.reviewers),
                                     (team.risk_paths, team.reviewers, team.admins)):
        path = next((name for name in files if any(matches(name, item) for item in patterns)), "")
        people = (set(owners) - authors) or (set(others) - authors)
        if path and people:
            needs.append((path, people, tuple(patterns)))
    return needs


def review_states(reviews: object) -> dict[str, tuple[str, str]]:
    """The latest review of each person on a pull request: APPROVED, CHANGES_REQUESTED, or DISMISSED, and the commit
    that the person reviewed."""
    states = {}
    for item in reviews if isinstance(reviews, list) else []:
        if isinstance(item, dict) and item.get("state") in ("APPROVED", "CHANGES_REQUESTED", "DISMISSED"):
            states[str((item.get("user") or {}).get("login") or "").lower()] = (item["state"],
                                                                                  str(item.get("commit_id") or ""))
    return states


def approved(root: Path, states: dict[str, tuple[str, str]], people: set[str], patterns: tuple[str, ...],
             head: str) -> bool:
    """True when one of the people approved, and no file of the patterns changed between the commit that they reviewed
    and the head: a later change of a risky file needs a new review. GitHub Free does not dismiss an old approval."""
    for name in people:
        state, reviewed = states.get(name, ("", ""))
        if state != "APPROVED":
            continue
        if not reviewed or reviewed == head:
            return True
        changed = repo.gh(root, "api", f"repos/{repo.origin(root)}/compare/{reviewed}...{head}", "--jq",
                          ".files[].filename")
        if changed.returncode == 0 and not any(matches(path, item) for path in changed.stdout.split()
                                               for item in patterns):
            return True
    return False


def block(text: str) -> str:
    if START in text and END in text:
        return text[text.index(START):text.index(END) + len(END)] + "\n"
    return ""


def merge_block(text: str, new_block: str) -> str:
    """Put the Akasha block last in a CODEOWNERS text, because the last matching line wins. Keep the other lines."""
    old = block(text)
    rest = text.replace(old, "") if old else text
    return (rest.rstrip() + "\n\n" if rest.strip() else "") + new_block


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
    owners = next((text for path in CODEOWNERS_FILES if (text := _server_file(root, branch, path)) is not None), "")
    if (team.admins or team.reviewers) and block(owners) != codeowners(team):
        problems.append("the Akasha block of CODEOWNERS is missing or old: an administrator runs `akasha setup`")
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
