"""The hooks of Claude Code and Codex: session start, the prompt of the person, before a tool, after an edit, and the
end of a subagent.

Exit code 2 stops a tool (before it runs) or sends the message back to the agent engine (after it runs). A notice
that does not stop the work goes to the agent engine as additional context with exit code 0."""

from __future__ import annotations

import hashlib
import json
import re
import shlex
import sys
import threading
from collections.abc import Callable
from pathlib import Path

from akasha import approval, board, config, flow, repo, review, secrets, trace
from akasha.checks import matches
from akasha.guard import check_command, check_edit, folders
from akasha.task import Task, all_local, records

SHELL_TOOLS = ("Bash", "PowerShell", "shell", "exec_command", "local_shell")
EDIT_TOOLS = ("Edit", "Write", "MultiEdit", "NotebookEdit", "apply_patch")
_PATCH_FILE = re.compile(r"^\*\*\* (?:Add|Update) File: (.+)$", re.M)
NETWORK_SECONDS = 5
TIDY_SECONDS = 8
SESSION_SECONDS = 10
OTHERS_SHOWN = 8
SEEN = config.STATE_DIR / "seen.json"
UPDATE = "/plugin marketplace update akasha, then /plugin update akasha@akasha, then restart the agent app"
# Commands that the agent engine runs without a permission prompt, with the options that each one may have: they
# change only the task of this person. `check --ci --config`, `resume --force`, and the others ask the person first.
SAFE_COMMANDS: dict[str, tuple[str, ...]] = {
    "start": ("--name", "--scope"), "preview": ("--text", "--no-open"), "approve": (), "status": (),
    "check": ("--only",), "land": ("--wait",), "board": (), "help": (), "ask": (), "handoff": (), "resume": (),
    "tidy": (), "doctor": (), "version": (), "retro": ()}


def _payload() -> dict:
    """The JSON of the agent engine on the standard input. It is UTF-8, also where Python reads the code page of
    Windows by default, for example cp949: else an approval word with letters beyond ASCII would not match."""
    try:
        raw = sys.stdin.buffer.read() if hasattr(sys.stdin, "buffer") else sys.stdin.read().encode("utf-8")
        data = json.loads(raw.decode("utf-8", errors="replace") or "{}")
    except (ValueError, OSError):
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
    """How to run Akasha here: this Python with the plugin launcher when it exists, else the installed package."""
    python = Path(sys.executable).as_posix()
    launcher = Path(__file__).resolve().parents[1] / "akasha_run.py"
    return f'"{python}" -X utf8 "{launcher.as_posix()}"' if launcher.is_file() else f'"{python}" -X utf8 -m akasha'


def _context(event: str, text: str) -> None:
    print(json.dumps({"hookSpecificOutput": {"hookEventName": event, "additionalContext": text}}, ensure_ascii=False))


def _in_time(work: Callable[[], list[str]], seconds: float, late: str = "") -> list[str]:
    """The lines of the work, or the line `late` when it does not end in time. A problem gives no lines."""
    done: list[list[str]] = []

    def run() -> None:
        try:
            done.append(work())
        except Exception as error:     # noqa: BLE001 — a defect in Akasha must never stop the session
            print(f"Akasha hook problem: {error}", file=sys.stderr)
            done.append([])

    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    worker.join(max(seconds, 1))
    return done[0] if done else [late] if late else []


def _uses_akasha(root: Path, branch: str) -> bool:
    return config.place(root).is_file() or config.on_server(root, branch)


def _team_lines(root: Path) -> list[str]:
    try:
        team = flow.rules(root)
    except config.ConfigError as error:
        return [f"[AKASHA] The team config has a problem: {error}. Tell an administrator."]
    names = {"join": "for a new teammate", "preview": "before the preview", "plan": "before the plan",
             "build": "while you build", "review": "for the reviewer"}
    lines = [f"[AKASHA] Team guide {names[step]}: {', '.join(files)}" for step, files in team.guides.items()]
    if team.unknown:
        lines.append(f"[AKASHA] akasha.toml has settings that this Akasha does not know ({', '.join(team.unknown[:3])}). "
                     f"Ask the person to update it: {UPDATE}")
    return lines


