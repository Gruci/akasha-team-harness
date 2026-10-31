"""Set up Akasha in a repository: the team config, the files that Codex reads, and the GitHub settings."""

from __future__ import annotations

from pathlib import Path

from akasha import config
from akasha.core.workcopy import fetch, git
from akasha.engine import codex
from akasha.infra import github
from akasha.validators import langs

IGNORED = (".akasha/state/", ".akasha/work/")
RULES_TEXT = {
    "github": "Server rules: GitHub branch protection and auto-merge.",
    "akasha": "Server rules: GitHub has no branch protection on this plan, so the merge and watch workflows of Akasha "
              "enforce the rules. When the plan changes, set up Akasha again to use the GitHub rules.",
}
MAP_GUIDE = """# Product map

This folder has one map file for each feature key: `<feature key>.md`. A part of a large feature has the key
`<feature>/<part>` and the file `<feature>/<part>.md`. Thus the tasks of different features do not change the same
file. The agent engine reads the file of its feature before each impact analysis and updates it before each
handover. Write in Simplified Technical English.

<!-- The map file of one feature:
# <Feature name>
- Purpose: what the feature does for the user
- Screens: the screens or commands that show the feature
- Data: the tables, columns, or files that the feature reads or writes
- APIs: the endpoints or functions that other features use
- Depends on: the feature keys of the features that this feature uses
-->
"""


def _team_config(root: Path) -> str:
    packs = langs.detect(root)
    lines = ["# The team rules of Akasha. Change them with the approval of an administrator.",
             "[roles]", 'developers = []', 'administrators = []', "",
             "[risk]", 'high = ["**/migrations/**", "**/auth/**", "**/payments/**"]', 'medium = ["**/api/**"]', "",
             "# The agent engine makes the technical decisions. To add a person gate for a risk level, remove the #.",
             "[approval]", '# high = ["developer"]', "",
             "[checks]"]
    required = ["secrets"] + (["tests"] if packs and packs[0].tests else [])
    lines.append("required = [" + ", ".join(f'"{name}"' for name in required) + "]")
    if packs and packs[0].setup:
        lines.append(f'# setup = "{packs[0].setup}"    # installs the dependencies in a work copy and in CI')
    if packs and packs[0].tests:
        lines.append(f'tests = "{packs[0].tests}"')
    if packs and packs[0].lint:
        lines.append(f'lint = "{packs[0].lint}"')
    lines += ["", "[preview]", '# command = "npm run dev -- --port {port}"', 'database = "app_{task}"']
    return "\n".join(lines) + "\n"


def _on_server(root: Path) -> str:
    """The default branch when it has akasha.toml on the server, but this checkout has none, else "". Then the setup
    pull request merged, and this checkout is old: a new akasha.toml would make a second setup pull request."""
    if (root / config.CONFIG_FILE).is_file() or git(root, "remote", "get-url", "origin").returncode:
        return ""
    branch = github.default_branch(root)
    if branch:
        fetch(root, branch)
    return branch if branch and config.on_server(root, f"origin/{branch}") else ""


def run(root: Path, approved_by: str) -> list[str]:
    """Examine the repository first. A repository with the team rules and the server rules on needs only the files
    that Codex reads from this Akasha: an update of Akasha can change them. A checkout that only lacks the latest
    default branch needs a pull, not a second setup."""
    path = root / config.CONFIG_FILE
    pull = _on_server(root)
    if pull:
        return [f"The default branch {pull} on the server already has {config.CONFIG_FILE}, but this checkout does not. "
                f"Akasha does not write a second team config. Pull the default branch first: git pull origin {pull}. "
                "Then run the setup again: it examines the server rules."]
    problems = [] if approved_by else github.status(root)
    warned = [] if approved_by else [f"GitHub warning: {item}" for item in github.warnings(root)]
    if path.is_file() and not approved_by and not problems:
        ready = "Akasha is ready in this repository: the team rules and the server rules are on."
        changed = codex.write(root)
        if not changed:
            return [f"{ready} Nothing to set up."] + warned
        return [ready, f"Akasha updated {' and '.join(changed)} for this Akasha. Make a branch, commit them, and open "
                       "a pull request, so that each Codex session gets the current rules and hooks."] + warned
    report = []
    if path.is_file():
        report.append(f"{config.CONFIG_FILE} is present. Akasha keeps it.")
    else:
        path.write_text(_team_config(root), encoding="utf-8")
        report.append(f"Akasha wrote {config.CONFIG_FILE}. Ask the team for the roles and the high-risk areas.")
    team = config.load(root)                             # stop here if the team config is not correct
    guide = root / team.map_dir / config.MAP_README      # the product map of Akasha 1.0.0 stays where it is
    if not guide.is_file():
        guide.parent.mkdir(parents=True, exist_ok=True)
        guide.write_text(MAP_GUIDE, encoding="utf-8")
        report.append(f"Akasha wrote {team.map_dir}/{config.MAP_README}. The agent engine writes one map file for each "
                      "feature during the tasks.")
    ignore = root / ".gitignore"
    present = ignore.read_text(encoding="utf-8") if ignore.is_file() else ""
    made = [line for pack in langs.detect(root) for line in pack.ignore]     # files that tests and builds make
    missing = [line for line in dict.fromkeys(IGNORED + tuple(made)) if line not in present.splitlines()]
    if missing:
        ignore.write_text(present.rstrip("\n") + ("\n" if present.strip() else "") + "\n".join(missing) + "\n",
                          encoding="utf-8")
    written = codex.write(root)
    if written:
        report.append("Akasha wrote " + ", ".join(written) + ". Codex needs Akasha installed with pip.")
    if approved_by:
        refused, risks = github.apply(root, approved_by)
        report += [f"GitHub: {item}" for item in refused] or ["GitHub settings agree with akasha.toml."]
        report += [f"GitHub warning: {item}" for item in risks]
        report.append(RULES_TEXT[config.load(root).server_rules])
    else:
        report += [f"GitHub: {item}" for item in problems] + warned
        if github.readiness(root).get("admin"):
            report.append("You administer this repository. Approve the change, then run setup again with "
                          "--approve-infra <your GitHub name>.")
        else:
            report.append("An administrator of the repository must turn on the server rules. Ask an administrator.")
    return report
