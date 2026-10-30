"""Read and examine the team config (akasha.toml) and the workflows.

The commands of a task read the rules from the default branch on the server (shared), so that each computer uses the
rules that the administrators merged, also when its checkout is old. The setup reads and writes the files of the
checkout, because the administrator changes them there and opens a pull request."""

from __future__ import annotations

import re
import subprocess
import tomllib
from dataclasses import dataclass, field
from pathlib import Path, PureWindowsPath

CONFIG_FILE = "akasha.toml"
STATE_DIR = Path(".akasha") / "state"
TEAM_WORKFLOWS = Path(".akasha") / "workflows"
TEAM_CONTEXT = Path(".akasha") / "context"           # the decisions and lessons of the team, as Markdown files
# The product map tells how features, screens, data, and APIs connect: one file for each feature key in the map
# folder, so that the tasks of different features do not change the same file. Akasha 1.0.0 had one file for all.
MAP_DIR = TEAM_CONTEXT / "map"
MAP_README = "README.md"                             # the guide of the map folder. It maps no feature
LEGACY_MAP = TEAM_CONTEXT / "product-map.md"
# The device names of Windows. Windows cannot make a file or a folder with such a name, also with an extension, so
# git cannot check out a commit that has one.
WINDOWS_NAMES = "(?:con|prn|aux|nul|com[0-9]|lpt[0-9])"
BUILT_IN_WORKFLOWS = Path(__file__).parent / "workflows"

RISK_LEVELS = ("low", "medium", "high")
ROLES = ("requester", "developer", "administrator")
# The names that a workflow can use as an exit condition. akasha/core/stages.py has one test for each name.
EXIT_CONDITIONS = ("conditions_clear", "requester_approved", "impact_assessed", "risk_approvals", "scope_respected",
                   "checks_pass", "accepted", "map_current", "infra_ready", "pull_request_open", "merged")

_KEYS: dict[str, set[str] | None] = {
    "roles": {"developers", "administrators"},
    "risk": {"high", "medium"},
    "approval": {"high", "medium"},
    "checks": None,                          # the team gives the check names (_checks)
    "preview": {"command", "database"},
    "contracts": None,                       # the team gives the contract names
    "workflows": {"enabled"},
    "server": {"rules"},
    "context": {"map"},
}
# Who enforces the server rules: "github" (branch protection and auto-merge of GitHub) or "akasha" (the merge and
# watch workflows of Akasha, for a plan without branch protection). The setup selects it.
SERVER_RULES = ("github", "akasha")
# The keys of a check in [checks.<name>].
CHECK_KEYS = ("command", "cwd", "only_when", "command_windows")
# The keys of [checks] that are settings, not checks. secrets is the built-in check: it has no command.
CHECK_SETTINGS = ("required", "setup", "run_all_when")
RESERVED_CHECKS = CHECK_SETTINGS + ("secrets",)
ONE_LINE_CHECKS = ("tests", "lint")          # Akasha 1.0.0 had one command line for each of these checks
CHECK_NAME = re.compile(r"[A-Za-z0-9_-]+")
# A change of these files can break each check, so each check runs, also a check with only_when: the dependencies,
# the project settings, the team config, and the server workflows.
RUN_ALL_WHEN = ("**/requirements*.txt", "**/pyproject.toml", "**/setup.cfg", "**/setup.py", "**/Pipfile",
                "**/Pipfile.lock", "**/poetry.lock", "**/uv.lock", "**/package.json", "**/package-lock.json",
                "**/npm-shrinkwrap.json", "**/yarn.lock", "**/pnpm-lock.yaml", "**/go.mod", "**/go.sum",
                "**/build.gradle", "**/build.gradle.kts", "**/settings.gradle", "**/settings.gradle.kts",
                "**/gradle.properties", "**/pom.xml", CONFIG_FILE, ".github/workflows/**")


class ConfigError(ValueError):
    """The team config or a workflow has an incorrect shape."""


@dataclass(frozen=True)
class Stage:
    id: str
    exit: tuple[str, ...]


@dataclass(frozen=True)
class Workflow:
    name: str
    stages: tuple[Stage, ...]

    def stage(self, stage_id: str) -> Stage:
        for stage in self.stages:
            if stage.id == stage_id:
                return stage
        raise ConfigError(f"workflow {self.name} has no stage {stage_id}")

    def after(self, stage_id: str) -> str | None:
        ids = [stage.id for stage in self.stages]
        position = ids.index(stage_id)
        return ids[position + 1] if position + 1 < len(ids) else None


