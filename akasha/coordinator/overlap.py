"""Find tasks that change the same feature, files, or contracts before a task starts."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from akasha.core.task import Task, active

ACTIONS = {
    "join": "Both tasks make the same feature. Join the two tasks into one.",
    "order": "Both tasks change the same files. Akasha sets the sequence: the earlier task merges first.",
    "notify": "Both tasks change the same public contract. Akasha tells the owners of the contract.",
}


@dataclass(frozen=True)
class Overlap:
    kind: str           # join, order, or notify
    other: str          # the id of the other task
    detail: str

    def message(self) -> str:
        return f"{self.other}: {self.detail}. {ACTIONS[self.kind]}"


def _fixed_part(pattern: str) -> str:
    """The part of a file pattern before its first wildcard."""
    cut = min((pattern.find(mark) for mark in "*?[" if mark in pattern), default=len(pattern))
    return pattern[:cut]


def _scopes_touch(first: Iterable[str], second: Iterable[str]) -> list[str]:
    """Pairs of patterns that can match the same file. The test is careful: when in doubt, it reports a touch."""
    found = []
    for left in first:
        for right in second:
            a, b = _fixed_part(left), _fixed_part(right)
            if a.startswith(b) or b.startswith(a):
                found.append(f"{left} and {right}")
    return found


def find(task: Task, others: Iterable[Task]) -> list[Overlap]:
    overlaps = []
    for other in others:
        if other.id == task.id or not active(other):
            continue
        if task.feature and task.feature == other.feature:
            overlaps.append(Overlap("join", other.id, f"the same feature {task.feature}"))
        touched = _scopes_touch(task.scope, other.scope)
        if touched:
            overlaps.append(Overlap("order", other.id, f"the same files ({touched[0]})"))
        shared = sorted(set(task.contracts) & set(other.contracts))
        if shared:
            overlaps.append(Overlap("notify", other.id, f"the same contract {', '.join(shared)}"))
    return overlaps
