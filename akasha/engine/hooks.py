"""Hook entry for Claude Code and Codex: session start, before a tool runs, after a file changes, and turn end.

Exit code 2 stops the tool call (before it runs) or sends the message back to the agent (after it runs). A notice
that does not stop the work goes to the agent as additional context with exit code 0. Both agent engines give the
standard output of the session start to the agent.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path

from akasha import config, flow, repo
from akasha.coordinator import board, overlap
from akasha.core import risk
from akasha.core import task as tasks
from akasha.core import workcopy
from akasha.infra import github
from akasha.repo import main_root
from akasha.validators import guard, secrets

SHELL_TOOLS = ("Bash", "PowerShell", "shell")
EDIT_TOOLS = ("Edit", "Write", "MultiEdit", "NotebookEdit", "apply_patch")
_PATCH_FILE = re.compile(r"^\*\*\* (?:Add|Update) File: (.+)$", re.M)
SETUP_HINT = "This repository does not use Akasha yet. To start, use the akasha-setup skill."
# Each network call of a hook waits this long at most, so that the notice comes in the time limit of the hook
NETWORK_SECONDS = 5
SESSION_SECONDS = 15        # the session start notice comes in this time. Claude Code stops the hook after 20 seconds
MAP_NAMES = 30                                         # the session start names this many feature keys at most
SEEN_FILE = config.STATE_DIR / "seen.json"             # the overlap notices that the hook after an edit gave


def _payload() -> dict:
    try:
        data = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _edited(tool: str, tool_input: dict, cwd: Path) -> list[Path]:
    if tool == "apply_patch":
        text = tool_input.get("input") or tool_input.get("command") or ""
        names = _PATCH_FILE.findall(text if isinstance(text, str) else "")
    else:
        names = [tool_input.get("file_path") or tool_input.get("notebook_path") or ""]
    return [(cwd / name).resolve() if not Path(name).is_absolute() else Path(name) for name in names if name]


def command() -> str:
    """How to run Akasha here: this Python with the plugin launcher when it exists, else with the installed package.

    Some computers have only `python3` and no `python`, so the command names the Python that runs this hook."""
    python = Path(sys.executable).as_posix()
    launcher = Path(__file__).resolve().parents[2] / "akasha_run.py"
    return f'"{python}" -X utf8 "{launcher.as_posix()}"' if launcher.is_file() else f'"{python}" -X utf8 -m akasha'


def _server_only(root: Path) -> str:
    """The default branch that has akasha.toml when this checkout has none, else "". For example, the setup pull
    request merged, and this person did not pull since. It uses no network: it reads what git fetched last."""
    if (root / config.CONFIG_FILE).is_file():
        return ""
    branch = github.known_branch(root)
    return branch if branch and config.on_server(root, f"origin/{branch}") else ""


def _uses_akasha(root: Path) -> bool:
    """True when this checkout or the default branch on the server has akasha.toml. Then the hooks run."""
    return (root / config.CONFIG_FILE).is_file() or bool(_server_only(root))


def _rules(root: Path) -> config.Team:
    """The team rules on the default branch as git fetched it last: the hooks use no network for them. A team config
    with a problem gives the default rules here, so that the other notices stay. The commands of a task tell the
    problem."""
    branch = github.known_branch(root)
    try:
        return config.shared(root, f"origin/{branch}" if branch else "")
    except (config.ConfigError, LookupError, ValueError, TypeError, AttributeError, OSError):
        return config.Team()


def session_start(root: Path) -> int:
    """The notice at the start of a session. Claude Code and Codex give it to the agent engine.

    The lines without the network always come: the board and the GitHub name wait NETWORK_SECONDS each at most, and
    the examination of the server rules gets the rest of SESSION_SECONDS (_in_time)."""
    started = time.monotonic()
    notice = f"[AKASHA] Akasha command: {command()} <command>"
    if not _uses_akasha(root):
        print(f"[AKASHA] {SETUP_HINT}\n{notice}")
        return 0
    lines = ["[AKASHA] Do each change as an Akasha task. The akasha-request skill gives the procedure.", notice]
    pull = _server_only(root)
    if pull:
        lines.append(f"[AKASHA] The default branch {pull} on the server uses Akasha, but this checkout is old and has "
                     f"no {config.CONFIG_FILE}. Do not set up Akasha again. Pull the default branch first: git pull "
                     f"origin {pull}")
    context = sorted(path.relative_to(root).as_posix() for path in (root / config.TEAM_CONTEXT).glob("*.md"))
    if context:
        lines.append(f"[AKASHA] Read the team context before you write a specification: {', '.join(context)}")
    team = _rules(root)
    lines += _map_lines(root, team)
    lines += _task_lines(root, team)
    lines += _in_time(lambda: _server_notice(root), SESSION_SECONDS - (time.monotonic() - started))
    print("\n".join(lines))
    return 0


def _in_time(work: Callable[[], list[str]], seconds: float) -> list[str]:
    """The lines of the work, or no lines when the work does not end in `seconds`, one second at least. Such work,
    for example an examination of the server rules on a slow GitHub, stops when the hook ends, and the next session
    start tries again. The handover examines the server rules itself.

    A problem in the work gives no lines and one line on the standard error, as for each other hook (__main__)."""
    done: list[list[str]] = []

    def run() -> None:
        try:
            done.append(work())
        except Exception as error:     # noqa: BLE001 — a defect in Akasha must never stop the other lines
            print(f"Akasha hook problem: {error}", file=sys.stderr)
            done.append([])

    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    worker.join(max(seconds, 1))
    return done[0] if done else []


def _map_files(root: Path, team: config.Team) -> list[str]:
    """The files in the map folder, relative to the top of the repository: on the default branch as git fetched it
    last, so that an old checkout also knows the map files that other people merged. Else in this checkout."""
    branch = github.known_branch(root)
    listed = workcopy.git(root, "ls-tree", "-r", "-z", "--name-only", "--full-tree", f"origin/{branch}", "--",
                          team.map_dir) if branch else None
    if listed is not None and listed.returncode == 0:
        return [path for path in listed.stdout.split("\0") if path]
    folder = root / team.map_dir
    return [path.relative_to(root).as_posix() for path in folder.rglob("*.md") if path.is_file()] \
        if folder.is_dir() else []


def _map_lines(root: Path, team: config.Team) -> list[str]:
    """Where the map file of each feature is, and the feature keys that have a map file. A new task takes one of
    these keys when it fits."""
    prefix = team.map_dir + "/"
    names = sorted(path[len(prefix):-len(".md")] for path in _map_files(root, team)
                   if path.startswith(prefix) and path.endswith(".md"))
    keys = [name for name in names if flow.FEATURE_KEY.fullmatch(name)]      # not the guide README.md
    lines = [f"[AKASHA] Product map: {team.map_dir}/<feature key>.md. Read the file of the feature before the impact "
             "analysis, and update it before the handover."]
    if keys:
        more = f", and {len(keys) - MAP_NAMES} more" if len(keys) > MAP_NAMES else ""
        lines.append(f"[AKASHA] Feature keys with a map file: {', '.join(keys[:MAP_NAMES])}{more}")
    return lines


def _task_lines(root: Path, team: config.Team) -> list[str]:
    """The active tasks of this person. With GitHub, the tasks on the board that this person holds or requested, and
    the count of new comments on the issue of each task (flow.fresh). The board and the comments come in one call of
    gh. Without GitHub, or when gh does not answer in NETWORK_SECONDS, the tasks on this computer."""
    found = [task for task in tasks.all_tasks(root) if tasks.active(task)]
    listed = board.overview(root, timeout=NETWORK_SECONDS) if board.available(root) else None
    name = repo.me(root, timeout=NETWORK_SECONDS) if listed is not None else ""
    if not name:
        return [_task_line(task, "", "", 0) for task in found]
    here = repo.host(root)
    listed += [(task, []) for task in found if not task.board]          # its first board write failed
    return [_task_line(task, name, here, len(flow.fresh(root, team, task, comments, name)))
            for task, comments in listed
            if tasks.active(task) and name in (task.holder, task.requester.lstrip("@").lower())]


def _task_line(task: tasks.Task, name: str, here: str, news: int) -> str:
    """One task for the session start notice, with the count of its new comments."""
    told = f". {news} new comment(s) on its issue: the Akasha command show {task.id} shows them" if news else ""
    return (f"[AKASHA] Task {task.id}: {task.status}, stage {task.stage}, risk {task.risk}"
            f"{_held_by(task, name, here)}, {task.title}{told}")


def _held_by(task: tasks.Task, name: str, here: str) -> str:
    """Who holds the task, for the session start notice. The holder is a person in one copy of the repository.
    Nothing without GitHub."""
    if not name:
        return ""
    if (task.holder, task.holder_host) == (name, here):
        return ", you hold it"
    if task.holder == name:
        return ", you hold it in another copy: hand it off there, then take it over here"
    return f", {task.holder} holds it" if task.holder else ", nobody holds it"


def _server_notice(root: Path) -> list[str]:
    """Nothing when the server rules are on. Else who can turn them on: this person, or an administrator."""
    known = github.readiness(root)
    if not known["problems"]:
        return []
    if known.get("admin"):
        who = "[AKASHA] You administer this repository. To turn the server rules on, use the akasha-setup skill."
    else:
        who = "[AKASHA] Ask an administrator of the repository to turn them on. You can work now; the handover waits."
    return [f"[AKASHA] The server rules of this repository are off: {known['problems'][0]}.", who]


def before_tool(root: Path, cwd: Path, tool: str, tool_input: dict) -> int:
    if tool in SHELL_TOOLS:
        reason = guard.check_command(str(tool_input.get("command") or ""), cwd, root)
    elif tool in EDIT_TOOLS:
        known = tasks.all_tasks(root)
        reasons = [guard.check_edit(path, root, known) for path in _edited(tool, tool_input, cwd)]
        reason = next((item for item in reasons if item), None)
    else:
        reason = None
    if reason:
        print(reason, file=sys.stderr)
        return 2
    return 0


def after_tool(root: Path, cwd: Path, tool: str, tool_input: dict) -> int:
    """After an edit. A secret key sends the message back to the agent engine (exit 2), with the overlap notices. Else
    an overlap notice goes to the agent engine as additional context, and the work continues (_overlap_notices)."""
    edited = _edited(tool, tool_input, cwd) if tool in EDIT_TOOLS else []
    found = []
    for path in edited:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        found += [f"{path.name}:{line} {kind}" for line, kind in secrets.find(text)]
    try:
        notices = _overlap_notices(root, edited)
    except Exception:     # noqa: BLE001 — a problem of an overlap notice must never hide a secret key
        notices = []
    if found:
        print("\n".join(["Akasha found a secret key. Remove it and read the key from the environment: "
                         + "; ".join(found)] + notices), file=sys.stderr)
        return 2
    if notices:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse",
                                                 "additionalContext": "\n".join(notices)}}))
    return 0


def _work_copy_of(root: Path, known: list[tasks.Task], path: Path) -> tuple[tasks.Task, str] | None:
    """The task whose work copy has the file, and the path relative to the top of the work copy, as in a scope. None
    outside each work copy, and for a task that another copy of the repository holds."""
    for task in known:
        try:
            relative = path.resolve().relative_to(Path(task.workcopy).resolve()).as_posix()
        except (ValueError, OSError):
            continue
        return (task, relative) if not task.holder_host or task.holder_host == repo.host(root) else None
    return None


def _seen(root: Path, ids: set[str]) -> dict[str, dict[str, str]]:
    """The overlap notices that the agent engine got: for each task here, the other tasks and their scopes. The
    notices of the tasks that are not active here any more go away."""
    try:
        seen = json.loads((root / SEEN_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {key: value for key, value in seen.items() if key in ids and isinstance(value, dict)} \
        if isinstance(seen, dict) else {}


def _overlap_notices(root: Path, paths: list[Path]) -> list[str]:
    """A notice for each task of this copy of the repository whose edited files are in the scope of another open
    task. Only the files in the work copy count: the team context and the map folder are outside each scope
    (flow.outside_scope), and a task and the task that it builds on are one line of work.

    The agent engine gets the notice once for each pair of tasks, until the scope of the other task changes
    (SEEN_FILE). With GitHub, the other tasks come from the copy of the board of the hooks (board.cached)."""
    local = tasks.all_tasks(root)
    known = [task for task in local if tasks.active(task) and task.workcopy and Path(task.workcopy).is_dir()]
    edited = [found for path in paths if (found := _work_copy_of(root, known, path)) is not None]
    if not edited:
        return []
    team = _rules(root)
    free, edits = (flow.CONTEXT_PREFIX, team.map_dir + "/"), {}
    for task, relative in edited:
        if not relative.startswith(free):
            edits.setdefault(task.id, (task, []))[1].append(relative)
    others = board.cached(root, timeout=NETWORK_SECONDS) if edits and board.available(root) else []
    if not edits or others is None:
        return []                                     # when gh does not answer: no notice, and the work continues
    others += [task for task in local if tasks.active(task) and not task.board]
    seen, notices = _seen(root, {task.id for task in known}), []
    for task, changed in edits.values():
        for other in others:
            if other.id == task.id or not tasks.active(other) or task.id == other.builds_on \
                    or other.id == task.builds_on:
                continue
            hits = [(path, pattern) for path in changed for pattern in other.scope if risk.matches(path, pattern)]
            mark = hashlib.sha256("\n".join(sorted(other.scope)).encode("utf-8")).hexdigest()[:16]
            if not hits or (seen.get(task.id) or {}).get(other.id) == mark:
                continue
            seen.setdefault(task.id, {})[other.id] = mark
            files = ", ".join(dict.fromkeys(path for path, _pattern in hits))
            patterns = ", ".join(dict.fromkeys(pattern for _path, pattern in hits))
            notices.append(f"[AKASHA] {files} of the task {task.id} is also in the scope of the task {other.id} "
                           f"({other.title}, requester {other.requester or 'unknown'}): {patterns}. "
                           f"{overlap.ACTIONS['order']} Continue the work, and name the task {other.id} in the impact "
                           f"analysis of {task.id}.")
    if notices:
        try:
            (root / SEEN_FILE).parent.mkdir(parents=True, exist_ok=True)
            repo.write_whole(root / SEEN_FILE, json.dumps(seen))
        except OSError:
            pass                                      # another hook writes it now: a notice can come once more
    return notices


def turn_end(root: Path) -> int:
    """Tell the user about each task with a work copy on this computer that needs a person: a stopped task, or
    changes outside the task scope. A task that this computer handed off has no work copy here. With GitHub, a
    developer opens a stopped task again with the decision comment /resume on its issue."""
    found, team = [], None
    for task in tasks.all_tasks(root):
        if not task.workcopy or not Path(task.workcopy).is_dir():
            continue
        if task.status == "stopped":
            found.append(f"Task {task.id} stopped after failed repairs. A developer must examine it"
                         + (f", then write /resume as a new comment on {task.board}." if task.board else "."))
        elif task.status == "open":
            team = team or _rules(root)
            outside = flow.outside_scope(team, task, workcopy.changed_files(task))
            if outside:
                found.append(f"Task {task.id} changed files outside its scope: {', '.join(outside[:5])}.")
    if found:
        print(json.dumps({"systemMessage": "[AKASHA] " + " ".join(found)}))
    return 0


def main(agent: str, event: str) -> int:
    payload = _payload()
    cwd = Path(str(payload.get("cwd") or Path.cwd()))
    root = main_root(cwd)
    if root is None:
        return 0
    if event == "SessionStart":
        return session_start(root)
    if not _uses_akasha(root):                        # an old checkout of a repository with Akasha keeps the guard
        return 0
    tool = str(payload.get("tool_name") or "")
    tool_input = payload.get("tool_input") if isinstance(payload.get("tool_input"), dict) else {}
    if event == "PreToolUse":
        return before_tool(root, cwd, tool, tool_input)
    if event == "PostToolUse":
        return after_tool(root, cwd, tool, tool_input)
    if event == "Stop":
        return turn_end(root)
    return 0
