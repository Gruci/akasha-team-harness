"""Set the risk level of a change from the changed files and the risk rules of the team."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from fnmatch import fnmatchcase

from akasha.config import Team


def matches(path: str, pattern: str) -> bool:
    """True when the file matches the pattern. A leading `**/` also matches a file at the top of the repository."""
    return fnmatchcase(path, pattern) or fnmatchcase("/" + path, pattern)


@dataclass(frozen=True)
class Assessment:
    level: str
    reasons: tuple[str, ...]
    contracts: tuple[str, ...]


def assess(changed: Iterable[str], team: Team) -> Assessment:
    files = sorted(set(changed))
    level, reasons = "low", []
    for candidate in ("high", "medium"):
        hits = [f"{path} matches {pattern}" for path in files for pattern in team.risk.get(candidate, ())
                if matches(path, pattern)]
        if hits:
            level = candidate if level == "low" else level
            reasons += hits
    contracts = tuple(name for name, patterns in team.contracts.items()
                      if any(matches(path, pattern) for path in files for pattern in patterns))
    if contracts and level == "low":
        level = "medium"
        reasons.append(f"changes the public contract {', '.join(contracts)}")
    return Assessment(level, tuple(reasons), contracts)
