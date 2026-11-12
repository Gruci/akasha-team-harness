"""The team config akasha.toml: who sets up the team, which paths need a review, which checks must pass, and where
the work goes.

The commands read the config from the default branch as git fetched it last, so that each computer uses the rules
that the administrators merged, also when its checkout is old. The setup reads and writes the file in the checkout,
because the administrator changes it there and merges it with a pull request."""

from __future__ import annotations

import re
import subprocess
import tomllib
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path, PureWindowsPath
from typing import TypeVar

CONFIG_FILE = "akasha.toml"
PLACES = (CONFIG_FILE, f".github/{CONFIG_FILE}")    # where the team config can be, in this order
STATE_DIR = Path(".docs") / "state"        # the state of this computer. Git ignores it
RECORDS_DIR = ".docs/tasks"                  # the records of each task in work: the preview, the plan, the summary.
#                                              They are in the branch of the task, never in the default branch
ARCHIVE_DIR = ".docs/archive"                # the records of each merged task: YYYY/MM/YYYY-MM-DD-<task>. The landing
#                                              moves them there, and no work copy holds the archive of other tasks
WORK_DIR = ".claude/worktrees"               # a git worktree for each task: <folder>/<task>. Claude Code moves a
#                                              session into a folder here without asking, and asks anywhere else
BRANCH_PREFIX = "akasha/"                    # the branch of each task: <prefix><task>
LABEL = "akasha"                             # the label of each pull request of a task: the open ones are the board
HELP_LABEL = "akasha-help"                   # a task that waits for an administrator
SERVER_RULES = ("github", "akasha")          # who stops a merge without the checks: GitHub, or Akasha on each computer
GUIDE_STEPS = ("join", "preview", "plan", "build", "review")
CHECK_KEYS = ("command", "cwd", "only_when", "command_windows", "ready", "kind")
CHECK_KINDS = ("", "integration")            # integration: the check runs against a real store, for example a
#                                              database
CHECK_SETTINGS = ("required", "setup", "run_all_when")
# The checks of Akasha itself, in flow.py and on the server: a check of the team cannot take their names
RESERVED_CHECKS = CHECK_SETTINGS + ("secrets", "data", "screen", "version", "quick", "admin_only", "gate",
                                    "evidence", "consistency", "folders", "map", "proof", "ops", "size", "scope",
                                    "integration")
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
AKASHA_VERSION = re.compile(r"v?(\d+\.\d+\.\d+)")
AKASHA_CHECK = "akasha"                      # the name of the check of .github/workflows/akasha.yml

_KEYS: dict[str, set[str] | None] = {
    "team": {"admins", "own_procedure", "agents", "version"},
    "risk": {"paths"},
    "checks": None,                          # the team names its checks
    "ci": {"required", "runs-on", "python"},
    "work": {"folder", "branch_prefix", "records", "archive"},
    "guides": set(GUIDE_STEPS),
    "server": {"rules"},
    "core": {"paths", "areas", "used_by"},
    "deploy": {"workflow", "verify"},
    "quick": {"paths"},
    "preview": {"data", "screens", "check"},
    "definitions": {"on"},
    "pins": {"policy"},
    "review": {"command", "files", "timeout"},
    "boundaries": None,                      # the team names its boundaries
    "ops": {"migrations", "env", "off", "allow"},
    "models": {"work", "review"},
    "size": {"function", "file", "task"},
}
OPS_RULES = ("migration", "env", "timeout", "silent")
SIZE_FUNCTION, SIZE_FILE, SIZE_TASK = 100, 800, 1500


class ConfigError(ValueError):
    """The team config has an incorrect shape."""


@dataclass(frozen=True)
class Boundary:
    """One rule of [boundaries]: the files of an area are open only through its entries (private, public), some
    files do not import others (sources, forbidden), or the imports between some areas make no cycle (acyclic).
    `exceptions`: exact pairs, importer and target."""
    name: str
    private: tuple[str, ...] = ()
    public: tuple[str, ...] = ()
    sources: tuple[str, ...] = ()
    forbidden: tuple[str, ...] = ()
    exceptions: tuple[tuple[str, str], ...] = ()
    acyclic: tuple[str, ...] = ()


@dataclass(frozen=True)
class Check:
    """A check of the team in [checks.<name>]: a command that must pass."""
    command: str
    cwd: str = ""                            # the folder of the command, with / between the parts. "" is the top
    only_when: tuple[str, ...] = ()          # the check runs only when a changed file matches. () is each change
    command_windows: str = ""                # the command on Windows, for cmd.exe
    ready: str = ""                          # a command that passes when this computer can run the check (doctor)
    kind: str = ""                           # "integration": it runs against a real store, for example a database