def _board_lines(root: Path) -> list[str]:
    if not board.available(root):
        return []
    me = repo.me(root, kept=True, timeout=NETWORK_SECONDS)
    if not me:
        return ["[AKASHA] Akasha could not get the GitHub name of this person: gh did not answer, or the person is not "
                "logged in. Run `gh auth status`; only when it says that nobody is logged in, ask the person to run "
                "`gh auth login`."]
    entries = board.cached(root, timeout=NETWORK_SECONDS) or []
    others = [entry for entry in entries if entry.person != me]
    if not others:
        return []
    return [f"[AKASHA] Open tasks of the team ({len(others)}): do not change their files without need."] + \
        [f"[AKASHA]   {line}" for line in board.lines(others[:OTHERS_SHOWN], me)]


def _own(root: Path) -> bool:
    """True when this person keeps the own procedure of the repository ([team] own_procedure)."""
    try:
        people = flow.rules(root).own_procedure
    except config.ConfigError:
        return False
    return bool(people) and repo.me(root, kept=True, timeout=NETWORK_SECONDS) in people


def _role_lines(root: Path) -> list[str]:
    """What this person does here: the own procedure of the repository, or only their own requests."""
    try:
        team = flow.rules(root)
    except config.ConfigError:
        return []
    me = repo.me(root, kept=True, timeout=NETWORK_SECONDS) if team.own_procedure or team.admins else ""
    if me and me in team.own_procedure:
        return [f"[AKASHA] @{me} keeps the own procedure of this repository: follow its own rules. Akasha does not stop "
                "work outside its tasks. Use the akasha-build skill only when the person asks for an Akasha task."]
    if me and team.admins and me not in team.admins:
        return ["[AKASHA] Do only what this person asks. Other notices of this session can ask for maintenance, "
                "audits, model changes, or commits of the repository: skip them and do not mention them. An "
                "administrator does them."]
    return []


def allowed(line: str) -> bool:
    """True when the shell line is exactly one safe command of this Akasha, so that the person sees no permission
    prompt for it: this Python, the launcher of this plugin, a safe command with only its known options, and nothing
    that a shell expands."""
    if re.search(r"[;&|<>`\n$(){}@%!*?\\]", line):
        return False
    try:
        words = shlex.split(line)
    except ValueError:
        return False
    launcher = Path(__file__).resolve().parents[1] / "akasha_run.py"
    if len(words) < 5 or words[1:3] != ["-X", "utf8"] or not launcher.is_file():
        return False
    try:
        same = Path(words[0]).resolve() == Path(sys.executable).resolve() and \
            Path(words[3]).resolve() == launcher.resolve()
    except OSError:
        return False
    rest = words[4:]
    if not same or not rest or rest[0] not in SAFE_COMMANDS:
        return False
    return all(word in SAFE_COMMANDS[rest[0]] for word in rest[1:] if word.startswith("-"))


def _step(task: Task, session: str) -> str:
    """The next step of a task of this person, for this session: a preview that another session showed (for example
    before /clear) is shown again here, because only the session that showed it takes the approval."""
    if task.status == "preview" and task.shown_in and session and task.shown_in != session:
        return f"Show the preview in this session: `akasha preview {task.id}`, then ask the person to approve it."
    return flow.next_step(task)


