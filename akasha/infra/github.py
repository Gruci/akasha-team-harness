"""Read and change the repository settings on GitHub with the gh command."""

from __future__ import annotations

import functools
import hashlib
import json
import re
import subprocess
import time
from pathlib import Path

from akasha import config, repo
from akasha.core.workcopy import fetch, git
from akasha.infra import desired, server
from akasha.repo import gh, gh_repo

SERVER_STATE = config.STATE_DIR / "server.json"      # the last examination of the server rules on this computer
RECORD_AGE = 3600                                      # one hour, in seconds
ANSWER_SECONDS = 10                                    # git waits this long for the server to tell its default branch
_NO_PLAN = "Upgrade to GitHub Pro"                     # GitHub Free has no branch protection for private repositories
UPDATE = "/plugin update akasha@akasha in Claude Code, or pip install again for Codex"
_HEAD = re.compile(r"^ref: refs/heads/(\S+)\tHEAD$", re.M)        # the answer of git ls-remote --symref origin HEAD


def repository(root: Path) -> tuple[str, str] | None:
    """(owner/name, default branch) of the GitHub repository, or None without GitHub."""
    named = gh_repo(root)                             # gh repo view does not read GH_REPO
    viewed = gh(root, "repo", "view", *([named] if named else []), "--json", "nameWithOwner,defaultBranchRef")
    if viewed.returncode:
        return None
    data = json.loads(viewed.stdout)
    return data["nameWithOwner"], (data.get("defaultBranchRef") or {}).get("name") or "main"


def default_branch(root: Path) -> str:
    """The default branch on the server now, for example main, or "" when the server does not tell it.

    With GitHub, gh tells it. Else, or when gh does not answer, git asks the server for its HEAD. The origin/HEAD of
    this computer is not enough: git sets it at the clone, and it stays when the team renames the default branch.
    git asks for ANSWER_SECONDS at most: without this limit, each command waits until the computer stops the
    connection to a server that does not answer, for example about 21 seconds on Windows."""
    found = repository(root) if repo.origin(root) else None
    if found is not None:
        return found[1]
    listed = git(root, "ls-remote", "--symref", "origin", "HEAD", timeout=ANSWER_SECONDS)
    head = _HEAD.search(listed.stdout) if listed.returncode == 0 else None
    return head.group(1) if head else ""


def known_branch(root: Path) -> str:
    """The default branch that this computer knows without the network, or "": the branch of the last examination
    of the server rules, else origin/HEAD."""
    try:
        branch = json.loads((root / SERVER_STATE).read_text(encoding="utf-8")).get("branch")
    except (OSError, ValueError, AttributeError):
        branch = ""
    if isinstance(branch, str) and branch:
        return branch
    head = git(root, "symbolic-ref", "-q", "--short", "refs/remotes/origin/HEAD").stdout.strip()
    return head.removeprefix("origin/") if head.startswith("origin/") else ""


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
    return config.shared(root, f"origin/{branch}")


def _workflow_problems(root: Path, branch: str, team: config.Team) -> list[str]:
    """The server workflow files on the default branch that are not as this Akasha makes them from the team config
    there. A fix of Akasha keeps the version 1.0.0, so two computers can make different files: the update of Akasha
    comes first."""
    problems = []
    for target, text in desired.workflows(team).items():
        found = _server_file(root, branch, target)
        if found is None:
            problems.append(f"{target} is missing on {branch}")
        elif found != text:
            problems.append(f"{target} on {branch} is different from the file that the Akasha on this computer makes "
                            f"from the team config — update Akasha ({UPDATE}). When Akasha is up to date, an "
                            "administrator sets up Akasha again")
    return problems


