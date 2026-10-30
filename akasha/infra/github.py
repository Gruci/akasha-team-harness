"""Read and change the repository settings on GitHub with the gh command."""

from __future__ import annotations

import json
import subprocess
import tempfile
import time
from pathlib import Path

from akasha import config, repo
from akasha.core.workcopy import git
from akasha.infra import desired, server
from akasha.repo import gh, gh_repo

SERVER_STATE = config.STATE_DIR / "server.json"      # the last examination of the server rules on this computer
_NO_PLAN = "Upgrade to GitHub Pro"                     # GitHub Free has no branch protection for private repositories


def repository(root: Path) -> tuple[str, str] | None:
    """(owner/name, default branch) of the GitHub repository, or None without GitHub."""
    named = gh_repo(root)                             # gh repo view does not read GH_REPO
    viewed = gh(root, "repo", "view", *([named] if named else []), "--json", "nameWithOwner,defaultBranchRef")
    if viewed.returncode:
        return None
    data = json.loads(viewed.stdout)
    return data["nameWithOwner"], (data.get("defaultBranchRef") or {}).get("name") or "main"


def protection(root: Path, slug: str, branch: str) -> dict | None:
    """The branch protection. Only administrators can read all of it. For other people, Akasha reads the required
    checks from the branch and marks the result as partial."""
    full = gh(root, "api", f"repos/{slug}/branches/{branch}/protection")
    if full.returncode == 0:
        return json.loads(full.stdout)
    if _NO_PLAN in full.stdout + full.stderr:
        return {"unavailable": True}
    seen = gh(root, "api", f"repos/{slug}/branches/{branch}")
    if seen.returncode:
        return None
    data = json.loads(seen.stdout)
    if not data.get("protected"):
        return None
    return {"required_status_checks": (data.get("protection") or {}).get("required_status_checks") or {},
            "partial": True}


def settings(root: Path, slug: str) -> dict:
    read = gh(root, "api", f"repos/{slug}")
    return json.loads(read.stdout) if read.returncode == 0 else {}


def _server_file(root: Path, branch: str, path: str) -> str | None:
    shown = git(root, "show", f"origin/{branch}:{path}")
    return shown.stdout.replace("\r\n", "\n") if shown.returncode == 0 else None


def _server_team(root: Path, branch: str) -> config.Team:
    """The team config on the default branch. The server files must agree with it, not with a local copy that is
    not up to date."""
    text = _server_file(root, branch, config.CONFIG_FILE)
    if text is None:
        return config.load(root)
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / config.CONFIG_FILE
        path.write_text(text, encoding="utf-8")
        return config.load(root, path)


def status(root: Path) -> list[str]:
    """The problems of the repository settings. An empty list means that the settings are correct.

    Each examination also updates the record that the session start notice reads."""
    found = repository(root)
    if found is None:
        problems = ["Akasha cannot read the GitHub repository — make sure that gh is installed and logged in"]
        _remember(root, problems, False)
        return problems
    slug, branch = found
    current = settings(root, slug)
    git(root, "fetch", "-q", "origin", branch)                        # the server uses the default branch
    team = _server_team(root, branch)
    if team.server_rules == "akasha":                 # GitHub has no protection on this plan; the helpers enforce
        problems = desired.settings_drift(current, ("allow_squash_merge",))
    else:
        problems = desired.drift(protection(root, slug, branch)) + desired.settings_drift(current)
    problems += [f"{target} on {branch} is missing or different" for target, text in desired.workflows().items()
                 if _server_file(root, branch, target) != text]
    owners = next((text for path in desired.CODEOWNERS_FILES
                   if (text := _server_file(root, branch, path)) is not None), "")
    if desired.block(owners) != desired.codeowners(team):
        problems.append(f"the Akasha block of CODEOWNERS on {branch} is missing or different from akasha.toml")
    _remember(root, problems, bool((current.get("permissions") or {}).get("admin")), team.server_rules)
    return problems


def _remember(root: Path, problems: list[str], admin: bool, rules: str = "github") -> None:
    path = root / SERVER_STATE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"checked": time.time(), "problems": problems, "admin": admin, "rules": rules}),
                    encoding="utf-8")


def readiness(root: Path, max_age: float = 12 * 3600) -> dict:
    """The last examination of the server rules: the problems, and whether this person administers the repository.

    Akasha examines GitHub again only when the record is older than max_age, so that a session start stays fast."""
    path = root / SERVER_STATE
    try:
        known = json.loads(path.read_text(encoding="utf-8"))
        if time.time() - known["checked"] < max_age:
            return known
    except (OSError, ValueError, KeyError):
        pass
    status(root)
    return json.loads(path.read_text(encoding="utf-8"))


