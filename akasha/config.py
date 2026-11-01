"""The team config akasha.toml: who sets up the team, which paths need a review, which checks must pass, and where
the work goes.

The commands read the config from the default branch as git fetched it last, so that each computer uses the rules
that the administrators merged, also when its checkout is old. The setup reads and writes the file in the checkout,
because the administrator changes it there and merges it with a pull request."""

from __future__ import annotations

import re
import subprocess
import tomllib
from dataclasses import dataclass, field
from pathlib import Path, PureWindowsPath

CONFIG_FILE = "akasha.toml"
PLACES = (CONFIG_FILE, f".github/{CONFIG_FILE}")    # where the team config can be, in this order
STATE_DIR = Path(".akasha") / "state"        # the state of this computer. Git ignores it
RECORDS_DIR = ".akasha/tasks"                # the preview, the plan, and the summary of each task. They go into git
WORK_DIR = ".akasha/work"                    # a git worktree for each task: <folder>/<task>
BRANCH_PREFIX = "akasha/"                    # the branch of each task: <prefix><task>
LABEL = "akasha"                             # the label of each pull request of a task: the open ones are the board
HELP_LABEL = "akasha-help"                   # a task that waits for an administrator
SERVER_RULES = ("github", "akasha")          # who stops a merge without the checks: GitHub, or Akasha on each computer
GUIDE_STEPS = ("join", "preview", "plan", "build", "review")
CHECK_KEYS = ("command", "cwd", "only_when", "command_windows", "ready")
CHECK_SETTINGS = ("required", "setup", "run_all_when")
RESERVED_CHECKS = CHECK_SETTINGS + ("secrets",)
ONE_LINE_CHECKS = ("tests", "lint")          # a check with one command line: tests = "<command>"
CHECK_NAME = re.compile(r"[A-Za-z0-9_-]+")
NOT_IN_BRANCH = re.compile(r"[\x00-\x20\x7f~^:?*\[\\]|\.\.|@\{")
WINDOWS_NAMES = "(?:con|prn|aux|nul|com[0-9]|lpt[0-9])"
# A change of these files can break each check, so each check runs, also a check with only_when
RUN_ALL_WHEN = ("**/requirements*.txt", "**/pyproject.toml", "**/setup.cfg", "**/setup.py", "**/Pipfile",
                "**/Pipfile.lock", "**/poetry.lock", "**/uv.lock", "**/package.json", "**/package-lock.json",
                "**/npm-shrinkwrap.json", "**/yarn.lock", "**/pnpm-lock.yaml", "**/go.mod", "**/go.sum",
                "**/build.gradle", "**/build.gradle.kts", "**/pom.xml", *PLACES, ".github/workflows/**")
RUNS_ON = ("ubuntu-latest",)
PYTHON = "3.12"
LOWEST_PYTHON = (3, 11)
PYTHON_VERSION = re.compile(r"(\d+)\.(\d+)(?:\.\d+)?")
AKASHA_CHECK = "akasha"                      # the name of the check of .github/workflows/akasha.yml

_KEYS: dict[str, set[str] | None] = {
    "team": {"admins", "own_procedure"},
    "risk": {"paths"},
    "checks": None,                          # the team names its checks
    "ci": {"required", "runs-on", "python"},
    "work": {"folder", "branch_prefix", "records"},
    "guides": set(GUIDE_STEPS),
    "server": {"rules"},
    "deploy": {"workflow"},
}


class ConfigError(ValueError):
    """The team config has an incorrect shape."""


@dataclass(frozen=True)
class Check:
    """A check of the team in [checks.<name>]: a command that must pass."""
    command: str
    cwd: str = ""                            # the folder of the command, with / between the parts. "" is the top
    only_when: tuple[str, ...] = ()          # the check runs only when a changed file matches. () is each change
    command_windows: str = ""                # the command on Windows, for cmd.exe
    ready: str = ""                          # a command that passes when this computer can run the check (doctor)


