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
          + (f"\n  board {task.board}" if task.board else "")
          + (f"\n  holder {task.holder} ({task.holder_host})" if task.holder else ""))


def _uncounted(task_id: str) -> None:
    """The decision comments on the issue that do not count, so that the person can write them again."""
    for item in flow.ignored(task_id):
        print(f"  not counted — {item}")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m akasha", description=f"Akasha {VERSION}")
    commands = parser.add_subparsers(dest="command", required=True)
    made = commands.add_parser("setup", help="write akasha.toml and the files that Codex reads")
    made.add_argument("--approve-infra", metavar="ADMINISTRATOR", help="also change GitHub settings, with this approval")
    request = commands.add_parser("request", help="record a new task")
    request.add_argument("title")
    request.add_argument("--requester", default="", help="the GitHub name of the requester; default: you")
    request.add_argument("--workflow", default="feature")
    request.add_argument("--feature", default="", metavar="KEY",
                         help="the feature key, for example billing or billing/invoice. It selects the map file")
    request.add_argument("--scope", nargs="*", default=[])
    request.add_argument("--contract", nargs="*", default=[])
    request.add_argument("--builds-on", default="", metavar="TASK", help="build on an earlier task of the same feature")
    specify = commands.add_parser("specify", help="add completion conditions, open questions, or scope patterns")
    specify.add_argument("task")
    specify.add_argument("--condition", nargs="*", default=[])
    specify.add_argument("--question", nargs="*", default=[])
    specify.add_argument("--clear-questions", action="store_true")
    specify.add_argument("--scope", nargs="*", default=[])
    specify.add_argument("--builds-on", metavar='""', help='stop building on the earlier task: --builds-on ""')
    specify.add_argument("--requester", metavar="NAME",
                         help="the GitHub name of the requester, when the requester is not a GitHub account")
    specify.add_argument("--feature", metavar="KEY", help='change the feature key; --feature "" removes it')
    impact = commands.add_parser("impact", help="record the impact analysis of the agent engine")
    impact.add_argument("task")
    for name in ("features", "data", "contracts", "tasks", "rollback"):
        impact.add_argument(f"--{name}", default="")
    impact.add_argument("--map-unchanged", default="", metavar="REASON",
                        help="why the map file of the feature does not change")
    impact.add_argument("--changes-task", nargs=2, metavar=("TASK", "WHAT"),
                        help="tell the requester of an earlier task that this task changes behavior that they accepted")
    brief = commands.add_parser("brief", help="examine and record the pull request briefing")
    brief.add_argument("task")
    brief.add_argument("--file", type=Path, required=True)
    by = "the person who decides. With GitHub, it must be the GitHub account of this computer"
    approve = commands.add_parser("approve", help="record an approval")
    approve.add_argument("task")
    approve.add_argument("--role", required=True, choices=config.ROLES)
    approve.add_argument("--by", default="", help=by)
    resume = commands.add_parser("resume", help="open a stopped task again after a developer examined it")
    resume.add_argument("task")
    resume.add_argument("--by", default="", help=by)
    cancel = commands.add_parser("cancel", help="stop a task for good, for example a withdrawn request")
    cancel.add_argument("task")
    cancel.add_argument("--by", default="", help=by)
    cancel.add_argument("--reason", default="")
    for name, text in (("advance", "move the task to its next stage"), ("show", "show one task"),
                       ("handover", "open the pull request and turn on auto-merge"),
                       ("handoff", "save the work on the server and free the task for another person"),
                       ("takeover", "hold a task that another person handed off, and continue it here")):
        commands.add_parser(name, help=text).add_argument("task")
    check = commands.add_parser("check", help="run the required checks")
    check.add_argument("task", nargs="?")
    check.add_argument("--ci", action="store_true")
    check.add_argument("--config", type=Path)
    check.add_argument("--base", default="origin/main")
    accept = commands.add_parser("accept", help="record the inspection of the requester")
    accept.add_argument("task")
    accept.add_argument("--condition", help="the text or the number of the condition; default: all conditions")
    accept.add_argument("--result", choices=("yes", "no"), required=True)
    accept.add_argument("--reason", default="", help="why the result is not correct, with --result no")
    commands.add_parser("board", help="show the tasks of all requesters on the shared task board")
    infra = commands.add_parser("infra", help="show or correct the GitHub settings")
    infra.add_argument("--apply", action="store_true")
    infra.add_argument("--by", default="", help="the administrator who approves the change: the GitHub account of "
                                               "this computer")
    hook = commands.add_parser("hook", help="the entry point for agent hooks")
    hook.add_argument("--agent", choices=("claude", "codex"), default="claude")
    hook.add_argument("--event", required=True)
    helper = commands.add_parser("server", help="the merge and watch workflows of Akasha run these on GitHub")
    jobs = helper.add_subparsers(dest="job", required=True)
    merge = jobs.add_parser("merge", help="merge a pull request with the label akasha-merge after its check passed")
    merge.add_argument("--repository", required=True)
    merge.add_argument("--head-sha", required=True)
    watch = jobs.add_parser("watch", help="undo a change on the default branch that went around the check")
    watch.add_argument("--repository", required=True)
    for name in ("branch", "before", "after", "forced", "pusher"):
        watch.add_argument(f"--{name}", default="")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "hook":
        from akasha.engine import hooks
        try:
            return hooks.main(args.agent, args.event)
        except Exception as error:     # noqa: BLE001 — a defect in Akasha must never stop the work of the agent
            print(f"Akasha hook problem: {error}", file=sys.stderr)
            return 0
    if args.command == "server":                      # GitHub Actions run this in the checkout of the repository
        from akasha.infra import server
        if args.job == "merge":
            print(server.merge(Path.cwd(), args.repository, args.head_sha))
        else:
            print(server.watch(Path.cwd(), args.repository, args.branch, args.before, args.after,
                               args.forced.lower() == "true", args.pusher))
        return 0
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
                                 args.contract, args.builds_on)
        _show(task)
        for note in task.notes:
            print(f"  note — {note}")
        if flow.behind(root):                         # the main checkout is old: read the latest files on the server
            print(f"  note — {flow.behind(root)}")
        for item in found:
            print(f"  overlap — {item.message()}")
        return 0
    if args.command == "impact":
        values = {name: getattr(args, name) for name in ("features", "data", "contracts", "tasks", "rollback")}
        task, told = flow.impact(root, args.task, values, args.map_unchanged,
                                 tuple(args.changes_task) if args.changes_task else None)
        _show(task)
        if told:
            print(f"  {told}")
        return 0
    if args.command == "brief":
        problems = flow.brief(root, args.task, args.file.read_text(encoding="utf-8"))
        print("\n".join(f"- {item}" for item in problems) or "Akasha recorded the briefing.")
        return 1 if problems else 0
    if args.command == "specify":
        task, found = flow.specify(root, args.task, args.condition, args.question, args.clear_questions, args.scope,
                                   args.builds_on, args.requester, args.feature)
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
    if args.command == "cancel":
        _show(flow.cancel(root, args.task, args.by, args.reason))
        return 0
    if args.command in ("handoff", "takeover"):
        _show(getattr(flow, args.command)(root, args.task))
        return 0
    if args.command == "advance":
        blocked = flow.advance(root, args.task)
        _show(flow.load(root, args.task, write=False))
        for reason in blocked:
            print(f"  blocked — {reason}")
        _uncounted(args.task)
        return 1 if blocked else 0
    if args.command == "show":
        task = flow.load(root, args.task, write=False)
        _show(task)
        team = flow.rules(root)
        for name, template in team.preview.items():
            if template:
                print(f"  preview {name}: {resources.fill(template, task.id)}")
        if task.feature:
            print(f"  feature: {task.feature}")
        print(f"  map file: {flow.map_file(team, task.feature) or f'any file in {team.map_dir}/'}")
        if task.builds_on:
            print(f"  builds on: {task.builds_on}")
        print(f"  specification: r{task.spec_rev}")
        for number, condition in enumerate(task.conditions, 1):
            print(f"  condition {number}: {condition}")
        for name in ("scope", "risk_reasons", "open_questions", "notes"):
            for item in getattr(task, name):
                print(f"  {name.replace('_', ' ').rstrip('s')}: {item}")
        for key, text in task.impact.items():
            print(f"  impact {key}: {text}")
        if task.map_note:
            print(f"  product map unchanged: {task.map_note}")
        print(f"  briefing: {'recorded' if task.briefing else 'not recorded'}")
        for role, person in task.approvals.items():
            print(f"  approval: {role} {person}")
        for condition, result in task.accepted.items():
            print(f"  inspection: {'yes' if result else 'no'} — {condition}")
        for name, status in task.checks.items():
            print(f"  check {name}: {status}")
        if task.setup_output:
            print(f"  setup command output on this computer:\n{task.setup_output}")
        _uncounted(task.id)
        return 0
    if args.command == "check":
        result = flow.check(root, args.task)
        task = flow.load(root, args.task, write=False)
        for name, status in result.status.items():
            print(f"[{status}] {name}" + (f"\n{result.details[name]}" if status != "PASS" and result.details[name] else ""))
        for note in result.notes:
            print(note)
        if task.status == "stopped":
            print(task.notes[-1])
        return 0 if all(status == "PASS" for status in result.status.values()) else 1
    if args.command == "accept":
        _show(flow.accept(root, args.task, args.condition, args.result == "yes", args.reason))
        return 0
    if args.command == "handover":
        address, blocked = flow.handover(root, args.task)
        print(f"Pull request: {address} — auto-merge is on")
        for reason in blocked:
            print(f"  blocked — {reason}")
        return 1 if blocked else 0
    if args.command == "board":
        listed, source = board.read(root)
        print(f"Shared task board ({source}): {len(listed)} task(s)")
        for task in listed:
            held = f" · holder {task.holder or 'nobody'}" if source == "github" else ""
            print(f"- {task.id} · {task.status} · {task.stage} · risk {task.risk} · {task.requester or 'unknown'}"
                  f"{held} · feature {task.feature or 'none'} · {task.title}")
        return 0
    if args.command == "infra":
        problems = github.apply(root, args.by) if args.apply else github.status(root)
        print("\n".join(f"- {item}" for item in problems) or "The GitHub settings agree with akasha.toml.")
        print(setup.RULES_TEXT[config.load(root).server_rules])
        return 1 if problems else 0
    return 2


def run(argv: list[str] | None = None) -> int:
    """Run a command. Tell an expected problem in one line, without a traceback. One command reads the rules from
    the server once, also when it shows the task after the change."""
    try:
        with flow.one_command():
            return main(argv)
    except (ValueError, LookupError, RuntimeError, PermissionError) as error:
        print(f"Akasha: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(run())
