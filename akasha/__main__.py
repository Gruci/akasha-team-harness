"""The Akasha command line. The agent engine runs these commands. People do not have to remember them."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from akasha import VERSION, config, flow, setup
from akasha.coordinator import board, resources
from akasha.core import task as tasks
from akasha.infra import github
from akasha.repo import main_root


def _root() -> Path:
    root = main_root(Path.cwd())
    if root is None:
        raise SystemExit("Akasha needs a git repository. Run the command inside a repository.")
    return root


def _show(task: tasks.Task) -> None:
    print(f"{task.id} · {task.title}\n  workflow {task.workflow} · stage {task.stage} · status {task.status} · "
          f"risk {task.risk}" + (f"\n  work copy {task.workcopy}" if task.workcopy else "")
          + (f"\n  board {task.board}" if task.board else ""))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m akasha", description=f"Akasha {VERSION}")
    commands = parser.add_subparsers(dest="command", required=True)
    made = commands.add_parser("setup", help="write akasha.toml and the files that Codex reads")
    made.add_argument("--approve-infra", metavar="ADMINISTRATOR", help="also change GitHub settings, with this approval")
    request = commands.add_parser("request", help="record a new task")
    request.add_argument("title")
    request.add_argument("--requester", required=True)
    request.add_argument("--workflow", default="feature")
    request.add_argument("--feature", default="")
    request.add_argument("--scope", nargs="*", default=[])
    request.add_argument("--contract", nargs="*", default=[])
    specify = commands.add_parser("specify", help="add completion conditions, open questions, or scope patterns")
    specify.add_argument("task")
    specify.add_argument("--condition", nargs="*", default=[])
    specify.add_argument("--question", nargs="*", default=[])
    specify.add_argument("--clear-questions", action="store_true")
    specify.add_argument("--scope", nargs="*", default=[])
    approve = commands.add_parser("approve", help="record an approval")
    approve.add_argument("task")
    approve.add_argument("--role", required=True, choices=config.ROLES)
    approve.add_argument("--by", required=True)
    resume = commands.add_parser("resume", help="open a stopped task again after a developer examined it")
    resume.add_argument("task")
    resume.add_argument("--by", required=True, help="the developer who examined the problem")
    for name, text in (("advance", "move the task to its next stage"), ("show", "show one task"),
                       ("handover", "open the pull request with the handover document")):
        commands.add_parser(name, help=text).add_argument("task")
    check = commands.add_parser("check", help="run the required checks")
    check.add_argument("task", nargs="?")
    check.add_argument("--ci", action="store_true")
    check.add_argument("--config", type=Path)
    check.add_argument("--base", default="origin/main")
    accept = commands.add_parser("accept", help="record the inspection of the requester")
    accept.add_argument("task")
    accept.add_argument("--condition")
    accept.add_argument("--result", choices=("yes", "no"), required=True)
    commands.add_parser("board", help="show the open tasks of all requesters")
    infra = commands.add_parser("infra", help="show or correct the GitHub settings")
    infra.add_argument("--apply", action="store_true")
    infra.add_argument("--by", default="", help="the administrator who approves the change")
    hook = commands.add_parser("hook", help="the entry point for agent hooks")
    hook.add_argument("--agent", choices=("claude", "codex"), default="claude")
    hook.add_argument("--event", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "hook":
        from akasha.engine import hooks
        return hooks.main(args.agent, args.event)
    if args.command == "check" and args.ci:
        result = flow.ci_check(Path.cwd(), args.config, args.base)
        for name, status in result.status.items():
            print(f"[{status}] {name}" + (f"\n{result.details[name]}" if status != "PASS" and result.details[name] else ""))
        return 0 if all(status == "PASS" for status in result.status.values()) else 1
    root = _root()
    if args.command == "setup":
        for line in setup.run(root, args.approve_infra or ""):
            print(line)
        return 0
    if args.command == "request":
        task, found = flow.start(root, args.title, args.requester, args.workflow, args.feature, args.scope,
                                 args.contract)
        _show(task)
        for item in found:
            print(f"  overlap — {item.message()}")
        return 0
    if args.command == "specify":
        task, found = flow.specify(root, args.task, args.condition, args.question, args.clear_questions, args.scope)
        _show(task)
        for item in found:
            print(f"  overlap — {item.message()}")
        return 0
    if args.command == "approve":
        _show(flow.approve(root, args.task, args.role, args.by))
        return 0
    if args.command == "resume":
        _show(flow.resume(root, args.task, args.by))
        return 0
    if args.command == "advance":
        blocked = flow.advance(root, args.task)
        _show(tasks.load(root, args.task))
        for reason in blocked:
            print(f"  blocked — {reason}")
        return 1 if blocked else 0
    if args.command == "show":
        task = tasks.load(root, args.task)
        _show(task)
        preview = config.load(root).preview
        for name, template in preview.items():
            if template:
                print(f"  preview {name}: {resources.fill(template, task.id)}")
        for name in ("scope", "risk_reasons", "conditions", "open_questions", "notes"):
            for item in getattr(task, name):
                print(f"  {name.replace('_', ' ').rstrip('s')}: {item}")
        for role, person in task.approvals.items():
            print(f"  approval: {role} {person}")
        for condition, result in task.accepted.items():
            print(f"  inspection: {'yes' if result else 'no'} — {condition}")
        for name, status in task.checks.items():
            print(f"  check {name}: {status}")
        return 0
    if args.command == "check":
        result = flow.check(root, args.task)
        task = tasks.load(root, args.task)
        for name, status in result.status.items():
            print(f"[{status}] {name}" + (f"\n{result.details[name]}" if status != "PASS" and result.details[name] else ""))
        if task.status == "stopped":
            print(task.notes[-1])
        return 0 if all(status == "PASS" for status in result.status.values()) else 1
    if args.command == "accept":
        _show(flow.accept(root, args.task, args.condition, args.result == "yes"))
        return 0
    if args.command == "handover":
        address, blocked = flow.handover(root, args.task)
        print(f"Pull request: {address}")
        for reason in blocked:
            print(f"  blocked — {reason}")
        return 1 if blocked else 0
    if args.command == "board":
        open_tasks, source = board.open_tasks(root)
        print(f"Shared task board ({source}): {len(open_tasks)} open task(s)")
        for task in open_tasks:
            print(f"- {task.id} · {task.stage} · risk {task.risk} · {task.requester or 'unknown'} · {task.title}")
        return 0
    if args.command == "infra":
        problems = github.apply(root, args.by) if args.apply else github.status(root)
        print("\n".join(f"- {item}" for item in problems) or "The GitHub settings agree with akasha.toml.")
        return 1 if problems else 0
    return 2


def run(argv: list[str] | None = None) -> int:
    """Run a command. Tell an expected problem in one line, without a traceback."""
    try:
        return main(argv)
    except (ValueError, LookupError, RuntimeError, PermissionError) as error:
        print(f"Akasha: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(run())