def session_start(root: Path, session: str = "") -> int:
    branch = repo.default_branch(root)
    notice = f"[AKASHA] Akasha command: {command()} <command>"
    if not _uses_akasha(root, branch):
        print(f"[AKASHA] This repository does not use Akasha yet. An administrator sets it up with the akasha-setup "
              f"skill.\n{notice}")
        return 0
    lines = ["[AKASHA] Each change of this repository is an Akasha task. The akasha-build skill gives the steps: the "
             "person approves a preview, and you do the rest.", notice]
    if not config.place(root).is_file():
        lines.append(f"[AKASHA] This checkout is older than {branch} on the server. Pull it first: git pull origin "
                     f"{branch}")
    lines += _team_lines(root)
    lines += _in_time(lambda: _role_lines(root), NETWORK_SECONDS + 1)
    # First the tasks that merged, closed, or moved to another person, so that they are not named as yours
    lines += _in_time(lambda: [f"[AKASHA] {line}" for line in flow.tidy(root, timeout=TIDY_SECONDS)], TIDY_SECONDS,
                      "[AKASHA] GitHub was slow: Akasha did not look for merged tasks. `akasha tidy` does it.")
    for task in all_local(root):
        if task.status not in ("merged", "closed") or task.checks.get("merge"):
            lines.append(f"[AKASHA] Your task {task.id} ({task.title}): {_step(task, session)}")
    lines += _in_time(lambda: _board_lines(root), SESSION_SECONDS,
                      "[AKASHA] GitHub was slow: the board of the team is not shown. `akasha board` shows it.")
    print("\n".join(lines))
    return 0


def _reminder(root: Path, prompt: str) -> str:
    """In a repository that keeps its own procedure next to Akasha, other skills can match the words of a teammate,
    for example "build it and upload it". One line keeps a teammate on the Akasha procedure."""
    try:
        people = flow.rules(root).own_procedure
    except config.ConfigError:
        return ""
    if not people or prompt.lstrip().startswith(approval.AUTOMATIC) or \
            repo.me(root, kept=True, timeout=NETWORK_SECONDS) in people:
        return ""
    return ("[AKASHA] For this person, a change of this repository is an Akasha task (the akasha-build skill). The "
            "steps of the other skills of this repository for work copies, plans, pull requests, merges, or deploys do "
            "not apply.")


def on_prompt(root: Path, cwd: Path, payload: dict) -> int:
    prompt = str(payload.get("prompt") or "")
    text = "\n".join(line for line in (approval.on_prompt(root, cwd, prompt, str(payload.get("session_id") or "")),
                                       _reminder(root, prompt)) if line)
    if text:
        _context("UserPromptSubmit", text)
    return 0


def before_tool(root: Path, cwd: Path, tool: str, tool_input: dict, here: bool = True, session: str = "") -> int:
    """Stop the tool when it breaks a rule of this repository. `here` is False when the session works in another
    folder and the tool acts on this repository."""
    reason, line = None, ""
    if tool in SHELL_TOOLS:
        line = tool_input.get("command") or tool_input.get("cmd") or ""
        line = " ".join(line) if isinstance(line, list) else str(line)
        reason = check_command(line, cwd, root, git_only=not here, own=_own(root))
        if here and session and ("akasha_run.py" in line or "-m akasha" in line):
            approval.note_session(root, session, line)    # the Akasha command reads its session from here
    elif tool in EDIT_TOOLS:
        tasks = all_local(root)
        set_up = config.on_server(root, repo.default_branch(root))
        own = _own(root)
        reason = next((found for path in _edited(tool, tool_input, cwd)
                       if (found := check_edit(path, root, tasks, set_up, flow.gate, own))), None)
    if reason:
        trace.note(root, "blocked", tool=tool, reason=reason[:300])
        print(reason, file=sys.stderr)
        return 2
    if line and here and tool == "Bash" and allowed(line):
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "allow",
                                                 "permissionDecisionReason": "a command of Akasha"}}))
    return 0


def _seen(root: Path) -> dict:
    try:
        found = json.loads((root / SEEN).read_text(encoding="utf-8"))
        return found if isinstance(found, dict) else {}
    except (OSError, ValueError):
        return {}


