"""Read and examine the team config (akasha.toml) and the workflows.

The commands of a task read the rules from the default branch on the server (shared), so that each computer uses the
rules that the administrators merged, also when its checkout is old. The setup reads and writes the files of the
checkout, because the administrator changes them there and opens a pull request."""

from __future__ import annotations

import re
import subprocess
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

CONFIG_FILE = "akasha.toml"
STATE_DIR = Path(".akasha") / "state"
TEAM_WORKFLOWS = Path(".akasha") / "workflows"
TEAM_CONTEXT = Path(".akasha") / "context"           # the decisions and lessons of the team, as Markdown files
PRODUCT_MAP = TEAM_CONTEXT / "product-map.md"        # how features, screens, data, and APIs connect
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
    "checks": {"required", "setup", "tests", "lint"},
    "preview": {"command", "database"},
    "contracts": None,                       # the team gives the contract names
    "workflows": {"enabled"},
    "server": {"rules"},
}
# Who enforces the server rules: "github" (branch protection and auto-merge of GitHub) or "akasha" (the merge and
# watch workflows of Akasha, for a plan without branch protection). The setup selects it.
SERVER_RULES = ("github", "akasha")


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
class Team:
    developers: tuple[str, ...] = ()
    administrators: tuple[str, ...] = ()
    risk: dict[str, tuple[str, ...]] = field(default_factory=dict)
    approval: dict[str, tuple[str, ...]] = field(default_factory=dict)     # no person gate unless the team sets one
    required_checks: tuple[str, ...] = ("secrets",)
    commands: dict[str, str] = field(default_factory=dict)
    preview: dict[str, str] = field(default_factory=dict)
    contracts: dict[str, tuple[str, ...]] = field(default_factory=dict)
    workflows: dict[str, Workflow] = field(default_factory=dict)     # the enabled workflows, for new requests
    defined: dict[str, Workflow] = field(default_factory=dict)       # all workflows, for the tasks that started
    server_rules: str = "github"


def _strings(value: object, where: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise ConfigError(f"{where} must be a list of text values")
    return tuple(value)


def _text(value: object, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{where} must be a text value")
    return value


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
    return Team(
        developers=_strings(roles.get("developers", []), "[roles] developers"),
        administrators=_strings(roles.get("administrators", []), "[roles] administrators"),
        risk={level: _strings(globs, f"[risk] {level}") for level, globs in risk.items()},
        approval={level: _strings(holders, f"[approval] {level}") for level, holders in approval.items()},
        required_checks=_strings(checks.get("required", ["secrets"]), "[checks] required"),
        commands={name: _text(checks[name], f"[checks] {name}") for name in ("setup", "tests", "lint")
                  if name in checks},
        preview={name: _text(value, f"[preview] {name}") for name, value in preview.items()},
        contracts={name: _strings(globs, f"[contracts] {name}") for name, globs in contracts.items()},
        workflows={name: flows[name] for name in enabled},
        defined=dict(flows),
        server_rules=rules,
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
