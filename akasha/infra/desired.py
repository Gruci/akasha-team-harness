"""The repository settings that the team config needs. Nothing here uses the network."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from pathlib import Path

from akasha.config import CONFIG_FILE, LEGACY_MAP, TEAM_WORKFLOWS, Team

CHECK_NAME = "akasha"
TEMPLATES = Path(__file__).parent / "templates"
# The required check, and the two helpers. The helpers merge and undo only where GitHub has no branch protection or
# auto-merge. In each repository, they bring the pull requests of the tasks up to date.
WORKFLOW_FILES = {f".github/workflows/{name}": name for name in ("akasha.yml", "akasha-merge.yml", "akasha-watch.yml")}
TEMPLATE_FILE = ".github/pull_request_template.md"
CODEOWNERS_FILES = (".github/CODEOWNERS", "CODEOWNERS", "docs/CODEOWNERS")     # GitHub uses the first that exists
START, END = "# akasha:start", "# akasha:end"
SETTINGS = {"allow_auto_merge": True, "allow_squash_merge": True, "delete_branch_on_merge": True}
NO_PLAN = ("GitHub has no branch protection for this private repository on its plan — set up Akasha again, "
           "so that the merge and watch workflows of Akasha enforce the rules")
# The marks in the template of the required check that the team config fills. str.format and string.Template cannot
# fill the template: it has ${{ }} of GitHub and ${…} of the shell.
RUNS_ON_MARK, PYTHON_MARK = "@@AKASHA_RUNS_ON@@", "@@AKASHA_PYTHON@@"
PLAIN_LABEL = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9.]+)+")     # YAML reads ubuntu-latest as text without quotes
# The labels of the standard machines that GitHub gives, for example ubuntu-latest, windows-2022, macos-15, and
# ubuntu-24.04-arm. Only the suffixes of GitHub: a runner of the team can have a label such as ubuntu-22.04-gpu. Other
# labels name a runner of the team, or a larger runner of GitHub with the name that the team gave it.
HOSTED = re.compile(r"(?:ubuntu|windows|macos)-(?:latest|slim|\d+(?:\.\d+)?)(?:-(?:arm|intel|large|xlarge))?", re.I)


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
    risk patterns of its level to the people with the gate roles.

    The product map has no owner. After the risk patterns, lines without owners take the map folder and the one
    product map of Akasha 1.0.0 back, because the last matching line wins: the map file of the feature auth/login is
    not code of auth."""
    lines = [START, "# Akasha writes this block from akasha.toml. To change it, change akasha.toml and set up Akasha."]
    gated = []
    for level in ("medium", "high"):
        owners = _holders(team, team.approval.get(level, ()))
        if owners:
            gated += [f"{pattern} {' '.join(owners)}" for pattern in team.risk.get(level, ())]
    if gated:
        gated += [f"/{team.map_dir}/", f"/{LEGACY_MAP.as_posix()}"]
    lines += gated
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


def runs_on(labels: tuple[str, ...]) -> str:
    """The runner labels in YAML: one label, or a flow list for the labels of a runner of the team. A label gets
    quotes, unless YAML reads it as text without them, for example ubuntu-latest."""
    if len(labels) == 1 and PLAIN_LABEL.fullmatch(labels[0]):
        return labels[0]
    quoted = [json.dumps(label) for label in labels]                # a JSON text is a YAML text in double quotes
    return quoted[0] if len(quoted) == 1 else f"[{', '.join(quoted)}]"


def workflows(team: Team | None = None) -> dict[str, str]:
    """The workflow files that Akasha installs, with their text. The team config gives the machine and the Python of
    the required check. Without a team, the defaults: ubuntu-latest and Python 3.12.

    The merge and watch workflows always run on ubuntu-latest: they can write to the repository, so they must not run
    on a machine where the code of a pull request ran."""
    team = team or Team()
    marks = {RUNS_ON_MARK: runs_on(team.runs_on), PYTHON_MARK: team.python}
    files = {}
    for target, source in WORKFLOW_FILES.items():
        text = (TEMPLATES / source).read_text(encoding="utf-8")
        for mark, value in marks.items():
            text = text.replace(mark, value)
        files[target] = text
    return files


def hosted(labels: tuple[str, ...]) -> bool:
    """True when GitHub gives the machine of the labels, for example ubuntu-latest."""
    return all(HOSTED.fullmatch(label) for label in labels)


def warnings(team: Team, current: dict) -> list[str]:
    """The risks of the settings that do not stop a handover. In a public repository, the required check runs the
    code of each pull request, also a pull request from a fork. On a runner of the team, that code runs on a machine
    of the team."""
    if current.get("private") is not False or hosted(team.runs_on):
        return []
    return [f"the required check runs on the runner {runs_on(team.runs_on)} of [ci] runs-on, and the repository is "
            "public: a pull request from a fork runs its code on that machine. Use a machine that GitHub gives, for "
            "example ubuntu-latest, or make the repository private"]


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
