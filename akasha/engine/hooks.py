"""Hook entry for Claude Code and Codex: session start, before a tool runs, after a file changes, and turn end.

Exit code 2 stops the tool call (before it runs) or sends the message back to the agent (after it runs).
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from akasha import config
from akasha.core import task as tasks
from akasha.repo import main_root
from akasha.validators import guard, secrets

SHELL_TOOLS = ("Bash", "PowerShell", "shell")
EDIT_TOOLS = ("Edit", "Write", "MultiEdit", "NotebookEdit", "apply_patch")
_PATCH_FILE = re.compile(r"^\*\*\* (?:Add|Update) File: (.+)$", re.M)
SETUP_HINT = "Akasha is installed, but this repository has no akasha.toml. When the user asks, say: Set up Akasha."


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
    """How to run Akasha here: the plugin launcher when it exists, else the installed package."""
    launcher = Path(__file__).resolve().parents[2] / "akasha_run.py"
    return f'python -X utf8 "{launcher.as_posix()}"' if launcher.is_file() else "python -X utf8 -m akasha"


def session_start(root: Path) -> int:
    open_tasks = [task for task in tasks.all_tasks(root) if task.status == "open"]
    lines = ["[AKASHA] Do each change as an Akasha task. The akasha-request skill gives the procedure.",
             f"[AKASHA] Akasha command: {command()} <command>"]
    lines += [f"[AKASHA] Open task {task.id}: stage {task.stage}, risk {task.risk}, {task.title}" for task in open_tasks]
    print("\n".join(lines))
    return 0


def before_tool(root: Path, cwd: Path, tool: str, tool_input: dict) -> int:
    if tool in SHELL_TOOLS:
        reason = guard.check_command(str(tool_input.get("command") or ""), cwd, root)
    elif tool in EDIT_TOOLS:
        open_tasks = tasks.all_tasks(root)
        reasons = [guard.check_edit(path, root, open_tasks) for path in _edited(tool, tool_input, cwd)]
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
    stopped = [task for task in tasks.all_tasks(root) if task.status == "stopped"]
    if stopped:
        print(json.dumps({"systemMessage": f"[AKASHA] Task {stopped[0].id} stopped after failed repairs. "
                                           "A developer must examine it."}))
    return 0


def main(agent: str, event: str) -> int:
    payload = _payload()
    cwd = Path(str(payload.get("cwd") or Path.cwd()))
    root = main_root(cwd)
    if root is None:
        return 0
    if not (root / config.CONFIG_FILE).is_file():
        if event == "SessionStart":
            print(f"[AKASHA] {SETUP_HINT}")
        return 0
    tool = str(payload.get("tool_name") or "")
    tool_input = payload.get("tool_input") if isinstance(payload.get("tool_input"), dict) else {}
    if event == "SessionStart":
        return session_start(root)
    if event == "PreToolUse":
        return before_tool(root, cwd, tool, tool_input)
    if event == "PostToolUse":
        return after_tool(cwd, tool, tool_input)
    if event == "Stop":
        return turn_end(root)
    return 0