@dataclass(frozen=True)
class Check:
    """A check of the team in [checks.<name>]: a command that must pass."""
    command: str
    cwd: str = ""                             # the folder of the command, with / between the parts. "" is the top
    only_when: tuple[str, ...] = ()           # the check runs only when a changed file matches. () is each change
    command_windows: str = ""                 # the command on Windows, for cmd.exe


@dataclass(frozen=True)
class Team:
    developers: tuple[str, ...] = ()
    administrators: tuple[str, ...] = ()
    risk: dict[str, tuple[str, ...]] = field(default_factory=dict)
    approval: dict[str, tuple[str, ...]] = field(default_factory=dict)     # no person gate unless the team sets one
    required_checks: tuple[str, ...] = ("secrets",)
    checks: dict[str, Check] = field(default_factory=dict)          # only the checks in required_checks run
    setup: str = ""                                                  # the command that prepares a new copy
    run_all_when: tuple[str, ...] = RUN_ALL_WHEN
    preview: dict[str, str] = field(default_factory=dict)
    contracts: dict[str, tuple[str, ...]] = field(default_factory=dict)
    workflows: dict[str, Workflow] = field(default_factory=dict)     # the enabled workflows, for new requests
    defined: dict[str, Workflow] = field(default_factory=dict)       # all workflows, for the tasks that started
    server_rules: str = "github"
    map_dir: str = MAP_DIR.as_posix()                                # the map folder, with / between the parts