@dataclass(frozen=True)
class Team:
    admins: tuple[str, ...] = ()             # GitHub names, in lower case, without @
    own_procedure: tuple[str, ...] = ()      # GitHub names that keep the own procedure of the repository
    # GitHub names of agent accounts: they work from the request of a person, without a preview, and that person
    # approves the result before the merge (agent.py)
    agents: tuple[str, ...] = ()
    # The version of Akasha that the team uses, for example 1.1.3: the CI and the watch install it, and each computer
    # compares its own with it (version.py). "" compares nothing
    version: str = ""
    risk_paths: tuple[str, ...] = ()         # only an administrator changes these files, for example the database
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
    archive_dir: str = ARCHIVE_DIR           # the records of the merged tasks (archive.py)
    guides: dict[str, tuple[str, ...]] = field(default_factory=dict)    # step -> team files to read in that step
    server_rules: str = "github"
    deploy_workflow: str = ""                # the workflow that puts a merged change live, for example "Deploy"
    deploy_verify: str = ""                  # the command after a deployment: it passes when the change works live
    core_paths: tuple[str, ...] = ()         # an administrator approves a change of existing lines of these files
    core_areas: tuple[str, ...] = ()         # folder patterns of one feature each, for example "domains/*"
    core_used_by: int = 2                    # a file that so many other areas import is core
    quick_paths: tuple[str, ...] = ()        # files other than code and text that a quick task can change
    data_paths: tuple[str, ...] = ()         # files that make data people see: their task defines its values (spec.py)
    screen_paths: tuple[str, ...] = ()       # files that make a screen: a task without one changes none (screen.py)
    preview_check: str = ""                  # a command of the team that examines a preview before the person sees it
    definitions_on: bool = False             # the list of the definitions holds (definitions.py)
    pins_policy: str = ""                    # "" (not answered), observe, new, or all (pins.py)
    review_command: str = ""                 # a command that reviews a plan in its own process (reviewer.py)
    review_files: tuple[str, ...] = ()       # the files of the repository that the command needs
    review_timeout: int = 900                # seconds
    boundaries: tuple[Boundary, ...] = ()    # which code may import which (boundaries.py)
    ops_migrations: tuple[str, ...] = ()     # the files that change the database. () is a folder migrations (ops.py)
    ops_env: tuple[str, ...] = ()            # the files that name each setting of the server. () is .env.example
    ops_off: tuple[str, ...] = ()            # the rules of the check ops that the team does not use
    ops_allow: tuple[tuple[str, str], ...] = ()      # (rule, file pattern): the rule does not hold for these files
    size_function: int = SIZE_FUNCTION       # lines of one function. 0 turns the limit off (size.py)
    size_file: int = SIZE_FILE               # lines of one file of code
    size_task: int = SIZE_TASK               # lines of code that one task changes
    # The model of each agent of a task, when the team chooses one: work (akasha-worker), review (akasha-reviewer).
    # The status of a task names them, and the session starts the agent with it
    models: dict[str, str] = field(default_factory=dict)
    unknown: tuple[str, ...] = ()            # settings of a newer Akasha that this one does not know

    @property
    def record_roots(self) -> tuple[str, ...]:
        """The folders that hold the records of the tasks: of the tasks in work, and the archive. They hold no
        code: a listing of the files of the repository leaves them out."""
        return (self.records_dir, self.archive_dir)

    @property
    def status_checks(self) -> tuple[str, ...]:
        """The checks that GitHub must see pass before a merge: the CI of the team and the check of Akasha. The
        check of Akasha is there in each case: the evidence of a task and the checks of Akasha do not depend on a step
        that the team adds to its own CI."""
        return tuple(dict.fromkeys(self.ci_required + (AKASHA_CHECK,)))


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


