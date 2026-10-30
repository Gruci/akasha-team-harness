"""The pull request text: the briefing of the agent engine, and the Verification section from the real results."""

from __future__ import annotations

from akasha.core.task import Task


def verification(task: Task, branch: str, commands: dict[str, str]) -> str:
    """Akasha writes this section itself from the recorded checks and inspection, so that each claim is true."""
    names = [f"{name} (`{commands[name]}`)" if name in commands else name for name in sorted(task.checks)]
    lines = [f"- The required checks passed on the latest {branch}: {', '.join(names) or 'none'}."]
    if task.accepted:
        accepted = sum(1 for condition in task.conditions if task.accepted.get(condition))
        lines.append(f"- The requester accepted {accepted} of {len(task.conditions)} completion conditions "
                     "in a preview.")
    else:
        lines.append("- The workflow of this task has no inspection by the requester.")
    return "## Verification\n\n" + "\n".join(lines)


def commit_body(task: Task, branch: str, commands: dict[str, str]) -> str:
    """The body of the squash commit: the briefing, then Verification."""
    return task.briefing.strip() + "\n\n" + verification(task, branch, commands) + "\n"


def pull_request_body(task: Task, branch: str, commands: dict[str, str]) -> str:
    body = commit_body(task, branch, commands)
    if task.board:                                    # the merge closes the issue of the task on the board
        body += f"\nCloses #{task.board.rstrip('/').rsplit('/', 1)[-1]}\n"
    return body + f"\n<!-- akasha-task: {task.id} -->\n"