def _strings(value: object, where: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise ConfigError(f"{where} must be a list of text values")
    return tuple(value)


def _text(value: object, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{where} must be a text value")
    return value


def _relative(value: object, where: str, example: str, top: bool = True) -> str:
    """A folder in the repository, with / between the parts. "" is the top of the repository, unless `top` is False.
    An absolute path, a drive, and `..` are refused."""
    path = PureWindowsPath(_text(value, where).strip())       # it reads both / and \ and finds each drive
    if path.anchor or ".." in path.parts or not (path.parts or top):
        raise ConfigError(f"{CONFIG_FILE}: {where} must be a folder in the repository, for example {example}. Do not "
                          "use an absolute path or ..")
    return "/".join(path.parts)


def _folder(value: object, where: str) -> str:
    """The map folder, with / between the parts. The top of the repository is refused too: Akasha puts the folder
    outside each task scope. A device name of Windows is refused too, because each Windows checkout of the folder
    would fail."""
    folder = _relative(value, where, MAP_DIR.as_posix(), top=False)
    device = [part for part in folder.split("/") if re.fullmatch(WINDOWS_NAMES, part.split(".")[0].rstrip(" "), re.I)]
    if device:
        raise ConfigError(f"{CONFIG_FILE}: {where} cannot have the part {device[0]}: it is a device name of Windows")
    return folder


def _check(name: str, value: object) -> Check:
    """One check of [checks]: a table [checks.<name>], or one command line for tests or lint, as in Akasha 1.0.0."""
    where = f"[checks.{name}]"
    if name in RESERVED_CHECKS:
        raise ConfigError(f"{CONFIG_FILE}: {name} cannot be the name of a check in [checks] — use another name")
    if name in ONE_LINE_CHECKS and not isinstance(value, dict):
        return Check(_text(value, f"[checks] {name}"))
    if not isinstance(value, dict):
        raise ConfigError(f"{CONFIG_FILE}: unknown key {name} in [checks] — write a check as a table {where} with "
                          'command = "<command>"')
    if not CHECK_NAME.fullmatch(name):
        raise ConfigError(f"{CONFIG_FILE}: the check name {name} can have only letters, digits, - and _")
    unknown = sorted(set(value) - set(CHECK_KEYS))
    if unknown:
        raise ConfigError(f"{CONFIG_FILE}: unknown key {unknown[0]} in {where} — use {', '.join(CHECK_KEYS)}")
    only_when = _strings(value.get("only_when", []), f"{where} only_when")
    if "only_when" in value and not only_when:
        raise ConfigError(f"{CONFIG_FILE}: {where} only_when needs one or more file patterns. To run the check for "
                          "each change, remove only_when")
    return Check(command=_text(value.get("command"), f"{where} command"),
                 cwd=_relative(value.get("cwd", "."), f"{where} cwd", "frontend"), only_when=only_when,
                 command_windows=_text(value["command_windows"], f"{where} command_windows")
                 if "command_windows" in value else "")


def _checks(section: dict) -> dict[str, Check]:
    """The checks in [checks]. A setting with a table is a check with a reserved name, which _check refuses."""
    return {name: _check(name, value) for name, value in section.items()
            if name not in CHECK_SETTINGS or isinstance(value, dict)}


def _required(section: dict) -> tuple[str, ...]:
    """The names of the required checks. The default is the built-in check secrets. An empty list is refused: no
    check is not a pass, so each task would wait at its checks."""
    required = _strings(section.get("required", ["secrets"]), "[checks] required")
    if not required:
        raise ConfigError(f'{CONFIG_FILE}: [checks] required needs one or more checks, for example ["secrets"]')
    return required


def _examine_keys(data: dict) -> None:
    for section, value in data.items():
        if section not in _KEYS:
            raise ConfigError(f"{CONFIG_FILE}: unknown section [{section}] — use {', '.join(_KEYS)}")
        if not isinstance(value, dict):
            raise ConfigError(f"{CONFIG_FILE}: [{section}] must be a table")
        allowed = _KEYS[section]
        unknown = sorted(set(value) - allowed) if allowed is not None else []
        if unknown:
            raise ConfigError(f"{CONFIG_FILE}: unknown key {unknown[0]} in [{section}]")


def _workflow(name: str, text: str) -> Workflow:
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        raise ConfigError(f"{name}: {error}") from None
    flow_name = _text(data.get("name"), f"{name}: name")
    raw = data.get("stages")
    if not isinstance(raw, list) or not raw:
        raise ConfigError(f"{name}: a workflow needs one or more [[stages]]")
    stages = []
    for item in raw:
        stage_id = _text(item.get("id"), f"{name}: stage id")
        exits = _strings(item.get("exit", []), f"{name}: exit of {stage_id}")
        unknown = [condition for condition in exits if condition not in EXIT_CONDITIONS]
        if unknown:
            raise ConfigError(f"{name}: unknown exit condition {unknown[0]} — use {', '.join(EXIT_CONDITIONS)}")
        stages.append(Stage(stage_id, exits))
    if len({stage.id for stage in stages}) != len(stages):
        raise ConfigError(f"{name}: two stages have the same id")
    return Workflow(flow_name, tuple(stages))


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace")


def _shown(root: Path, ref: str, path: str) -> str | None:
    """The text of a file at a git ref, for example origin/main, or None when the ref has no such file."""
    shown = _git(root, "show", f"{ref}:{path}")
    return shown.stdout if shown.returncode == 0 else None


def _team_files(root: Path, ref: str) -> list[tuple[str, str]]:
    """The team workflows as (file name, text): from the checkout, or from the git ref."""
    if not ref:
        folder = root / TEAM_WORKFLOWS
        return [(path.name, path.read_text(encoding="utf-8")) for path in sorted(folder.glob("*.toml"))] \
            if folder.is_dir() else []
    folder = TEAM_WORKFLOWS.as_posix()
    listed = _git(root, "ls-tree", "-z", f"{ref}:{folder}")         # "<mode> <type> <object>\t<name>" for each file
    entries = [item.split("\t", 1) for item in listed.stdout.split("\0") if "\t" in item] if listed.returncode == 0 \
        else []
    names = sorted(name for kind, name in entries if kind.split()[1:2] == ["blob"] and name.endswith(".toml"))
    return [(name, text) for name in names if (text := _shown(root, ref, f"{folder}/{name}")) is not None]


def workflows(root: Path, ref: str = "") -> dict[str, Workflow]:
    """The built-in workflows. A team workflow with the same name replaces the built-in workflow. With `ref`, the
    team workflows come from that git ref."""
    found = {}
    built_in = [(path.name, path.read_text(encoding="utf-8")) for path in sorted(BUILT_IN_WORKFLOWS.glob("*.toml"))]
    for name, text in built_in + _team_files(root, ref):
        flow = _workflow(name, text)
        found[flow.name] = flow
    return found


def _parsed(text: str) -> dict:
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        raise ConfigError(f"{CONFIG_FILE}: {error}") from None


def _team(data: dict, flows: dict[str, Workflow]) -> Team:
    """Examine the data of akasha.toml and make the team rules."""
    _examine_keys(data)
    roles, risk, approval = data.get("roles", {}), data.get("risk", {}), data.get("approval", {})
    checks, preview, contracts = data.get("checks", {}), data.get("preview", {}), data.get("contracts", {})
    enabled = _strings(data["workflows"]["enabled"], "[workflows] enabled") if "workflows" in data else tuple(flows)
    missing = [name for name in enabled if name not in flows]
    if missing:
        raise ConfigError(f"{CONFIG_FILE}: workflow {missing[0]} does not exist")
    for level, holders in approval.items():
        unknown = [role for role in _strings(holders, f"[approval] {level}") if role not in ROLES]
        if unknown:
            raise ConfigError(f"{CONFIG_FILE}: unknown role {unknown[0]} in [approval] — use {', '.join(ROLES)}")
    rules = data.get("server", {}).get("rules", "github")
    if rules not in SERVER_RULES:
        raise ConfigError(f"{CONFIG_FILE}: [server] rules must be {' or '.join(SERVER_RULES)}")
    named = _checks(checks)
    return Team(
        developers=_strings(roles.get("developers", []), "[roles] developers"),
        administrators=_strings(roles.get("administrators", []), "[roles] administrators"),
        risk={level: _strings(globs, f"[risk] {level}") for level, globs in risk.items()},
        approval={level: _strings(holders, f"[approval] {level}") for level, holders in approval.items()},
        required_checks=_required(checks),
        checks=named,
        setup=_text(checks["setup"], "[checks] setup") if "setup" in checks else "",
        run_all_when=_strings(checks["run_all_when"], "[checks] run_all_when") if "run_all_when" in checks
        else RUN_ALL_WHEN,
        preview={name: _text(value, f"[preview] {name}") for name, value in preview.items()},
        contracts={name: _strings(globs, f"[contracts] {name}") for name, globs in contracts.items()},
        workflows={name: flows[name] for name in enabled},
        defined=dict(flows),
        server_rules=rules,
        map_dir=_folder(data.get("context", {}).get("map", MAP_DIR.as_posix()), "[context] map"),
    )


def load(root: Path, path: Path | None = None) -> Team:
    """The team config in this checkout of the repository at root. Without akasha.toml, Akasha uses the default rules.

    CI gives `path`: the team config from the default branch, so that a pull request cannot change its own rules."""
    path = path or root / CONFIG_FILE
    return _team(_parsed(path.read_text(encoding="utf-8")) if path.is_file() else {}, workflows(root))


def shared(root: Path, ref: str) -> Team:
    """The team config on the server: akasha.toml and the team workflows at `ref`, for example origin/main after a
    fetch. Thus each computer uses the rules that the administrators merged, also when its checkout is old. Without
    `ref`, or when `ref` has no akasha.toml, the files of this checkout, as in Akasha 1.0.0."""
    text = _shown(root, ref, CONFIG_FILE) if ref else None
    if text is None:
        return load(root)
    try:
        return _team(_parsed(text), workflows(root, ref))
    except ConfigError as error:
        raise ConfigError(f"{error} (the team config on {ref})") from None


def on_server(root: Path, ref: str) -> bool:
    """True when the git ref, for example origin/main, has akasha.toml. It uses no network."""
    return bool(ref) and _git(root, "cat-file", "-e", f"{ref}:{CONFIG_FILE}").returncode == 0


def set_server_rules(root: Path, rules: str) -> None:
    """Write the [server] rules into akasha.toml and keep each other line."""
    path = root / CONFIG_FILE
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    line = f'rules = "{rules}"'
    if re.search(r"(?m)^\[server\]\s*$", text):
        text = re.sub(r'(?m)^rules\s*=.*$', line, text, count=1) if re.search(r"(?m)^rules\s*=", text) else \
            re.sub(r"(?m)^\[server\]\s*$", f"[server]\n{line}", text, count=1)
    else:
        text = text.rstrip("\n") + ("\n\n" if text.strip() else "") + f"[server]\n{line}\n"
    path.write_text(text, encoding="utf-8")
