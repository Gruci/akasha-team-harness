"""The Akasha command line. The agent engine runs these commands; people do not have to remember them."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from akasha import VERSION, board, checks, config, flow, land, repo, retro, setup
from akasha.task import Task, all_local, load, records

# 3: run the same landing again. 4: an agent task waits for the person (`akasha result`, then end the turn)
EXIT = {land.MERGED: 0, land.CLOSED: 0, land.DEPLOYED: 0, land.WAITING: 3, land.DEPLOYING: 3, land.ASK: 4}


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
    made.add_argument("--new", action="store_true", help="a repository that starts now: the definitions, the "
                      "structure guide, and the files that only an administrator changes")
    made.add_argument("--stack", default="", help="the languages, for example python,typescript")
    made.add_argument("--areas", default="", help="with --new: the folder of one area, for example domains/*")
    made.add_argument("--entries", default="", help="with --new: the entry files of an area, for example "
                      "api.py,index.ts")
    commands.add_parser("doctor", help="what this person needs to work here")
    start = commands.add_parser("start", help="start a task: a work copy and a draft pull request")
    start.add_argument("title")
    start.add_argument("--name", default="", help="a short name of the task: a to z, 0 to 9, and -")
    start.add_argument("--scope", nargs="*", default=[], help="the file patterns that the task plans to change")
    start.add_argument("--quick", action="store_true",
                       help="a quick task: a small change of existing files that no other area uses")
    start.add_argument("--no-screen", action="store_true",
                       help="an administrator: a task without a screen, whose plan the person approves")
    upgrade = commands.add_parser("upgrade", help="make a quick task a full task with a preview and a plan")
    upgrade.add_argument("task")
    splitting = commands.add_parser("split", help="make a part of a task for a worker at the same time as others")
    splitting.add_argument("task")
    splitting.add_argument("part", help="a short name of the part: a to z, 0 to 9, and -")
    splitting.add_argument("--scope", nargs="+", required=True, help="the file patterns that only this part changes")
    joining = commands.add_parser("join", help="merge the parts into the work copy of the task")
    joining.add_argument("task")
    joining.add_argument("--keep", action="store_true", help="keep the work copies of the parts")
    preview = commands.add_parser("preview", help="show the preview to the person and wait for the approval")
    preview.add_argument("task")
    preview.add_argument("--text", default="", help="make a plain preview from this text when there is none")
    preview.add_argument("--no-open", action="store_true", help="do not open the browser")
    preview.add_argument("--check", action="store_true", help="only examine the preview: show nothing, and change "
                         "no state of the task (for a step in a new context)")
    approve = commands.add_parser("approve", help="record the approval from the last message of the person")
    approve.add_argument("task")
    approve.add_argument("--here", action="store_true", help="the person approves in their own terminal: for an "
                         "agent engine that has no hook for the words of the person")
    review = commands.add_parser("review", help="record a self-review where no reviewer agent exists (not in Claude "
                                                "Code)")
    review.add_argument("task")
    review.add_argument("--verdict", choices=("pass", "changes"),
                        help="a review of the agent engine itself. Without it, the reviewer command of the team runs "
                        "([review] command)")
    check = commands.add_parser("check", help="run the checks of the team in the work copy")
    check.add_argument("task", nargs="?")
    check.add_argument("--only", nargs="*", default=[], help="run only these checks and save nothing")
    check.add_argument("--ci", action="store_true", help="the server check runs this")
    check.add_argument("--config", type=Path)
    check.add_argument("--base", default="origin/main")
    landing = commands.add_parser("land", help="make the pull request ready and merge it when the checks pass")
    landing.add_argument("task")
    landing.add_argument("--wait", type=float, default=0, help="seconds to wait for the merge and the deployment")
    shown = commands.add_parser("result", help="an agent task: the result for the person, before the merge")
    shown.add_argument("task")
    status = commands.add_parser("status", help="the tasks on this computer and the next step of each")
    status.add_argument("task", nargs="?")
    status.add_argument("--resume", action="store_true", help="continue the task in this session: the session that "
                        "held it before is stopped at its next edit")
    status.add_argument("--here", action="store_true", help="with --resume: the person runs it in their own terminal")
    status.add_argument("--brief", action="store_true", help="one screen: the kind, the paths, the next step, the "
                        "digest of the review, and what stops the task")
    status.add_argument("--review", action="store_true", help="for the reviewer: what to judge again since the last "
                                                               "review, and the change of the plan")
    shown_board = commands.add_parser("board", help="the open tasks of the team")
    shown_board.add_argument("--scope", nargs="*", default=[],
                             help="only the open tasks that plan or change files of these patterns, before a start")
    resume = commands.add_parser("resume", help="continue a task of the board on this computer")
    resume.add_argument("task", help="the task name or the number of its pull request")
    resume.add_argument("--force", action="store_true", help="the person who holds it agrees or is gone")
    handoff = commands.add_parser("handoff", help="save the work on the server and free the task")
    handoff.add_argument("task")
    cancel = commands.add_parser("cancel", help="stop a task for good")
    cancel.add_argument("task")
    cancel.add_argument("--force", action="store_true", help="drop the changes that are not saved")
    helping = commands.add_parser("help", help="ask the administrators for what only they can do, on the pull "
                                                "request of the task")
    helping.add_argument("task")
    helping.add_argument("text")
    shown_map = commands.add_parser("map", help="the map of the product: what each area keeps and whom it uses, or "
                                                "the public names of one folder or file")
    shown_map.add_argument("path", nargs="?", default="")
    shown_map.add_argument("--draft", action="store_true",
                           help="for an administrator: write a first sheet (area.toml) for each area without one")
    shown_map.add_argument("--json", action="store_true", help="the map as data, for another program")
    shown_map.add_argument("--parts", action="store_true", help="the components that more than one area uses")
    shown_map.add_argument("--report", action="store_true",
                           help="for an administrator: what Akasha observes, before the team turns on a rule")
    shown_map.add_argument("--definitions", action="store_true",
                           help="the definitions of the team with their code, entries, and tests")
    shown_map.add_argument("--addresses", nargs="?", const="", default=None, metavar="START",
                           help="each address of the server, its handler, and the screens that use it")
    finding = commands.add_parser("find", help="search the names and the descriptions of the code")
    finding.add_argument("words", nargs="+")
    naming = commands.add_parser("names", help="the rules for names: the whole card, or one language")
    naming.add_argument("language", nargs="?", default="")
    commands.add_parser("tidy", help="remove the work copies of the merged tasks")
    commands.add_parser("retro", help="what stops the work again and again")
    commands.add_parser("version")
    hook = commands.add_parser("hook", help="the entry point of the hooks")
    hook.add_argument("--agent", choices=("claude", "codex"), default="claude")
    hook.add_argument("--event", default="")
    hook.add_argument("--git", default="", metavar="NAME", help="a hook of git: pre-commit or pre-push")
    hook.add_argument("rest", nargs="*", help="what git gives the hook")
    server = commands.add_parser("server", help="the watch workflow runs this on GitHub")
    jobs = server.add_subparsers(dest="job", required=True)
    watch = jobs.add_parser("watch")
    watch.add_argument("--repository", required=True)
    for name in ("branch", "before", "after", "forced", "pusher"):
        watch.add_argument(f"--{name}", default="")
    for each in (parser, *commands.choices.values()):
        each.allow_abbrev = False          # `--forc` must not mean `--force`: only a whole option counts
    return parser


def _print_checks(result: checks.Result) -> None:
    for name, status in result.status.items():
        # The notes of the consistency check are advice: the server shows them also when the check passes
        shown = status in ("FAIL", "SKIP") or (name == "consistency" and result.details.get(name))
        print(f"[{status}] {name}" + (f"\n{result.details[name]}" if shown else ""))


def _map(root: Path, args) -> list[str]:
    """The answers of `akasha map` and `akasha find`: of the work copy where the command runs, else of the main
    checkout."""
    from akasha import codemap
    top = repo.git(Path.cwd(), "rev-parse", "--show-toplevel").stdout.strip()
    here = Path(top) if top else root
    if args.command == "map" and args.report:
        from akasha import report
        return report.lines(here, flow.rules(root), root)
    from akasha import definitions, sheets
    # A draft is of this checkout: an administrator names the areas in its akasha.toml and draws the map in one task
    team = config.load(here) if args.command == "map" and args.draft else flow.rules(root)
    found = codemap.Map(here, team, root)
    if args.command == "map" and args.draft:
        if not team.core_areas:
            return ["akasha.toml names no areas. Write [core] areas first, for example areas = [\"domains/*\"]: each "
                    "folder that matches is one area"]
        written = sheets.draft(team, here, found)
        return [f"wrote {path}" for path in written] + (
            ["Read each sheet against its code: correct the purpose (one line: what the area keeps) and `uses`. "
             "Then `akasha map` shows the map, and the check `map` holds it."] if written else
            ["each area has a sheet already: `akasha map` shows the map"])
    if args.command == "map" and args.json:
        return [sheets.as_json(team, here, found)]
    try:
        listed = definitions.parse(definitions.place(here).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        listed = []
    if args.command == "find":
        hits = found.find(args.words)
        words = [word.lower() for word in args.words]
        named = [f"definition — {definitions.line_of(item)}" for item in listed
                 if any(word in " ".join((item.key, *item.words)).lower() for word in words)]
        return named + [codemap.line_of(path, symbol) for path, symbol in hits] or \
            [f"no public name fits {' '.join(args.words)}"]
    if args.definitions:
        return [definitions.line_of(item) for item in listed] or \
            [f"no definition in {definitions.FILE}" if flow.rules(root).definitions_on else
             "the definitions are off: an administrator turns them on with [definitions] on = true"]
    if args.parts:
        return [f"{path}: {users} files in {areas} other areas import this file"
                for path, users, areas in found.shared_parts()] or ["no component that more than one area uses"]
    if args.addresses is not None:
        return [f"{method} {address} — {handler}:{line}" + (f" — used by {', '.join(screens[:5])}" if screens else "")
                for method, address, handler, line, screens in found.routes(args.addresses)] or \
            ["no address of a server"]
    if args.path:
        return codemap.listing(found, args.path)
    files = repo.paths(here, team.record_roots + (team.work_dir,), others=True)
    if sheets.drawn(team, files):
        return sheets.overview(team, here, found)
    return codemap.overview(found) + (["the map is not drawn yet: an administrator runs `akasha map --draft` in a task"]
                                      if team.core_areas else [])


def _status(root: Path, task_id: str | None) -> int:
    tasks = [load(root, task_id)] if task_id else all_local(root)
    if not tasks:
        print("No task on this computer. `akasha board` shows the open tasks of the team.")
    for task in tasks:
        plan = flow.review.subject_digest(task)
        what = "change digest" if task.kind == "quick" else "plan digest"
        print(f"{task.id} · {task.title} · {task.status}" + (f" · {task.kind}" if task.kind != "full" else "")
              + (f" · {task.pr}" if task.pr else ""))
        print(f"  work copy: {task.workcopy} · records: {records(task)}/" + (f" · {what}: {plan}" if plan else ""))
        print(f"  next: {flow.next_step(task)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "version":
        print(VERSION)
        return 0
    if args.command == "hook" and args.git:
        from akasha import githooks
        try:
            return githooks.main(args.git, repo.main_root(Path.cwd()), Path.cwd())
        except Exception as error:     # noqa: BLE001 — a defect in Akasha must never stop git
            print(f"Akasha hook problem: {error}", file=sys.stderr)
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
        problem = watch.version_problem(Path.cwd())
        if problem:
            print(problem, file=sys.stderr)
            return 1
        return 0
    if args.command == "check" and args.ci:
        team = config.load(Path.cwd(), args.config)
        # The workflow gives the author and the branch of the pull request in the environment, never in the text of
        # a shell command
        result = checks.ci(team, Path.cwd(), args.base, os.environ.get("AKASHA_PR_AUTHOR", ""),
                           os.environ.get("AKASHA_PR_HEAD", ""))
        _print_checks(result)
        return 0 if checks.passed(result.status) else 1
    root = _root()
    if args.command == "setup":
        # In the work copy of a task, the setup writes there: after the first setup, a change of the rules is a task
        top = repo.git(Path.cwd(), "rev-parse", "--show-toplevel").stdout.strip()
        choice = setup.Choice(args.new, tuple(item for item in args.stack.split(",") if item.strip()),
                              config.pattern(args.areas.rstrip("/")) if args.areas else "",
                              tuple(item.strip() for item in args.entries.split(",") if item.strip()))
        print("\n".join(setup.run(Path(top) if top else root, args.apply, choice)))
        return 0
    if args.command == "doctor":
        found = setup.doctor(root)
        for good, text in found:
            print(f"{'OK ' if good else 'FIX'} {text}")
        return 0 if all(good for good, _text in found) else 1
    if args.command == "names":
        from akasha import naming
        print(naming.of_language(args.language) if args.language else naming.card())
        return 0
    if args.command in ("map", "find"):
        for line in _map(root, args):
            print(line)
        return 0
    if args.command == "start":
        task, notes = flow.start(root, args.title, args.name, tuple(args.scope), args.quick, args.no_screen)
        print(f"Task {task.id}: {task.title}\n  work copy: {task.workcopy}\n  records: {records(task)}/"
              + (f"\n  board: {task.pr}" if task.pr else ""))
        print("\n".join(f"  {line}" for line in notes))
        print(f"  next: {flow.next_step(task)}")
        return 0
    if args.command == "preview":
        if args.check:
            print(flow.preview_check(root, args.task))
            return 0
        _task, message = flow.preview(root, args.task, args.text, not args.no_open)
        print(message)
        return 0
    if args.command == "approve":
        _task, message = flow.approve(root, args.task, here=args.here)
        print(message)
        return 0
    if args.command == "review":
        if not args.verdict:
            from akasha import reviewer
            task = reviewer.run(root, args.task)
            print(f"The reviewer command gave {task.review['verdict']}" + flow.review.told(task)
                  + f". next: {flow.next_step(task)}")
            return 0
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
    if args.command == "result":
        print(flow.result(root, args.task))
        return 0
    if args.command == "status":
        if args.resume:
            if not args.task:
                raise ValueError("name the task: akasha status <task> --resume")
            _task, message = flow.take(root, args.task, here=args.here)
            print(message)
            return 0
        if args.brief:
            if not args.task:
                raise ValueError("name the task: akasha status <task> --brief")
            print(flow.brief(root, args.task))
            return 0
        if args.review:
            if not args.task:
                raise ValueError("name the task: akasha status <task> --review")
            task = load(root, args.task)
            print("\n".join((flow.review.brief(task), flow.review_names(root, task))))
            return 0
        return _status(root, args.task)
    if args.command == "split":
        part, notes = flow.split(root, args.task, args.part, tuple(args.scope))
        print(f"Part {part['name']} of task {args.task}\n  work copy: {part['workcopy']}\n  branch: {part['branch']} "
              f"(on this computer only)\n  scope: {', '.join(part['scope'])}")
        print("\n".join(f"  {line}" for line in notes))
        print(f"  next: give the worker the work copy and the scope. When each part is done: akasha join {args.task}")
        return 0
    if args.command == "join":
        joined = flow.join(root, args.task, args.keep)
        print((f"Joined {', '.join(joined)} into task {args.task}." if joined else
               f"No part of task {args.task} had new work.") + f" next: akasha check {args.task}")
        return 0
    if args.command == "upgrade":
        task = flow.upgrade(root, args.task)
        print(f"Task {task.id} is a full task now. next: {flow.next_step(task)}")
        return 0
    if args.command == "board":
        if not board.available(root):
            print("origin of this repository is not on GitHub, so there is no board of the team")
            return 0
        entries = board.read(root)
        if entries is None:
            raise RuntimeError("gh cannot read the board. Log in to GitHub: gh auth login")
        if args.scope:
            planned = Task(id="", title="", scope=[config.pattern(item) for item in args.scope])
            print("\n".join(board.overlaps(planned, [], entries)) or "No open task plans or changes these files.")
            return 0
        print("\n".join(board.lines(entries, repo.me(root))) or "No open task.")
        return 0
    if args.command == "resume":
        task, notes = flow.resume(root, args.task, args.force)
        print(f"Task {task.id} continues here: {task.workcopy}")
        print("\n".join(f"  {line}" for line in notes + [f"next: {flow.next_step(task)}"]))
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
