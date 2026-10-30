"""Write the files that Codex reads, so that a Codex session obeys the same procedure and checks."""

from __future__ import annotations

import json
from pathlib import Path

START, END = "<!-- akasha:start -->", "<!-- akasha:end -->"
RULES = f"""{START}
## Akasha

This repository uses Akasha. Do each change as an Akasha task. The Akasha command is `python -m akasha`.
Ask people only what to make, how it looks, and how they use it. Make the technical decisions yourself and record them.

1. Record the task: `python -m akasha request "<title>" --requester <GitHub name> --feature <feature key>`.
   If an earlier task makes the same feature, add `--builds-on <earlier task>`.
2. Ask the requester questions until the completion conditions are clear. Record each condition:
   `python -m akasha specify <task> --condition "<condition>"`.
3. Read `.akasha/context/product-map.md`. Find the files, data, and APIs that the change touches.
   Record the scope: `python -m akasha specify <task> --scope <file patterns>`.
4. Record the impact analysis: `python -m akasha impact <task> --features "<text>" --data "<text>"
   --contracts "<text>" --tasks "<text>" --rollback "<text>"`.
5. Tell the requester the specification in simple words. Record the approval:
   `python -m akasha approve <task> --role requester --by <name>`.
6. Make the change only in the work copy of the task. Write an automated test for each completion condition.
7. Run `python -m akasha check <task>`. Repair each failure.
8. Show the result to the requester. Record each answer:
   `python -m akasha accept <task> --condition "<condition>" --result yes`.
9. Update the product map in the work copy, or record why it does not change:
   `python -m akasha impact <task> --map-unchanged "<reason>"`.
10. Write the briefing with the sections Why, What changed, Scope, Tradeoffs, and Blast Radius. Record it:
    `python -m akasha brief <task> --file <path>`. Then run `python -m akasha handover <task>`.

After each step, run `python -m akasha advance <task>`. If Akasha shows a blocker, do the step that removes it.

Never record an approval or an answer for a person who did not give it.
After three failed repairs, Akasha stops the task. Stop the work and tell a developer.
With GitHub, one person on one computer holds each task. If Akasha says that another person holds it, do not change it.
To let another person continue a task, run `python -m akasha handoff <task>` in the main checkout.
To continue a task that another person handed off, run `python -m akasha takeover <task>`.
Do not use a command that you cannot undo, for example a force push.
{END}
"""


def _hook(event: str, matcher: str | None) -> dict:
    arguments = f"-X utf8 -m akasha hook --agent codex --event {event}"
    # The file is shared in git, so it names no path of one computer. macOS and Linux have python3; Windows has python.
    entry = {"hooks": [{"type": "command", "command": f"python3 {arguments}", "commandWindows": f"python {arguments}",
                        "timeout": 120}]}
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