@dataclass(frozen=True)
class Team:
    admins: tuple[str, ...] = ()             # GitHub names, in lower case, without @
    own_procedure: tuple[str, ...] = ()      # GitHub names that keep the own procedure of the repository
    risk_paths: tuple[str, ...] = ()         # a change of these files waits for the review of an administrator
    required_checks: tuple[str, ...] = ("secrets",)
    checks: dict[str, Check] = field(default_factory=dict)
    setup: str = ""                          # the command that prepares a new work copy, for example npm ci
    run_all_when: tuple[str, ...] = RUN_ALL_WHEN
    ci_required: tuple[str, ...] = ()        # the checks of the CI of the team that GitHub must see pass
    runs_on: tuple[str, ...] = RUNS_ON       # the machine of the check of Akasha, when the team has no CI
    python: str = PYTHON
    work_dir: str = WORK_DIR
    branch_prefix: str = BRANCH_PREFIX
    records_dir: str = RECORDS_DIR
    guides: dict[str, tuple[str, ...]] = field(default_factory=dict)    # step -> team files to read in that step
    server_rules: str = "github"
    deploy_workflow: str = ""                # the workflow that puts a merged change live, for example "Deploy"
    unknown: tuple[str, ...] = ()            # settings of a newer Akasha that this one does not know

    @property
    def status_checks(self) -> tuple[str, ...]:
        """The checks that GitHub must see pass before a merge: the CI of the team, else the check of Akasha."""
        return self.ci_required or (AKASHA_CHECK,)


