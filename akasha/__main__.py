"""The Akasha command line. The agent engine runs these commands; people do not have to remember them."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from akasha import VERSION, board, checks, config, flow, land, repo, retro, setup
from akasha.task import all_local, load

EXIT = {land.MERGED: 0, land.CLOSED: 0, land.WAITING: 3}


def _root() -> Path:
    root = repo.main_root(Path.cwd())
    if root is None:
        raise SystemExit("Akasha needs a git repository. Run the command inside a repository.")
    return root


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="akasha", description=f"Akasha {VERSION}")
    commands = parser.add_subparsers(dest="command", required=True)
    made = commands.add_parser("setup", help="an administrator sets up the repository")
    made.add_argument("--apply", action="store_true", help="also change the GitHub settings (an administrator)")
    commands.add_parser("doctor", help="what this person needs to work here")
    start = commands.add_parser("start", help="start a task: a work copy and a draft pull request")
    start.add_argument("title")
    start.add_argument("--name", default="", help="a short name of the task: a to z, 0 to 9, and -")
    start.add_argument("--scope", nargs="*", default=[], help="the file patterns that the task plans to change")
    preview = commands.add_parser("preview", help="show the preview to the person and wait for the approval")
    preview.add_argument("task")
    preview.add_argument("--text", default="", help="make a plain preview from this text when there is none")
    preview.add_argument("--no-open", action="store_true", help="do not open the browser")
    review = commands.add_parser("review", help="record a self-review where no reviewer agent exists")
    review.add_argument("task")
    review.add_argument("--verdict", choices=("pass", "changes"), required=True)
    check = commands.add_parser("check", help="run the checks of the team in the work copy")
    check.add_argument("task", nargs="?")
    check.add_argument("--only", nargs="*", default=[])
    check.add_argument("--ci", action="store_true", help="the server check runs this")
    check.add_argument("--config", type=Path)
    check.add_argument("--base", default="origin/main")
    landing = commands.add_parser("land", help="make the pull request ready and merge it when the checks pass")
    landing.add_argument("task")
    landing.add_argument("--wait", type=float, default=0, help="seconds to wait for the merge")
    status = commands.add_parser("status", help="the tasks on this computer and the next step of each")
    status.add_argument("task", nargs="?")
    commands.add_parser("board", help="the open tasks of the team")
    resume = commands.add_parser("resume", help="continue a task of the board on this computer")
    resume.add_argument("task", help="the task name or the number of its pull request")
    resume.add_argument("--force", action="store_true", help="the person who holds it agrees or is gone")
    handoff = commands.add_parser("handoff", help="save the work on the server and free the task")
    handoff.add_argument("task")
    cancel = commands.add_parser("cancel", help="stop a task for good")
    cancel.add_argument("task")
    cancel.add_argument("--force", action="store_true", help="drop the changes that are not saved")
    helping = commands.add_parser("help", help="ask the administrators on the pull request of the task")
    helping.add_argument("task")
    helping.add_argument("text")
    commands.add_parser("tidy", help="remove the work copies of the merged tasks")
    commands.add_parser("retro", help="what stops the work again and again")
    commands.add_parser("version")
    hook = commands.add_parser("hook", help="the entry point of the hooks")
    hook.add_argument("--agent", choices=("claude", "codex"), default="claude")
    hook.add_argument("--event", required=True)
    server = commands.add_parser("server", help="the watch workflow runs this on GitHub")
    jobs = server.add_subparsers(dest="job", required=True)
    watch = jobs.add_parser("watch")
    watch.add_argument("--repository", required=True)
    for name in ("branch", "before", "after", "forced", "pusher"):
        watch.add_argument(f"--{name}", default="")
    return parser


def _print_checks(result: checks.Result) -> None:
    for name, status in result.status.items():
        print(f"[{status}] {name}" + (f"\n{result.details[name]}" if status in ("FAIL", "SKIP") else ""))


def _status(root: Path, task_id: str | None) -> int:
    tasks = [load(root, task_id)] if task_id else all_local(root)
    if not tasks:
        print("No task on this computer. `akasha board` shows the open tasks of the team.")
    for task in tasks:
        plan = flow.review.plan_digest(task)
        print(f"{task.id} · {task.title} · {task.status}" + (f" · {task.pr}" if task.pr else ""))
        print(f"  work copy: {task.workcopy}" + (f" · plan digest: {plan}" if plan else ""))
        print(f"  next: {flow.next_step(task)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "version":
        print(VERSION)
        return 0
    if args.command == "hook":
        from akasha import hooks
        try:
            return hooks.main(args.agent, args.event)
        except Exception as error:     # noqa: BLE001 — a defect in Akasha must never stop the agent engine
            print(f"Akasha hook problem: {error}", file=sys.stderr)
            return 0
    if args.command == "server":
        from akasha import watch
        print(watch.watch(Path.cwd(), args.repository, args.branch, args.before, args.after,
                          args.forced.lower() == "true", args.pusher))
        return 0
    if args.command == "check" and args.ci:
        team = config.load(Path.cwd(), args.config)
        result = checks.ci(team, Path.cwd(), args.base)
        _print_checks(result)
        return 0 if checks.passed(result.status) else 1
    root = _root()
    if args.command == "setup":
        # In the work copy of a task, the setup writes there: after the first setup, a change of the rules is a task
        top = repo.git(Path.cwd(), "rev-parse", "--show-toplevel").stdout.strip()
        print("\n".join(setup.run(Path(top) if top else root, args.apply)))
        return 0
    if args.command == "doctor":
        found = setup.doctor(root)
        for good, text in found:
            print(f"{'OK ' if good else 'FIX'} {text}")
        return 0 if all(good for good, _text in found) else 1
    if args.command == "start":
        task, notes = flow.start(root, args.title, args.name, tuple(args.scope))
        print(f"Task {task.id}: {task.title}\n  work copy: {task.workcopy}" + (f"\n  board: {task.pr}" if task.pr else ""))
        print("\n".join(f"  {line}" for line in notes))
        print(f"  next: {flow.next_step(task)}")
        return 0
    if args.command == "preview":
        _task, message = flow.preview(root, args.task, args.text, not args.no_open)
        print(message)
        return 0
    if args.command == "review":
        task = flow.self_review(root, args.task, args.verdict)
        print(f"Recorded a self-review: {task.review['verdict']}. next: {flow.next_step(task)}")
        return 0
    if args.command == "check":
        if not args.task:
            raise ValueError("name the task: akasha check <task>")
        result, notes = flow.check(root, args.task, tuple(args.only))
        _print_checks(result)
        print("\n".join(notes))
        return 0 if checks.passed(result.status) else 1
    if args.command == "land":
        state, lines = land.land(root, args.task, args.wait)
        print(state)
        print("\n".join(f"  {line}" for line in lines))
        return EXIT.get(state, 1)
    if args.command == "status":
        return _status(root, args.task)
    if args.command == "board":
        entries = board.read(root)
        if entries is None:
            raise RuntimeError("gh cannot read the board. Log in to GitHub: gh auth login")
        print("\n".join(board.lines(entries, repo.me(root))) or "No open task.")
        return 0
    if args.command == "resume":
        task = flow.resume(root, args.task, args.force)
        print(f"Task {task.id} continues here: {task.workcopy}\n  next: {flow.next_step(task)}")
        return 0
    if args.command == "handoff":
        print(flow.handoff(root, args.task))
        return 0
    if args.command == "cancel":
        print(flow.cancel(root, args.task, args.force))
        return 0
    if args.command == "help":
        print(flow.ask_help(root, args.task, args.text))
        return 0
    if args.command == "tidy":
        print("\n".join(flow.tidy(root)) or "Nothing to remove.")
        return 0
    if args.command == "retro":
        print("\n".join(retro.report(root)))
        return 0
    return 2


def _utf8() -> None:
    """Write UTF-8, also where Python writes the code page of Windows by default: the agent engine reads UTF-8."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def run(argv: list[str] | None = None) -> int:
    """Run a command. Tell an expected problem in one line, without a traceback."""
    _utf8()
    try:
        return main(argv)
    except (ValueError, LookupError, RuntimeError, PermissionError) as error:
        print(f"Akasha: {error}", file=sys.stderr)
        return 2


def entry() -> None:
    """The `akasha` command that pip installs."""
    sys.exit(run())


if __name__ == "__main__":
    entry()
