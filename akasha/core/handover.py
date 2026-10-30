"""The handover document: the pull request text that gives a developer the evidence for a review."""

from __future__ import annotations

from akasha.core.task import Task


def render(task: Task, changed: list[str]) -> str:
    """Markdown for the pull request body. It also tells what Akasha did not verify."""
    def lines(items: list[str], empty: str) -> list[str]:
        return [f"- {item}" for item in items] or [f"- {empty}"]

    acceptance = [f"- [{'x' if task.accepted.get(condition) else ' '}] {condition}" for condition in task.conditions]
    checks = [f"- {name}: {result}" for name, result in sorted(task.checks.items())]
    unverified = [name for name, result in task.checks.items() if result == "SKIP"]
    unverified += [condition for condition in task.conditions if not task.accepted.get(condition)]
    sections = [
        f"## Request\n\n{task.title}" + (f"\n\nRequester: {task.requester}" if task.requester else ""),
        "## Completion conditions and inspection\n\n" + "\n".join(acceptance or ["- No completion conditions"]),
        f"## Risk level: {task.risk}\n\n" + "\n".join(lines(list(task.risk_reasons), "No risk rule matched")),
        "## Checks\n\n" + "\n".join(checks or ["- No checks ran"]),
        "## Changed files\n\n" + "\n".join(lines(changed, "No files changed")),
        "## Not verified\n\n" + "\n".join(lines(unverified, "Akasha verified all checks and conditions above")),
        "## Remaining risks\n\n" + "\n".join(lines(task.notes, "None recorded")),
    ]
    return "\n\n".join(sections) + "\n\n<!-- akasha-task: " + task.id + " -->\n"