def _count(value: object, where: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ConfigError(f"{CONFIG_FILE}: {where} must be a whole number of 1 or more")
    return value


def _limit(value: object, where: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ConfigError(f"{CONFIG_FILE}: {where} must be a whole number: a limit of lines, or 0 for no limit")
    return value


def _flag(value: object, where: str) -> bool:
    if not isinstance(value, bool):
        raise ConfigError(f"{CONFIG_FILE}: {where} must be true or false")
    return value


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
    kind = value.get("kind", "")
    if kind not in CHECK_KINDS:
        raise ConfigError(f'{CONFIG_FILE}: {where} kind must be "integration": the check runs against a real store')
    return Check(command=_text(value.get("command"), f"{where} command"),
                 cwd=_relative(value.get("cwd", "."), f"{where} cwd", "frontend"), only_when=only_when,
                 command_windows=_text(value["command_windows"], f"{where} command_windows")
                 if "command_windows" in value else "",
                 ready=_text(value["ready"], f"{where} ready") if "ready" in value else "", kind=kind)


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


def _version(value: object) -> str:
    found = AKASHA_VERSION.fullmatch(value.strip()) if isinstance(value, str) else None
    if not found:
        raise ConfigError(f'{CONFIG_FILE}: [team] version must be the text of a version of Akasha, for example "1.1.3"')
    return found[1]


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


def _boundaries(section: dict) -> tuple[Boundary, ...]:
    """The boundaries of [boundaries.<name>]. Each one is of one kind: private and public, from and not, or
    acyclic."""
    found = []
    for name, value in section.items():
        where = f"[boundaries.{name}]"
        if not isinstance(value, dict) or set(value) - {"private", "public", "except", "from", "not", "acyclic"}:
            raise ConfigError(f"{CONFIG_FILE}: {where} has private and public, or from and not, or acyclic, and "
                              "except")
        pairs = []
        for item in _strings(value.get("except", []), f"{where} except"):
            one, arrow, other = item.partition("->")
            if not arrow or not one.strip() or not other.strip():
                raise ConfigError(f"{CONFIG_FILE}: {where} except is \"<file> -> <file>\", one exact pair")
            pairs.append((pattern(one.strip()), pattern(other.strip())))
        rule = Boundary(name, _patterns(value.get("private", []), f"{where} private"),
                        _patterns(value.get("public", []), f"{where} public"),
                        _patterns(value.get("from", []), f"{where} from"),
                        _patterns(value.get("not", []), f"{where} not"), tuple(pairs),
                        tuple(pattern(item.rstrip("/\\")) for item in _strings(value.get("acyclic", []),
                                                                             f"{where} acyclic")))
        kinds = [bool(rule.private), bool(rule.sources or rule.forbidden), bool(rule.acyclic)]
        if kinds.count(True) != 1 or bool(rule.sources) != bool(rule.forbidden):
            raise ConfigError(f"{CONFIG_FILE}: {where} has private and public, or from and not, or acyclic")
        found.append(rule)
    return tuple(found)


def _ops_rules(value: object, where: str) -> tuple[str, ...]:
    rules = _strings(value, where)
    wrong = [rule for rule in rules if rule not in OPS_RULES]
    if wrong:
        raise ConfigError(f"{CONFIG_FILE}: {where} names {wrong[0]}, and the rules are {', '.join(OPS_RULES)}")
    return rules


def _ops_allow(value: object) -> tuple[tuple[str, str], ...]:
    """[ops] allow: each item is "<rule>: <file pattern>"."""
    found = []
    for item in _strings(value, "[ops] allow"):
        rule, colon, files = item.partition(":")
        if not colon or rule.strip() not in OPS_RULES or not files.strip():
            raise ConfigError(f'{CONFIG_FILE}: [ops] allow is "<rule>: <file pattern>", for example "migration: '
                              f'db/migrations/0042_drop.sql". The rules are {", ".join(OPS_RULES)}')
        found.append((rule.strip(), pattern(files.strip())))
    return tuple(found)


def _policy(section: dict) -> str:
    """[pins] policy. A value that Akasha does not know is an error: it never counts as "observe"."""
    if "policy" not in section:
        return ""
    value = section["policy"]
    if value not in ("observe", "new", "all"):
        raise ConfigError(f"{CONFIG_FILE}: [pins] policy must be \"observe\", \"new\", or \"all\"")
    return value


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
    deploy, core = data.get("deploy", {}), data.get("core", {})
    admins = _names(team.get("admins", []), "[team] admins")
    own = _names(team.get("own_procedure", []), "[team] own_procedure")
    agents = _names(team.get("agents", []), "[team] agents")
    both = sorted(set(agents) & set(admins + own))
    if both:
        # An administrator is free of the locked files and of the core approval: an agent account never is
        raise ConfigError(f"{CONFIG_FILE}: @{both[0]} is in [team] agents and also in [team] admins or "
                          "own_procedure. An agent account has the rules of a teammate")
    boundaries = _boundaries(data.get("boundaries", {}))
    return Team(
        admins=admins,
        own_procedure=own,
        agents=agents,
        version=_version(team["version"]) if "version" in team else "",
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
        records_dir=(records_dir := _folder(work.get("records", RECORDS_DIR), "records", "docs/tasks", (work_dir,))),
        archive_dir=_folder(work.get("archive", ARCHIVE_DIR), "archive", "docs/archive", (work_dir, records_dir)),
        guides=_guides(data.get("guides", {})),
        server_rules=rules,
        deploy_workflow=_text(deploy["workflow"], "[deploy] workflow") if "workflow" in deploy else "",
        deploy_verify=_text(deploy["verify"], "[deploy] verify") if "verify" in deploy else "",
        core_paths=_patterns(core.get("paths", []), "[core] paths"),
        core_areas=tuple(pattern(item.rstrip("/\\")) for item in _strings(core.get("areas", []), "[core] areas")),
        core_used_by=_count(core.get("used_by", 2), "[core] used_by"),
        quick_paths=_patterns(data.get("quick", {}).get("paths", []), "[quick] paths"),
        data_paths=_patterns(data.get("preview", {}).get("data", []), "[preview] data"),
        screen_paths=_patterns(data.get("preview", {}).get("screens", []), "[preview] screens"),
        preview_check=_text(preview["check"], "[preview] check") if "check" in (preview := data.get("preview", {}))
        else "",
        definitions_on=_flag(data.get("definitions", {}).get("on", False), "[definitions] on"),
        pins_policy=_policy(data.get("pins", {})),
        review_command=_text(asked["command"], "[review] command") if "command" in (asked := data.get("review", {}))
        else "",
        review_files=_patterns(asked.get("files", []), "[review] files"),
        review_timeout=_count(asked.get("timeout", 900), "[review] timeout"),
        boundaries=boundaries,
        ops_migrations=_patterns((ops := data.get("ops", {})).get("migrations", []), "[ops] migrations"),
        ops_env=_patterns(ops.get("env", []), "[ops] env"),
        ops_off=_ops_rules(ops.get("off", []), "[ops] off"),
        ops_allow=_ops_allow(ops.get("allow", [])),
        size_function=_limit((size := data.get("size", {})).get("function", SIZE_FUNCTION), "[size] function"),
        size_file=_limit(size.get("file", SIZE_FILE), "[size] file"),
        size_task=_limit(size.get("task", SIZE_TASK), "[size] task"),
        models={step: _text(name, f"[models] {step}") for step, name in data.get("models", {}).items()},
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


_Answer = TypeVar("_Answer")
_MEMO: dict[tuple, object] | None = None     # what git answered, while a hook around a tool runs (memo)


def memo(on: bool) -> None:
    """Keep what git answers about the default branch and the team config, until `memo(False)`. Only a hook around a
    tool turns it on: it runs for an instant and asks the same questions several times. A command of Akasha never
    does: the landing fetches, and then reads the rules again."""
    global _MEMO
    _MEMO = {} if on else None


def remembered(key: tuple, find: Callable[[], _Answer]) -> _Answer:
    """The answer of `find`, kept under `key` while the memo is on."""
    if _MEMO is None:
        return find()
    if key not in _MEMO:
        _MEMO[key] = find()
    return _MEMO[key]                    # type: ignore[return-value]


def shown(root: Path, ref: str) -> str | None:
    """The text of the team config in the commit `ref`, or None when the commit has none."""
    return remembered(("shown", str(root), ref), lambda: _shown(root, ref))


def _shown(root: Path, ref: str) -> str | None:
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


def set_value(root: Path, section: str, key: str, value: str) -> None:
    """Write `key = "value"` into the section of akasha.toml, and keep each other line and the comment of the key."""
    path = place(root)
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    line = f'{key} = "{value}"'
    head = re.search(rf"(?m)^\[{section}\][ \t]*(#[^\n]*)?$", text)      # a comment may follow the header
    if not head:
        text = text.rstrip("\n") + ("\n\n" if text.strip() else "") + f"[{section}]\n{line}\n"
    else:
        after = re.search(r"(?m)^\[", text[head.end():])
        end = head.end() + after.start() if after else len(text)
        body = text[head.end():end]
        old = re.search(rf'(?m)^{key}[ \t]*=[ \t]*("[^"\n]*"|[^#\n]*?)(?=[ \t]*(#|$))', body)
        body = body[:old.start()] + line + body[old.end():] if old else f"\n{line}" + body
        text = text[:head.end()] + body + text[end:]
    path.write_text(text, encoding="utf-8")


def set_server_rules(root: Path, rules: str) -> None:
    """Write [server] rules into akasha.toml and keep each other line."""
    set_value(root, "server", "rules", rules)
