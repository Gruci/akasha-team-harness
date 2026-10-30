"""Read and examine the team config (akasha.toml) and the workflows."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

CONFIG_FILE = "akasha.toml"
STATE_DIR = Path(".akasha") / "state"
TEAM_WORKFLOWS = Path(".akasha") / "workflows"
BUILT_IN_WORKFLOWS = Path(__file__).parent / "workflows"

RISK_LEVELS = ("low", "medium", "high")
ROLES = ("requester", "developer", "administrator")
# The names that a workflow can use as an exit condition. akasha/core/stages.py has one test for each name.
EXIT_CONDITIONS = ("conditions_clear", "requester_approved", "risk_approvals", "scope_respected",
                   "checks_pass", "accepted", "infra_ready", "pull_request_open")

_KEYS: dict[str, set[str] | None] = {
    "roles": {"developers", "administrators"},
    "risk": {"high", "medium"},
    "approval": {"high", "medium"},
    "checks": {"required", "tests", "lint"},
    "preview": {"command", "database"},
    "contracts": None,                       # the team gives the contract names
    "workflows": {"enabled"},
}


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
    approval: dict[str, tuple[str, ...]] = field(default_factory=lambda: {"high": ("developer",)})
    required_checks: tuple[str, ...] = ("secrets",)
    commands: dict[str, str] = field(default_factory=dict)
    preview: dict[str, str] = field(default_factory=dict)
    contracts: dict[str, tuple[str, ...]] = field(default_factory=dict)
    workflows: dict[str, Workflow] = field(default_factory=dict)


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


def _workflow(path: Path) -> Workflow:
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as error:
        raise ConfigError(f"{path.name}: {error}") from None
    name = _text(data.get("name"), f"{path.name}: name")
    raw = data.get("stages")
    if not isinstance(raw, list) or not raw:
        raise ConfigError(f"{path.name}: a workflow needs one or more [[stages]]")
    stages = []
    for item in raw:
        stage_id = _text(item.get("id"), f"{path.name}: stage id")
        exits = _strings(item.get("exit", []), f"{path.name}: exit of {stage_id}")
        unknown = [condition for condition in exits if condition not in EXIT_CONDITIONS]
        if unknown:
            raise ConfigError(f"{path.name}: unknown exit condition {unknown[0]} — use {', '.join(EXIT_CONDITIONS)}")
        stages.append(Stage(stage_id, exits))
    if len({stage.id for stage in stages}) != len(stages):
        raise ConfigError(f"{path.name}: two stages have the same id")
    return Workflow(name, tuple(stages))


def workflows(root: Path) -> dict[str, Workflow]:
    """The built-in workflows. A team workflow with the same name replaces the built-in workflow."""
    found = {}
    for folder in (BUILT_IN_WORKFLOWS, root / TEAM_WORKFLOWS):
        for path in sorted(folder.glob("*.toml")) if folder.is_dir() else ():
            flow = _workflow(path)
            found[flow.name] = flow
    return found


def load(root: Path) -> Team:
    """The team config of the repository at root. Without akasha.toml, Akasha uses the default rules."""
    path = root / CONFIG_FILE
    data: dict = {}
    if path.is_file():
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError as error:
            raise ConfigError(f"{CONFIG_FILE}: {error}") from None
    _examine_keys(data)
    roles, risk, approval = data.get("roles", {}), data.get("risk", {}), data.get("approval", {})
    checks, preview, contracts = data.get("checks", {}), data.get("preview", {}), data.get("contracts", {})
    flows = workflows(root)
    enabled = _strings(data["workflows"]["enabled"], "[workflows] enabled") if "workflows" in data else tuple(flows)
    missing = [name for name in enabled if name not in flows]
    if missing:
        raise ConfigError(f"{CONFIG_FILE}: workflow {missing[0]} does not exist")
    for level, holders in approval.items():
        unknown = [role for role in _strings(holders, f"[approval] {level}") if role not in ROLES]
        if unknown:
            raise ConfigError(f"{CONFIG_FILE}: unknown role {unknown[0]} in [approval] — use {', '.join(ROLES)}")
    return Team(
        developers=_strings(roles.get("developers", []), "[roles] developers"),
        administrators=_strings(roles.get("administrators", []), "[roles] administrators"),
        risk={level: _strings(globs, f"[risk] {level}") for level, globs in risk.items()},
        approval={level: _strings(holders, f"[approval] {level}") for level, holders in approval.items()}
        if approval else {"high": ("developer",)},
        required_checks=_strings(checks.get("required", ["secrets"]), "[checks] required"),
        commands={name: _text(checks[name], f"[checks] {name}") for name in ("tests", "lint") if name in checks},
        preview={name: _text(value, f"[preview] {name}") for name, value in preview.items()},
        contracts={name: _strings(globs, f"[contracts] {name}") for name, globs in contracts.items()},
        workflows={name: flows[name] for name in enabled},
    )
