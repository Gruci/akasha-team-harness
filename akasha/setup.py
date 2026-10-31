"""Set up Akasha in a repository: the team config, the files that Codex reads, and the GitHub settings."""

from __future__ import annotations

from pathlib import Path

from akasha import config
from akasha.core.workcopy import fetch, git
from akasha.engine import codex
from akasha.infra import github
from akasha.validators import langs

HISTORY = 100           # the setup reads this many earlier versions of each file of Codex on the default branch
COMMIT_CODEX = ("Make a branch, commit them, and open a pull request, so that each Codex session gets the current "
                "rules and hooks.")
READY = "Akasha is ready in this repository: the team rules and the server rules are on."
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


def _server_text(root: Path, ref: str, name: str) -> str | None:
    """The file at a commit, or None when the commit has no such file."""
    shown = git(root, "show", f"{ref}:{name}")
    return shown.stdout.replace("\r\n", "\n") if shown.returncode == 0 else None


def _older(root: Path, branch: str, name: str) -> bool:
    """True when the default branch had the file as the Akasha on this computer makes it, and other text since: an
    Akasha that is newer than this Akasha wrote the file. A fix of Akasha keeps the version 1.0.0, so the history of
    the file tells the order."""
    listed = git(root, "log", "--format=%H", "-n", str(HISTORY), f"origin/{branch}", "--", name)
    return any(codex.current(name, _server_text(root, commit, name)) for commit in listed.stdout.split())


def _codex_files(root: Path) -> list[str]:
    """Bring the files that Codex reads up to date in a ready repository: an update of Akasha can change them.
    Return the lines of the report, or none when nothing changes. A hooks file that Akasha cannot read stays as it
    is, and the report tells it.

    The default branch on the server decides, as the examination of the server rules fetched it. A checkout that is
    only old needs a pull, and an Akasha that is older than the Akasha that wrote the files does not write its older
    rules back. Without a copy of the default branch, the checkout decides."""
    broken = codex.unreadable(root)
    told = [codex.NOT_JSON.format(name=name) for name in broken]
    names = tuple(name for name in codex.FILES if name not in broken)
    branch = github.known_branch(root)
    if not branch or git(root, "rev-parse", "-q", "--verify", f"refs/remotes/origin/{branch}").returncode:
        changed = codex.write(root, names)
        return told + ([f"Akasha updated {' and '.join(changed)} for this Akasha. {COMMIT_CODEX}"] if changed else [])
    stale = tuple(name for name in names if not codex.current(name, _server_text(root, f"origin/{branch}", name)))
    if not stale:
        old = [name for name in names if not codex.current(name, codex.read(root / name))]
        return told + ([f"The default branch {branch} has the current {' and '.join(old)}, but this checkout is old. "
                        f"Pull the default branch: git pull origin {branch}"] if old else [])
    files = " and ".join(stale)
    if any(_older(root, branch, name) for name in stale):
        return told + [f"An Akasha that is newer than the Akasha on this computer wrote {files} on {branch}. Akasha "
                       f"does not write the older rules back. Update Akasha ({github.UPDATE}), then run the setup "
                       "again."]
    if codex.write(root, stale):
        return told + [f"Akasha updated {files} for this Akasha. {COMMIT_CODEX}"]
    return told + [f"This checkout has the current {files}, but {branch} does not. {COMMIT_CODEX} When a pull request "
                   "with the files is open, wait for its merge."]


def _top(folder: str) -> str:
    """The .gitignore line of a folder of Akasha. A line with a / before its end matches only at its place in the
    repository. A name alone, for example tmp/, matches at each depth, so it gets a leading /."""
    return f"{folder}/" if "/" in folder else f"/{folder}/"


def _forms(line: str) -> set[str]:
    """The .gitignore lines that ignore the files of the line, or more. A line with a / before its end matches only at
    its place, with or without a leading /. A name with a leading / is also in the name without it, which matches at
    each depth."""
    bare = line.lstrip("/")
    return {line, bare, f"/{bare}"} if "/" in bare.rstrip("/") or line.startswith("/") else {line}


def _ignore(root: Path, lines: tuple[str, ...]) -> list[str]:
    """Add the lines to .gitignore when it does not have them (_forms). Return the lines that Akasha added."""
    ignore = root / ".gitignore"
    present = ignore.read_text(encoding="utf-8") if ignore.is_file() else ""
    known = set(present.splitlines())
    missing = [line for line in dict.fromkeys(lines) if not _forms(line) & known]
    if missing:
        ignore.write_text(present.rstrip("\n") + ("\n" if present.strip() else "") + "\n".join(missing) + "\n",
                          encoding="utf-8")
    return missing


def run(root: Path, approved_by: str) -> list[str]:
    """Examine the repository first. A repository with the team rules and the server rules on needs only the files
    that Codex reads from this Akasha, and the folders of Akasha in .gitignore: an update of Akasha and [work] can
    change them. A checkout that only lacks the latest default branch needs a pull, not a second setup.

    The files that the tests and the builds make go into .gitignore only at the first setup: later, the team owns
    these lines."""
    path = root / config.CONFIG_FILE
    pull = _on_server(root)
    if pull:
        return [f"The default branch {pull} on the server already has {config.CONFIG_FILE}, but this checkout does not. "
                f"Akasha does not write a second team config. Pull the default branch first: git pull origin {pull}. "
                "Then run the setup again: it examines the server rules."]
    problems = [] if approved_by else github.status(root)
    warned = [] if approved_by else [f"GitHub warning: {item}" for item in github.warnings(root)]
    ready = path.is_file() and not approved_by and not problems
    report = []
    if not path.is_file():
        path.write_text(_team_config(root), encoding="utf-8")
        report.append(f"Akasha wrote {config.CONFIG_FILE}. Ask the team for the roles and the high-risk areas.")
    elif not ready:
        report.append(f"{config.CONFIG_FILE} is present. Akasha keeps it.")
    team = config.load(root)                             # stop here if the team config is not correct
    made = () if ready else tuple(line for pack in langs.detect(root) for line in pack.ignore)
    added = _ignore(root, (_top(config.STATE_DIR.as_posix()), _top(team.work_dir), *made))     # also when ready
    if ready:
        told = _codex_files(root) + ([f"Akasha added {', '.join(added)} to .gitignore: git does not track the "
                                      "folders of Akasha on each computer. Commit .gitignore in a pull request."]
                                     if added else [])
        return ([READY] + told if told else [f"{READY} Nothing to set up."]) + warned
    guide = root / team.map_dir / config.MAP_README      # the product map of Akasha 1.0.0 stays where it is
    if not guide.is_file():
        guide.parent.mkdir(parents=True, exist_ok=True)
        guide.write_text(MAP_GUIDE, encoding="utf-8")
        report.append(f"Akasha wrote {team.map_dir}/{config.MAP_README}. The agent engine writes one map file for each "
                      "feature during the tasks.")
    written = codex.write(root)
    if written:
        report.append("Akasha wrote " + ", ".join(written) + ". Codex needs Akasha installed with pip.")
    report += [codex.NOT_JSON.format(name=name) for name in codex.unreadable(root)]
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
