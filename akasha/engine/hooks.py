"""Hook entry for Claude Code and Codex: session start, before a tool runs, after a file changes, and turn end.

Exit code 2 stops the tool call (before it runs) or sends the message back to the agent (after it runs).
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from akasha import config, flow, repo
from akasha.coordinator import board
from akasha.core import task as tasks
from akasha.core import workcopy
from akasha.infra import github
from akasha.repo import main_root
from akasha.validators import guard, secrets

SHELL_TOOLS = ("Bash", "PowerShell", "shell")
EDIT_TOOLS = ("Edit", "Write", "MultiEdit", "NotebookEdit", "apply_patch")
_PATCH_FILE = re.compile(r"^\*\*\* (?:Add|Update) File: (.+)$", re.M)
SETUP_HINT = "This repository does not use Akasha yet. To start, use the akasha-setup skill."
BOARD_SECONDS = 10                                     # the session start does not wait longer for the board


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


def session_start(root: Path) -> int:
    notice = f"[AKASHA] Akasha command: {command()} <command>"
    if not (root / config.CONFIG_FILE).is_file():
        print(f"[AKASHA] {SETUP_HINT}\n{notice}")
        return 0
    lines = ["[AKASHA] Do each change as an Akasha task. The akasha-request skill gives the procedure.", notice]
    context = sorted(path.relative_to(root).as_posix() for path in (root / config.TEAM_CONTEXT).glob("*.md"))
    if context:
        lines.append(f"[AKASHA] Read the team context before you write a specification: {', '.join(context)}")
    lines += _task_lines(root)
    lines += _server_notice(root)
    print("\n".join(lines))
    return 0


def _task_lines(root: Path) -> list[str]:
    """The active tasks of this person. With GitHub, the tasks on the board that this person holds or requested.
    Without GitHub, or when gh does not answer, the tasks on this computer."""
    found = [task for task in tasks.all_tasks(root) if tasks.active(task)]
    listed, name = [], ""
    if board.available(root):
        try:
            listed, name = board.read(root, timeout=BOARD_SECONDS)[0], repo.me(root)
        except board.BoardError:
            pass
    if name:
        found = [task for task in listed if tasks.active(task)
                 and name in (task.holder, task.requester.lstrip("@").lower())]
    here = repo.host(root) if name else ""
    return [f"[AKASHA] Task {task.id}: {task.status}, stage {task.stage}, risk {task.risk}"
            f"{_held_by(task, name, here)}, {task.title}" for task in found]


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


def after_tool(cwd: Path, tool: str, tool_input: dict) -> int:
    found = []
    for path in _edited(tool, tool_input, cwd) if tool in EDIT_TOOLS else []:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        found += [f"{path.name}:{line} {kind}" for line, kind in secrets.find(text)]
    if found:
        print("Akasha found a secret key. Remove it and read the key from the environment: " + "; ".join(found),
              file=sys.stderr)
        return 2
    return 0


def turn_end(root: Path) -> int:
    """Tell the user about each task with a work copy on this computer that needs a person: a stopped task, or
    changes outside the task scope. A task that this computer handed off has no work copy here."""
    found = []
    for task in tasks.all_tasks(root):
        if not task.workcopy or not Path(task.workcopy).is_dir():
            continue
        if task.status == "stopped":
            found.append(f"Task {task.id} stopped after failed repairs. A developer must examine it.")
        elif task.status == "open":
            outside = flow.outside_scope(task, workcopy.changed_files(task))
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
    if not (root / config.CONFIG_FILE).is_file():
        return 0
    tool = str(payload.get("tool_name") or "")
    tool_input = payload.get("tool_input") if isinstance(payload.get("tool_input"), dict) else {}
    if event == "PreToolUse":
        return before_tool(root, cwd, tool, tool_input)
    if event == "PostToolUse":
        return after_tool(cwd, tool, tool_input)
    if event == "Stop":
        return turn_end(root)
    return 0