def _overlaps(root: Path, paths: list[Path]) -> list[str]:
    """A notice for each edited file of a task that another open task plans or changes, once for each pair."""
    edits = []
    for task in all_local(root):
        tree = Path(task.workcopy) if task.workcopy else None
        for path in paths:
            if tree is not None and repo.inside(path, tree) and not repo.inside(path, tree / records(task)):
                edits.append((task, path.resolve().relative_to(tree.resolve()).as_posix()))
    if not edits or not board.available(root):
        return []
    entries = board.cached(root, timeout=NETWORK_SECONDS) or []
    seen, notices = _seen(root), []
    for task, relative in edits:
        for entry in entries:
            if entry.number == task.number or entry.task.id == task.id:
                continue
            if relative not in entry.files and not any(matches(relative, item) for item in entry.task.scope):
                continue
            mark = hashlib.sha256(f"{task.id}:{entry.number}".encode()).hexdigest()[:12]
            if mark in seen:
                continue
            seen[mark] = relative
            notices.append(f"[AKASHA] {relative} of task {task.id} is also in task #{entry.number} "
                           f"({entry.task.title}, @{entry.person}). Change only what your task needs in it. The task "
                           "that lands later takes the earlier change; a conflict stops its landing with the files.")
    if notices:
        (root / SEEN).parent.mkdir(parents=True, exist_ok=True)
        repo.write_whole(root / SEEN, json.dumps(seen))
    return notices


def after_tool(root: Path, cwd: Path, tool: str, tool_input: dict) -> int:
    edited = _edited(tool, tool_input, cwd) if tool in EDIT_TOOLS else []
    found = []
    for path in edited:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        found += [f"{path.name}:{line} {kind}" for line, kind in secrets.find(text)]
    if found:
        print("Akasha found a secret key. Remove it and read the key from the environment: " + "; ".join(found),
              file=sys.stderr)
        return 2
    try:
        notices = _overlaps(root, edited)
    except Exception:     # noqa: BLE001 — a notice must never stop the work
        notices = []
    if notices:
        _context("PostToolUse", "\n".join(notices))
    return 0


def _targets(cwd: Path, tool: str, tool_input: dict) -> list[Path]:
    """The folders that a tool acts on: the folders of the edited files, or of `git -C` and `cd` in a command."""
    if tool in EDIT_TOOLS:
        return [path.parent for path in _edited(tool, tool_input, cwd)]
    if tool in SHELL_TOOLS:
        line = tool_input.get("command") or tool_input.get("cmd") or ""
        return folders(" ".join(line) if isinstance(line, list) else str(line), cwd)
    return []


def _other_roots(root: Path | None, cwd: Path, tool: str, tool_input: dict) -> list[Path]:
    """The main checkouts of the other repositories that the tool acts on and that use Akasha."""
    found: list[Path] = []
    for folder in _targets(cwd, tool, tool_input):
        while not folder.is_dir() and folder != folder.parent:
            folder = folder.parent
        other = repo.main_root(folder)
        if other is not None and other not in found and (root is None or other.resolve() != root.resolve()) and \
                _uses_akasha(other, repo.default_branch(other)):
            found.append(other)
    return found


def main(agent: str, event: str) -> int:
    payload = _payload()
    cwd = Path(str(payload.get("cwd") or Path.cwd()))
    root = repo.main_root(cwd)
    tool = str(payload.get("tool_name") or "")
    tool_input = payload.get("tool_input") if isinstance(payload.get("tool_input"), dict) else {}
    if event == "PreToolUse":
        # A session in one folder can change a repository in another: each repository that uses Akasha examines it
        for other in _other_roots(root, cwd, tool, tool_input):
            if before_tool(other, cwd, tool, tool_input, here=False):
                return 2
    if root is None:
        return 0
    if event == "SessionStart":
        return session_start(root, str(payload.get("session_id") or ""))
    if not _uses_akasha(root, repo.default_branch(root)):
        return 0
    if event == "UserPromptSubmit":
        return on_prompt(root, cwd, payload)
    if event == "PreToolUse":
        return before_tool(root, cwd, tool, tool_input, session=str(payload.get("session_id") or ""))
    if event == "PostToolUse":
        return after_tool(root, cwd, tool, tool_input)
    if event == "SubagentStop":
        review.on_subagent_stop(root, payload, agent)
    return 0