def status(root: Path) -> list[str]:
    """The problems of the repository settings. An empty list means that the settings are correct.

    The server files must agree with the team config on the default branch, as CODEOWNERS does. Each examination
    also updates the record that the session start notice reads. The record also keeps the warnings that do not stop
    a handover, for `infra` and `setup`."""
    found = repository(root)
    if found is None:
        problems = ["Akasha cannot read the GitHub repository — make sure that gh is installed and logged in"]
        _remember(root, problems, False)
        return problems
    slug, branch = found
    current = settings(root, slug)
    fetch(root, branch)                               # the server uses the default branch
    team = _server_team(root, branch)
    if team.server_rules == "akasha":                 # GitHub has no protection on this plan; the helpers enforce
        problems = desired.settings_drift(current, ("allow_squash_merge",))
    else:
        problems = desired.drift(protection(root, slug, branch)) + desired.settings_drift(current)
    problems += _workflow_problems(root, branch, team)
    owners = next((text for path in desired.CODEOWNERS_FILES
                   if (text := _server_file(root, branch, path)) is not None), "")
    if desired.block(owners) != desired.codeowners(team):
        problems.append(f"the Akasha block of CODEOWNERS on {branch} is missing or different from akasha.toml")
    _remember(root, problems, bool((current.get("permissions") or {}).get("admin")), team.server_rules, branch,
              desired.warnings(team, current))
    return problems


def warnings(root: Path) -> list[str]:
    """The warnings of the last examination of the server rules, for example a runner of the team in a public
    repository. They do not stop a handover."""
    try:
        found = json.loads((root / SERVER_STATE).read_text(encoding="utf-8")).get("warnings")
    except (OSError, ValueError, AttributeError):
        return []
    return [item for item in found if isinstance(item, str)] if isinstance(found, list) else []


@functools.cache
def _installed() -> str:
    """A hash of the files of this Akasha. An update keeps the version 1.0.0, so the hash tells a new install."""
    package, digest = Path(__file__).resolve().parents[1], hashlib.sha256()
    for path in sorted(package.rglob("*")):
        if path.is_file() and path.suffix != ".pyc":
            digest.update(path.relative_to(package).as_posix().encode() + b"\0" + path.read_bytes() + b"\0")
    return digest.hexdigest()[:16]


def _marks(root: Path, branch: str) -> dict:
    """What the last examination depends on, without the network: the default branch as this computer knows it, the
    GitHub account of this person, and the files of Akasha. When one of them changes, the record is old."""
    commit = git(root, "rev-parse", "-q", "--verify", f"refs/remotes/origin/{branch}").stdout.strip() if branch else ""
    return {"commit": commit, "me": repo.me(root) if repo.origin(root) else "", "installed": _installed()}


def _remember(root: Path, problems: list[str], admin: bool, rules: str = "github", branch: str = "",
              warned: list[str] | None = None) -> None:
    path = root / SERVER_STATE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"checked": time.time(), "problems": problems, "admin": admin, "rules": rules,
                                "branch": branch, "warnings": warned or [], **_marks(root, branch)}), encoding="utf-8")


def readiness(root: Path, max_age: float = RECORD_AGE) -> dict:
    """The last examination of the server rules: the problems, and whether this person administers the repository.

    Akasha examines GitHub again when the record is older than max_age, or when the default branch on this computer,
    the GitHub account, or the files of Akasha changed since: for example, an administrator turned the rules on and
    merged the server files. Else the session start stays fast. The handover gate always examines GitHub again."""
    path = root / SERVER_STATE
    try:
        known = json.loads(path.read_text(encoding="utf-8"))
        marks = _marks(root, str(known.get("branch") or ""))
        if time.time() - known["checked"] < max_age and all(known.get(key) == value for key, value in marks.items()):
            return known
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
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


def apply(root: Path, approved_by: str = "") -> tuple[list[str], list[str]]:
    """Write the repository files and change the GitHub settings. An administrator must approve first. Return the
    problems, and the warnings that do not stop a handover.

    Akasha turns on the branch protection and the auto-merge of GitHub. When the plan of the repository has none,
    Akasha records `[server] rules = "akasha"`, and its merge and watch workflows enforce the rules. Akasha keeps the
    CODEOWNERS lines and the pull request template that the team already has. The server files get the values of
    the team config in this checkout: the administrator commits them with the team config in one pull request. Thus
    the warnings are for the team config in this checkout, before the pull request merges."""
    team = config.load(root)
    _examine_administrator(root, team, approved_by)
    for target, text in desired.workflows(team).items():
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
        return ["Akasha wrote the files, but cannot reach GitHub to change the settings"], []
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
    current = settings(root, slug)
    problems += [f"GitHub kept a setting off: {item}" for item in desired.settings_drift(current, wanted)]
    return problems, desired.warnings(team, current)


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
