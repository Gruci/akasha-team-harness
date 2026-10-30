"""Move a task through the stages of its workflow. A task goes forward only when it meets each exit condition."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from akasha.config import Workflow
from akasha.core.task import Task

MAX_FAILURES = 3
IMPACT_KEYS = ("features", "data", "contracts", "tasks", "rollback")


@dataclass(frozen=True)
class Context:
    """The facts that a task file does not hold. The caller measures them before it asks to advance."""
    approval_roles: tuple[str, ...] = ()      # roles that must approve the risk level of this task
    required_checks: tuple[str, ...] = ()
    outside_scope: tuple[str, ...] = ()       # changed files that the scope does not permit
    infra_ready: bool = False
    map_changed: bool = False                 # the change updates the product map
    merged: bool = False                      # GitHub merged the pull request


def _conditions_clear(task: Task, context: Context) -> bool:
    return bool(task.conditions) and not task.open_questions


def _requester_approved(task: Task, context: Context) -> bool:
    return "requester" in task.approvals


def _impact_assessed(task: Task, context: Context) -> bool:
    return all(task.impact.get(key, "").strip() for key in IMPACT_KEYS)


def _risk_approvals(task: Task, context: Context) -> bool:
    return all(role in task.approvals for role in context.approval_roles)


def _scope_respected(task: Task, context: Context) -> bool:
    return not context.outside_scope


def _checks_pass(task: Task, context: Context) -> bool:
    return all(task.checks.get(name) == "PASS" for name in context.required_checks) and \
        "FAIL" not in task.checks.values()


def _accepted(task: Task, context: Context) -> bool:
    return bool(task.conditions) and all(task.accepted.get(condition) for condition in task.conditions)


def _map_current(task: Task, context: Context) -> bool:
    return context.map_changed or bool(task.map_note.strip())


def _infra_ready(task: Task, context: Context) -> bool:
    return context.infra_ready


def _pull_request_open(task: Task, context: Context) -> bool:
    return bool(task.pull_request)


def _merged(task: Task, context: Context) -> bool:
    return context.merged


CONDITIONS: dict[str, Callable[[Task, Context], bool]] = {
    "conditions_clear": _conditions_clear,
    "requester_approved": _requester_approved,
    "impact_assessed": _impact_assessed,
    "risk_approvals": _risk_approvals,
    "scope_respected": _scope_respected,
    "checks_pass": _checks_pass,
    "accepted": _accepted,
    "map_current": _map_current,
    "infra_ready": _infra_ready,
    "pull_request_open": _pull_request_open,
    "merged": _merged,
}

EXPLAIN = {
    "conditions_clear": "the completion conditions are not clear, or a question is open",
    "requester_approved": "the requester did not approve the specification",
    "impact_assessed": "the impact analysis is not complete — record features, data, contracts, tasks, and rollback",
    "risk_approvals": "a person with the necessary role did not approve this risk level",
    "scope_respected": "the change touches files outside the task scope",
    "checks_pass": "a required check did not pass",
    "accepted": "the requester did not accept each completion condition",
    "map_current": "the change does not update the product map, and no reason is recorded",
    "infra_ready": "the required check, branch protection, or auto-merge is not on — an administrator must correct "
                   "the GitHub settings",
    "pull_request_open": "no pull request is open",
    "merged": "the pull request did not merge yet — GitHub merges it when the required check passes",
}


def blockers(task: Task, workflow: Workflow, context: Context) -> list[str]:
    """The exit conditions of the current stage that the task does not meet."""
    if task.status != "open":
        return [f"the task is {task.status}"]
    return [name for name in workflow.stage(task.stage).exit if not CONDITIONS[name](task, context)]


def advance(task: Task, workflow: Workflow, context: Context) -> list[str]:
    """Move the task to the next stage when it meets the exit conditions. Return the conditions that block it."""
    stopped = blockers(task, workflow, context)
    if stopped:
        return stopped
    following = workflow.after(task.stage)
    if following is None:
        task.status = "done"
    else:
        task.stage = following
    return []


def record_failure(task: Task, reason: str) -> bool:
    """Count one failed repair. After MAX_FAILURES, stop the task so that a developer can examine it."""
    task.failures += 1
    task.notes.append(f"repair {task.failures} failed: {reason}")
    if task.failures >= MAX_FAILURES:
        task.status = "stopped"
        task.notes.append(f"Stopped after {MAX_FAILURES} failed repairs. A developer must examine the problem: {reason}")
        return True
    return False
