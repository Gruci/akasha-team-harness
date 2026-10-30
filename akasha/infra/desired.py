"""The repository settings that the team config needs. Nothing here uses the network."""

from __future__ import annotations

from pathlib import Path

from akasha.config import CONFIG_FILE, Team

CHECK_NAME = "akasha"
TEMPLATES = Path(__file__).parent / "templates"
FILES = {
    ".github/workflows/akasha.yml": "akasha.yml",
    ".github/pull_request_template.md": "pull_request_template.md",
}


def protection() -> dict:
    """Branch protection for the default branch: required checks on an up-to-date branch, code owner reviews."""
    return {
        "required_status_checks": {"strict": True, "contexts": [CHECK_NAME]},
        "enforce_admins": False,
        "required_pull_request_reviews": {"required_approving_review_count": 1, "require_code_owner_reviews": True},
        "restrictions": None,
        "allow_force_pushes": False,
        "allow_deletions": False,
    }


def _holders(team: Team, roles: tuple[str, ...]) -> list[str]:
    people = {"developer": team.developers, "administrator": team.administrators}
    return sorted({person for role in roles for person in people.get(role, ())})


def codeowners(team: Team) -> str:
    """CODEOWNERS from the risk rules and the approval rules. The team rules belong to the administrators."""
    lines = ["# Akasha writes this file from akasha.toml. Change akasha.toml, then run: python -m akasha infra"]
    for level in ("medium", "high"):
        owners = _holders(team, team.approval.get(level, ()))
        if owners:
            lines += [f"{pattern} {' '.join(owners)}" for pattern in team.risk.get(level, ())]
    rules = sorted(team.administrators)
    if rules:
        lines += [f"/{CONFIG_FILE} {' '.join(rules)}", f"/.akasha/ {' '.join(rules)}", f"/.github/ {' '.join(rules)}"]
    return "\n".join(lines) + "\n"


def files(team: Team) -> dict[str, str]:
    """The repository files that Akasha installs, with their text."""
    found = {target: (TEMPLATES / source).read_text(encoding="utf-8") for target, source in FILES.items()}
    found[".github/CODEOWNERS"] = codeowners(team)
    return found


def drift(current: dict | None) -> list[str]:
    """What is different between the branch protection on GitHub and the protection that Akasha needs."""
    if not current:
        return ["the default branch has no branch protection"]
    problems = []
    checks = current.get("required_status_checks") or {}
    contexts = set(checks.get("contexts") or []) | {item.get("context") for item in checks.get("checks") or []}
    if CHECK_NAME not in contexts:
        problems.append(f"the check {CHECK_NAME} is not required")
    if not checks.get("strict"):
        problems.append("a pull request can merge when its branch is not up to date")
    reviews = current.get("required_pull_request_reviews") or {}
    if reviews.get("required_approving_review_count", 0) < 1:
        problems.append("a pull request can merge without an approval")
    if not reviews.get("require_code_owner_reviews"):
        problems.append("code owners do not have to approve")
    if (current.get("allow_force_pushes") or {}).get("enabled"):
        problems.append("force pushes are permitted")
    if (current.get("allow_deletions") or {}).get("enabled"):
        problems.append("the default branch can be deleted")
    return problems