def _strings(value: object, where: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise ConfigError(f"{CONFIG_FILE}: {where} must be a list of text values")
    return tuple(item.strip() for item in value)


def _text(value: object, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{CONFIG_FILE}: {where} must be a text value")
    return value.strip()


def _names(value: object, where: str) -> tuple[str, ...]:
    """GitHub names in lower case without @, so that a comparison with a login works."""
    return tuple(name.lstrip("@").lower() for name in _strings(value, where))


def pattern(text: str) -> str:
    """A file pattern in the form of the paths of git: / between the parts and no leading ./. A pattern that ends
    with / is each file in that folder."""
    text = text.replace("\\", "/")
    while text.startswith("./"):
        text = text[2:]
    return text + "**" if not text or text.endswith("/") else text


def _patterns(value: object, where: str) -> tuple[str, ...]:
    return tuple(pattern(item) for item in _strings(value, where))


def _relative(value: object, where: str, example: str, top: bool = True) -> str:
    """A folder in the repository, with / between the parts. An absolute path, a drive, and .. are refused."""
    path = PureWindowsPath(_text(value, where))
    if path.anchor or ".." in path.parts or not (path.parts or top):
        raise ConfigError(f"{CONFIG_FILE}: {where} must be a folder in the repository, for example {example}")
    return "/".join(path.parts)


def _folder(value: object, key: str, example: str, others: tuple[str, ...]) -> str:
    """A folder of Akasha in the repository, apart from .git, the state of Akasha, and the other folders."""
    folder = _relative(value, f"[work] {key}", example, top=False)
    parts = folder.lower().split("/")
    if any(re.fullmatch(WINDOWS_NAMES, part.split(".")[0]) for part in parts):
        raise ConfigError(f"{CONFIG_FILE}: [work] {key} {folder} has a device name of Windows")
    for other in (".git", STATE_DIR.as_posix(), *others):
        other = other.lower()
        if (folder.lower() + "/").startswith(other + "/") or (other + "/").startswith(folder.lower() + "/"):
            raise ConfigError(f"{CONFIG_FILE}: [work] {key} {folder} cannot be {other}, in it, or around it")
    return folder


def _prefix(value: object) -> str:
    prefix = _text(value, "[work] branch_prefix")
    if NOT_IN_BRANCH.search(prefix) or prefix.startswith("-") or \
            any(not part or part.startswith(".") or part.endswith(".lock") for part in (prefix + "x").split("/")):
        raise ConfigError(f"{CONFIG_FILE}: [work] branch_prefix {prefix!r} cannot start a branch name of git")
    return prefix


def _check(name: str, value: object, unknown: list[str]) -> Check:
    where = f"[checks.{name}]"
    if name in RESERVED_CHECKS:
        raise ConfigError(f"{CONFIG_FILE}: {name} cannot be the name of a check")
    if name in ONE_LINE_CHECKS and isinstance(value, str):
        return Check(_text(value, f"[checks] {name}"))
    if not isinstance(value, dict):
        raise ConfigError(f'{CONFIG_FILE}: write the check {name} as a table {where} with command = "<command>"')
    if not CHECK_NAME.fullmatch(name):
        raise ConfigError(f"{CONFIG_FILE}: the check name {name} can have only letters, digits, - and _")
    unknown += [f"{where} {key}" for key in sorted(set(value) - set(CHECK_KEYS))]
    only_when = _patterns(value.get("only_when", []), f"{where} only_when")
    if "only_when" in value and not only_when:
        raise ConfigError(f"{CONFIG_FILE}: {where} only_when needs one or more file patterns")
    return Check(command=_text(value.get("command"), f"{where} command"),
                 cwd=_relative(value.get("cwd", "."), f"{where} cwd", "frontend"), only_when=only_when,
                 command_windows=_text(value["command_windows"], f"{where} command_windows")
                 if "command_windows" in value else "",
                 ready=_text(value["ready"], f"{where} ready") if "ready" in value else "")


def _runs_on(value: object) -> tuple[str, ...]:
    labels = [value] if isinstance(value, str) else value
    if not isinstance(labels, list) or not labels or \
            not all(isinstance(label, str) and label.strip() for label in labels):
        raise ConfigError(f'{CONFIG_FILE}: [ci] runs-on must be a runner label or a list of labels, for example '
                          '"ubuntu-latest"')
    if any("#" in label or any(ord(char) < 32 for char in label) for label in labels):
        raise ConfigError(f"{CONFIG_FILE}: a label in [ci] runs-on cannot have a line break or #")
    return tuple(label.strip() for label in labels)


def _python(value: object) -> str:
    found = PYTHON_VERSION.fullmatch(value.strip()) if isinstance(value, str) else None
    if not found or (int(found[1]), int(found[2])) < LOWEST_PYTHON:
        raise ConfigError(f'{CONFIG_FILE}: [ci] python must be the text of a Python version of 3.11 or higher, for '
                          f'example "{PYTHON}"')
    return value.strip()


def _guides(section: dict) -> dict[str, tuple[str, ...]]:
    return {step: tuple(pattern(item) for item in _strings(files, f"[guides] {step}"))
            for step, files in section.items()}


def _known(data: dict) -> tuple[dict, list[str]]:
    """The data without the sections and keys that this Akasha does not know, and their names. A newer Akasha can
    write them into akasha.toml: an older one tells the person to update it, and does not stop the work."""
    known, unknown = {}, []
    for section, value in data.items():
        if section not in _KEYS:
            unknown.append(f"[{section}]")
            continue
        if not isinstance(value, dict):
            raise ConfigError(f"{CONFIG_FILE}: [{section}] must be a table")
        allowed = _KEYS[section]
        known[section] = value if allowed is None else {key: item for key, item in value.items() if key in allowed}
        unknown += [f"[{section}] {key}" for key in sorted(set(value) - (allowed or set(value)))]
    return known, unknown


def team_from(data: dict) -> Team:
    """Examine the data of akasha.toml and make the team rules."""
    data, unknown = _known(data)
    team, risk, checks = data.get("team", {}), data.get("risk", {}), data.get("checks", {})
    ci, work, server = data.get("ci", {}), data.get("work", {}), data.get("server", {})
    rules = server.get("rules", "github")
    if rules not in SERVER_RULES:
        raise ConfigError(f"{CONFIG_FILE}: [server] rules must be {' or '.join(SERVER_RULES)}")
    named = {}
    for name, value in checks.items():
        if name in CHECK_SETTINGS and not isinstance(value, dict):
            continue
        if not isinstance(value, dict) and name not in ONE_LINE_CHECKS:
            unknown.append(f"[checks] {name}")            # a setting of a newer Akasha, or a check without a table
            continue
        named[name] = _check(name, value, unknown)
    work_dir = _folder(work.get("folder", WORK_DIR), "folder", WORK_DIR, ())
    deploy = data.get("deploy", {})
    return Team(
        admins=_names(team.get("admins", []), "[team] admins"),
        own_procedure=_names(team.get("own_procedure", []), "[team] own_procedure"),
        risk_paths=_patterns(risk.get("paths", []), "[risk] paths"),
        required_checks=_strings(checks.get("required", ["secrets"]), "[checks] required") or ("secrets",),
        checks=named,
        setup=_text(checks["setup"], "[checks] setup") if "setup" in checks else "",
        run_all_when=_patterns(checks["run_all_when"], "[checks] run_all_when") if "run_all_when" in checks
        else RUN_ALL_WHEN,
        ci_required=_strings(ci.get("required", []), "[ci] required"),
        runs_on=_runs_on(ci.get("runs-on", list(RUNS_ON))),
        python=_python(ci.get("python", PYTHON)),
        work_dir=work_dir,
        branch_prefix=_prefix(work.get("branch_prefix", BRANCH_PREFIX)),
        records_dir=_folder(work.get("records", RECORDS_DIR), "records", "docs/tasks", (work_dir,)),
        guides=_guides(data.get("guides", {})),
        server_rules=rules,
        deploy_workflow=_text(deploy["workflow"], "[deploy] workflow") if "workflow" in deploy else "",
        unknown=tuple(unknown),
    )


def parse(text: str, where: str = CONFIG_FILE) -> Team:
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        raise ConfigError(f"{where}: {error}") from None
    try:
        return team_from(data)
    except ConfigError as error:
        raise ConfigError(f"{error} ({where})" if where != CONFIG_FILE else str(error)) from None


def place(root: Path) -> Path:
    """The team config in this checkout: at the top, or in .github/ for a repository that allows only listed files at
    the top. A new one goes to the top."""
    return next((root / name for name in PLACES if (root / name).is_file()), root / CONFIG_FILE)


def load(root: Path, path: Path | None = None) -> Team:
    """The team config in this checkout, or in `path`. Without the file, the default rules."""
    path = path or place(root)
    return parse(path.read_text(encoding="utf-8")) if path.is_file() else Team()


def shown(root: Path, ref: str) -> str | None:
    """The text of the team config in the commit `ref`, or None when the commit has none."""
    for name in PLACES:
        shown = subprocess.run(["git", "show", f"{ref}:{name}"], cwd=root, capture_output=True, text=True,
                               encoding="utf-8", errors="replace")
        if shown.returncode == 0:
            return shown.stdout
    return None


def shared(root: Path, branch: str) -> Team:
    """The team config on the default branch as git fetched it last, else the one in this checkout."""
    text = shown(root, f"origin/{branch}") if branch else None
    return parse(text, f"origin/{branch}") if text is not None else load(root)


def on_server(root: Path, branch: str) -> bool:
    """True when the default branch, as git fetched it last, has akasha.toml. It uses no network."""
    return bool(branch) and shown(root, f"origin/{branch}") is not None


def set_server_rules(root: Path, rules: str) -> None:
    """Write [server] rules into akasha.toml and keep each other line."""
    path = place(root)
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    line = f'rules = "{rules}"'
    if re.search(r"(?m)^\[server\]\s*$", text):
        text = re.sub(r"(?m)^rules\s*=.*$", line, text, count=1) if re.search(r"(?m)^rules\s*=", text) else \
            re.sub(r"(?m)^\[server\]\s*$", f"[server]\n{line}", text, count=1)
    else:
        text = text.rstrip("\n") + ("\n\n" if text.strip() else "") + f"[server]\n{line}\n"
    path.write_text(text, encoding="utf-8")
