"""The hooks of Claude Code and Codex: session start, the prompt of the person, before a tool, after an edit, and the
end of a subagent.

Exit code 2 stops a tool (before it runs) or sends the message back to the agent engine (after it runs). A notice
that does not stop the work goes to the agent engine as additional context with exit code 0."""

from __future__ import annotations

import hashlib
import json
import re
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


def _payload() -> dict:
    """The JSON of the agent engine on the standard input. It is UTF-8, also where Python reads the code page of
    Windows by default, for example cp949: else "승인" would not be an approval."""
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
    return (root / config.CONFIG_FILE).is_file() or config.on_server(root, branch)


def _team_lines(root: Path) -> list[str]:
    try:
        team = flow.rules(root)
    except config.ConfigError as error:
        return [f"[AKASHA] The team config has a problem: {error}. Tell an administrator."]
    names = {"join": "for a new teammate", "preview": "before the preview", "plan": "before the plan",
             "build": "while you build", "review": "for the reviewer"}
    return [f"[AKASHA] Team guide {names[step]}: {', '.join(files)}" for step, files in team.guides.items()]


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
    if not (root / config.CONFIG_FILE).is_file():
        lines.append(f"[AKASHA] This checkout is older than {branch} on the server. Pull it first: git pull origin "
                     f"{branch}")
    lines += _team_lines(root)
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


def on_prompt(root: Path, cwd: Path, payload: dict) -> int:
    text = approval.on_prompt(root, cwd, str(payload.get("prompt") or ""), str(payload.get("session_id") or ""))
    if text:
        _context("UserPromptSubmit", text)
    return 0


def before_tool(root: Path, cwd: Path, tool: str, tool_input: dict, here: bool = True) -> int:
    """Stop the tool when it breaks a rule of this repository. `here` is False when the session works in another
    folder and the tool acts on this repository."""
    reason = None
    if tool in SHELL_TOOLS:
        line = tool_input.get("command") or tool_input.get("cmd") or ""
        reason = check_command(" ".join(line) if isinstance(line, list) else str(line), cwd, root, git_only=not here)
    elif tool in EDIT_TOOLS:
        tasks = all_local(root)
        set_up = config.on_server(root, repo.default_branch(root))
        reason = next((found for path in _edited(tool, tool_input, cwd)
                       if (found := check_edit(path, root, tasks, set_up, flow.gate))), None)
    if reason:
        trace.note(root, "blocked", tool=tool, reason=reason[:300])
        print(reason, file=sys.stderr)
        return 2
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
        return before_tool(root, cwd, tool, tool_input)
    if event == "PostToolUse":
        return after_tool(root, cwd, tool, tool_input)
    if event == "SubagentStop":
        review.on_subagent_stop(root, payload, agent)
    return 0