def _examine_administrator(root: Path, team: config.Team, approved_by: str) -> None:
    """Only an administrator changes the repository settings.

    With GitHub, Akasha does not trust a typed name: the GitHub account of this computer must be in `[roles]
    administrators` when the list names people, and it must administer the repository on GitHub. Akasha asks gh for
    the account and does not read the name that it keeps for the hooks. `approved_by` is optional, and it must be
    that account. Without GitHub, the name as in Akasha 1.0.0."""
    named = {person.strip().lstrip("@").lower() for person in team.administrators}
    if not repo.origin(root):
        if not approved_by or (named and approved_by.strip().lstrip("@").lower() not in named):
            raise PermissionError("an administrator that akasha.toml names must approve a change to the repository "
                                  "settings")
        return
    name = repo.me(root, fresh=True)
    if not name:
        raise PermissionError("Akasha cannot read your GitHub name. Make sure that gh is installed and logged in: "
                              "gh auth status")
    if approved_by and approved_by.strip().lstrip("@").lower() != name:
        raise PermissionError(f"{approved_by} must approve the change on their own computer: the GitHub account on "
                              f"this computer is {name}")
    if named and name not in named:
        raise PermissionError(f"{name} is not an administrator in {config.CONFIG_FILE}: only "
                              f"{', '.join(team.administrators)} can approve a change to the repository settings")
    found = repository(root)
    if found is None or not (settings(root, found[0]).get("permissions") or {}).get("admin"):
        raise PermissionError(f"the GitHub account {name} does not administer this repository on GitHub. Ask an "
                              "administrator of the repository to approve the change on their own computer")


def apply(root: Path, approved_by: str = "") -> list[str]:
    """Write the repository files and change the GitHub settings. An administrator must approve first.

    Akasha turns on the branch protection and the auto-merge of GitHub. When the plan of the repository has none,
    Akasha records `[server] rules = "akasha"`, and its merge and watch workflows enforce the rules. Akasha keeps the
    CODEOWNERS lines and the pull request template that the team already has."""
    team = config.load(root)
    _examine_administrator(root, team, approved_by)
    for target, text in desired.workflows().items():
        path = root / target
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    owners = next((root / path for path in desired.CODEOWNERS_FILES if (root / path).is_file()),
                  root / desired.CODEOWNERS_FILES[0])
    owners.write_text(desired.merge(owners.read_text(encoding="utf-8") if owners.is_file() else "",
                                    desired.codeowners(team)), encoding="utf-8")
    template = root / desired.TEMPLATE_FILE
    if not template.is_file():
        template.write_text(desired.template(), encoding="utf-8")
    found = repository(root)
    if found is None:
        return ["Akasha wrote the files, but cannot reach GitHub to change the settings"]
    slug, branch = found
    problems = []
    rules = "github"
    done = gh(root, "api", "--method", "PUT", f"repos/{slug}/branches/{branch}/protection", "--input", "-",
              payload=desired.protection())
    if done.returncode and _NO_PLAN in done.stdout + done.stderr:
        rules = "akasha"                              # the helpers of Akasha take over on this plan
    elif done.returncode:
        problems.append(f"GitHub refused the branch protection: {done.stderr.strip()[:300]}")
    config.set_server_rules(root, rules)
    gh(root, "label", "create", server.MERGE_LABEL, "--color", "0e8a16", "--force",
       "--description", "Akasha merges this pull request after the check passes")
    wanted = desired.SETTINGS if rules == "github" else {"allow_squash_merge": True, "delete_branch_on_merge": True}
    changed = gh(root, "api", "--method", "PATCH", f"repos/{slug}", "--input", "-", payload=wanted)
    if changed.returncode:
        problems.append(f"GitHub refused the repository settings: {changed.stderr.strip()[:300]}")
    # GitHub can accept the request and keep a setting off, for example auto-merge in a private repository on the
    # free plan. Thus Akasha reads the settings again.
    problems += [f"GitHub kept a setting off: {item}" for item in desired.settings_drift(settings(root, slug), wanted)]
    return problems


def pull_request(root: Path, address_or_branch: str) -> dict:
    """The pull request of a task: url, state (OPEN, MERGED, or CLOSED), and autoMergeRequest. Empty when none."""
    if not address_or_branch:
        return {}
    viewed = gh(root, "pr", "view", address_or_branch, "--json", "url,state,autoMergeRequest,labels")
    return json.loads(viewed.stdout) if viewed.returncode == 0 else {}


def merged(root: Path, address: str) -> bool:
    return pull_request(root, address).get("state") == "MERGED"


def auto_merge(root: Path, address: str, subject: str, body: str) -> subprocess.CompletedProcess:
    """Turn on auto-merge: GitHub merges the pull request as one squash commit when the required check passes."""
    return gh(root, "pr", "merge", address, "--auto", "--squash", "--subject", subject, "--body", body)
