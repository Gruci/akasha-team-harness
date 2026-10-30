"""Write the files that Codex reads, so that a Codex session obeys the same procedure and checks."""

from __future__ import annotations

import json
from pathlib import Path

START, END = "<!-- akasha:start -->", "<!-- akasha:end -->"
RULES = f"""{START}
## Akasha

This repository uses Akasha. Do each change as an Akasha task.

1. Record the task: `python -m akasha request "<title>" --requester <name>`.
2. Ask the requester questions until the completion conditions are clear. Record them with `python -m akasha specify`.
3. Make the change only in the work copy of the task.
4. Run `python -m akasha check <task>`. Repair each failure.
5. Show the result to the requester. Record the answer with `python -m akasha accept`.
6. Open the pull request with `python -m akasha handover <task>`.

Do not use a command that you cannot undo, for example a force push.
{END}
"""


def _hook(event: str, matcher: str | None) -> dict:
    command = f"python -X utf8 -m akasha hook --agent codex --event {event}"
    entry = {"hooks": [{"type": "command", "command": command, "commandWindows": command, "timeout": 120}]}
    return {**({"matcher": matcher} if matcher else {}), **entry}


def write(root: Path) -> list[str]:
    """Put the Akasha rules into AGENTS.md and the hooks into .codex/hooks.json. Keep the other text."""
    agents = root / "AGENTS.md"
    text = agents.read_text(encoding="utf-8") if agents.is_file() else ""
    if START in text and END in text:
        text = text[:text.index(START)] + RULES.strip() + text[text.index(END) + len(END):]
    else:
        text = (text.rstrip() + "\n\n" if text.strip() else "") + RULES
    agents.write_text(text.rstrip() + "\n", encoding="utf-8")
    hooks = root / ".codex" / "hooks.json"
    hooks.parent.mkdir(exist_ok=True)
    hooks.write_text(json.dumps({"hooks": {
        "PreToolUse": [_hook("PreToolUse", "Bash|apply_patch|Edit|Write")],
        "PostToolUse": [_hook("PostToolUse", "Edit|Write|apply_patch")],
        "Stop": [_hook("Stop", None)],
    }}, indent=2) + "\n", encoding="utf-8")
    return ["AGENTS.md", ".codex/hooks.json"]
