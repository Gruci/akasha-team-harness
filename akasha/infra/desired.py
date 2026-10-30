"""The repository settings that the team config needs. Nothing here uses the network."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from akasha.config import CONFIG_FILE, TEAM_WORKFLOWS, Team

CHECK_NAME = "akasha"
TEMPLATES = Path(__file__).parent / "templates"
# The required check, and the two helpers that act only where GitHub has no branch protection or auto-merge
WORKFLOW_FILES = {f".github/workflows/{name}": name for name in ("akasha.yml", "akasha-merge.yml", "akasha-watch.yml")}
TEMPLATE_FILE = ".github/pull_request_template.md"
CODEOWNERS_FILES = (".github/CODEOWNERS", "CODEOWNERS", "docs/CODEOWNERS")     # GitHub uses the first that exists
START, END = "# akasha:start", "# akasha:end"
SETTINGS = {"allow_auto_merge": True, "allow_squash_merge": True, "delete_branch_on_merge": True}
NO_PLAN = ("GitHub has no branch protection for this private repository on its plan — set up Akasha again, "
           "so that the merge and watch workflows of Akasha enforce the rules")


def protection() -> dict:
    """Branch protection for the default branch: the required check on an up-to-date branch, and code owner reviews.

    No approval count: the team rules and the gates of the team have code owners. Other changes merge when the
    required check passes."""
    return {
        "required_status_checks": {"strict": True, "contexts": [CHECK_NAME]},
        "enforce_admins": False,
        "required_pull_request_reviews": {"required_approving_review_count": 0, "require_code_owner_reviews": True},
        "restrictions": None,
        "allow_force_pushes": False,
        "allow_deletions": False,
    }


def _owner(name: str) -> str:
    """A CODEOWNERS owner: @user, @org/team, or an email address. A plain GitHub name gets the @."""
    return name if "@" in name else f"@{name}"


def _holders(team: Team, roles: tuple[str, ...]) -> list[str]:
    people = {"developer": team.developers, "administrator": team.administrators}
    return sorted({_owner(person) for role in roles for person in people.get(role, ())})


def codeowners(team: Team) -> str:
    """The Akasha block of CODEOWNERS. The team rules belong to the administrators. A gate in `[approval]` gives the
    risk patterns of its level to the people with the gate roles."""
    lines = [START, "# Akasha writes this block from akasha.toml. To change it, change akasha.toml and set up Akasha."]
    for level in ("medium", "high"):
        owners = _holders(team, team.approval.get(level, ()))
        if owners:
            lines += [f"{pattern} {' '.join(owners)}" for pattern in team.risk.get(level, ())]
    rules = " ".join(sorted(_owner(person) for person in team.administrators))
    if rules:
        owned = (CONFIG_FILE, TEAM_WORKFLOWS.as_posix() + "/", ".github/", "CODEOWNERS", "docs/CODEOWNERS")
        lines += [f"/{path} {rules}" for path in owned]
    return "\n".join(lines + [END]) + "\n"


def block(text: str) -> str:
    """The Akasha block of a CODEOWNERS text, or "" when it has none."""
    if START in text and END in text:
        return text[text.index(START):text.index(END) + len(END)] + "\n"
    return ""


def merge(text: str, new_block: str) -> str:
    """Put the Akasha block into a CODEOWNERS text and keep the other lines of the team.

    The block goes last, because the last matching line wins in CODEOWNERS."""
    old = block(text)
    rest = text.replace(old, "") if old else text
    return (rest.rstrip() + "\n\n" if rest.strip() else "") + new_block


def workflows() -> dict[str, str]:
    """The workflow files that Akasha installs, with their text."""
    return {target: (TEMPLATES / source).read_text(encoding="utf-8") for target, source in WORKFLOW_FILES.items()}


def template() -> str:
    return (TEMPLATES / "pull_request_template.md").read_text(encoding="utf-8")


def drift(current: dict | None) -> list[str]:
    """What is different between the branch protection on GitHub and the protection that Akasha needs.

    `current` comes from the protection endpoint, which only administrators can read, or from the branch endpoint.
    The branch endpoint holds only the required checks, so Akasha examines only the checks then."""
    if not current:
        return ["the default branch has no branch protection"]
    if current.get("unavailable"):
        return [NO_PLAN]
    problems = []
    checks = current.get("required_status_checks") or {}
    contexts = set(checks.get("contexts") or []) | {item.get("context") for item in checks.get("checks") or []}
    if CHECK_NAME not in contexts:
        problems.append(f"the check {CHECK_NAME} is not required")
    if current.get("partial"):
        return problems
    if not checks.get("strict"):
        problems.append("a pull request can merge when its branch is not up to date")
    if not (current.get("required_pull_request_reviews") or {}).get("require_code_owner_reviews"):
        problems.append("code owners do not have to approve")
    if (current.get("allow_force_pushes") or {}).get("enabled"):
        problems.append("force pushes are permitted")
    if (current.get("allow_deletions") or {}).get("enabled"):
        problems.append("the default branch can be deleted")
    return problems


def settings_drift(current: dict, names: Iterable[str] = tuple(SETTINGS)) -> list[str]:
    """Repository settings that are off. GitHub hides some settings from people without administrator rights, so
    Akasha examines only the settings that it can read."""
    return [f"the repository setting {name} is off" for name in names if current.get(name) is False]
