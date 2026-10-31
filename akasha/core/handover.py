"""The pull request text: the briefing of the agent engine, and the Verification section from the real results."""

from __future__ import annotations

from akasha.config import Check
from akasha.core.task import Task
from akasha.validators.runner import command

TASK_MARK = "<!-- akasha-task:"                       # the mark of the task in the body of its pull request


def _named(name: str, checks: dict[str, Check]) -> str:
    """The name of a check with the command that ran, and with its folder when the command does not run at the top.
    The handover runs the checks on this computer, so the command is the command of this computer (runner.command)."""
    check = checks.get(name)
    if check is None:
        return name                                   # the built-in check secrets has no command
    return f"{name} (`{command(check)}`" + (f" in `{check.cwd}`" if check.cwd else "") + ")"


def verification(task: Task, branch: str, checks: dict[str, Check]) -> str:
    """Akasha writes this section itself from the recorded checks and inspection, so that each claim is true. A check
    that did not run, because the change touches no file that it examines, is not told as a pass. Both go in one
    item, so that the commit body stays under 40 lines (briefing.MAX_LINES)."""
    ran = [_named(name, checks) for name in sorted(task.checks) if task.checks[name] == "PASS"]
    idle = [name for name in sorted(task.checks) if task.checks[name] == "NOT_NEEDED"]
    lines = [f"- The required checks passed on the latest {branch}: {', '.join(ran) or 'none'}."
             + (f" These checks did not run, because the change touches no file that they examine: "
                f"{', '.join(idle)}." if idle else "")]
    if task.accepted:
        accepted = sum(1 for condition in task.conditions if task.accepted.get(condition))
        lines.append(f"- The requester accepted {accepted} of {len(task.conditions)} completion conditions "
                     "in a preview.")
    else:
        lines.append("- The workflow of this task has no inspection by the requester.")
    return "## Verification\n\n" + "\n".join(lines)


def commit_body(task: Task, branch: str, checks: dict[str, Check]) -> str:
    """The body of the squash commit: the briefing, then Verification."""
    return task.briefing.strip() + "\n\n" + verification(task, branch, checks) + "\n"


def pull_request_body(task: Task, branch: str, checks: dict[str, Check]) -> str:
    body = commit_body(task, branch, checks)
    if task.board:                                    # the merge closes the issue of the task on the board
        body += f"\nCloses #{task.board.rstrip('/').rsplit('/', 1)[-1]}\n"
    return body + f"\n{TASK_MARK} {task.id} -->\n"
