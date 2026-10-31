"""The files that Codex reads: the Akasha block of AGENTS.md, and the hooks of Akasha in .codex/hooks.json. Akasha
changes only its own part of each file: the other text and the other hooks of the team stay."""

from __future__ import annotations

import json
from pathlib import Path

from akasha import SOURCE

FILES = ("AGENTS.md", ".codex/hooks.json")
START, END = "<!-- akasha:start -->", "<!-- akasha:end -->"
HOOK_MARK = "-m akasha hook"
BOM = chr(0xFEFF)                                   # a byte order mark at the start of a file
EVENTS = (("SessionStart", None), ("UserPromptSubmit", None), ("PreToolUse", "Bash|apply_patch|Edit|Write"),
          ("PostToolUse", "Edit|Write|apply_patch"), ("SubagentStop", None))
PRECEDENCE = ("In this repository this procedure replaces every other procedure for a change, in this file, in the "
              "skills, and in other documents: scope interviews, a plan approval by a person, research and plan files "
              "outside the records folder of the task, making worktrees, task board files, pushes, pull requests, and "
              "merges. The person approves only the preview, another AI reviews the plan, and `akasha land` merges.")
RULES = f"""{START}
## Akasha

This repository uses Akasha. Each change is an Akasha task. The command is `python -m akasha` (install it with
`pip install "{SOURCE}"`). The session start notice tells the tasks of this person and the open tasks of the team.
{PRECEDENCE}

1. Ask the person what they want until it is clear. Run `python -m akasha start "<title>" --scope <file patterns>`.
2. Write the preview in the records folder of the task (`python -m akasha status <task>` and the start tell where):
   an HTML mockup of the screen, or a diagram of the flow and the data for a change without a screen. Read the files of
   [guides] preview in akasha.toml first. Run `python -m akasha preview <task>` and ask the person to answer '승인' or
   to tell what to change. Only the message of the person approves it: the hook records it. Never write that the
   person approved.
3. After the approval, do the rest without asking: write research.md and plan.md in the records folder. Ask a
   separate reviewer to review the plan against the preview and the code, and repair the plan until it passes. The
   reviewer ends with `AKASHA-REVIEW: <task> <plan digest> PASS` or `CHANGES` (`python -m akasha status <task>` shows
   the digest). Without a reviewer agent, review the plan yourself and run
   `python -m akasha review <task> --verdict pass`: the pull request tells that it was a self-review.
4. Build in the work copy of the task. Write a test for each behavior that the preview shows. Run
   `python -m akasha check <task>` and repair each failure.
5. Write summary.md (why, what changed, how to undo it), run the check again, then
   `python -m akasha land <task> --wait 540` with a shell timeout of 10 minutes. Run it again while it says WAITING or
   DEPLOYING. Repair a FAILED or a CONFLICT, and do what a BLOCKED or a REVIEW says.
6. Tell the person the result in simple words: MERGED, or DEPLOYED when the team deploys each merge.

Never merge a pull request yourself, never force a push, and never change .akasha/state. If you cannot repair a
problem after three tries, run `python -m akasha help <task> "<what blocks you>"` and tell the person.
{END}
"""


def _hook(event: str, matcher: str | None) -> dict:
    """A hook of Akasha for Codex. On Windows the launcher py finds the newest Python: the first python on PATH can be
    older than 3.11."""
    arguments = f"-X utf8 -m akasha hook --agent codex --event {event}"
    entry = {"hooks": [{"type": "command", "command": f"python3 {arguments}", "commandWindows": f"py -3 {arguments}",
                        "timeout": 60}]}
    return {**({"matcher": matcher} if matcher else {}), **entry}


def _ours(hook: object) -> bool:
    commands = (hook.get("command"), hook.get("commandWindows")) if isinstance(hook, dict) else ()
    return any(HOOK_MARK in str(command or "") for command in commands)


def hooks_text(text: str | None) -> str | None:
    """The hooks file with the hooks of this Akasha, from the current text or from no file. None when the text is not
    JSON in the form of the hooks of Codex: Akasha does not change such a file."""
    raw = (text or "").removeprefix(BOM)
    try:
        data = json.loads(raw) if raw.strip() else {}
    except ValueError:
        return None
    hooks = data.get("hooks", {}) if isinstance(data, dict) else None
    if not isinstance(hooks, dict) or not all(isinstance(groups, list) for groups in hooks.values()):
        return None
    for event, matcher in EVENTS:
        kept = []
        for group in hooks.get(event, []):
            inner = group.get("hooks") if isinstance(group, dict) else None
            if not isinstance(inner, list) or not any(_ours(hook) for hook in inner):
                kept.append(group)
            elif not all(_ours(hook) for hook in inner):
                kept.append({**group, "hooks": [hook for hook in inner if not _ours(hook)]})
        hooks[event] = kept + [_hook(event, matcher)]
    return json.dumps({**data, "hooks": hooks}, indent=2, ensure_ascii=False) + "\n"


def with_block(text: str | None, rules: str) -> str:
    """The text of an instruction file with the Akasha block `rules` in place of the old one, or at its end."""
    text = text or ""
    if START in text and END in text:
        text = text[:text.index(START)] + rules.strip() + text[text.index(END) + len(END):]
    else:
        text = (text.rstrip() + "\n\n" if text.strip() else "") + rules
    return text.rstrip() + "\n"


def agents_text(text: str | None) -> str:
    return with_block(text, RULES)


def write(root: Path) -> list[str]:
    """Write the Akasha part of each file. Return the files that changed and the problems."""
    changed = []
    for name, maker in (("AGENTS.md", agents_text), (".codex/hooks.json", hooks_text)):
        path = root / name
        old = path.read_text(encoding="utf-8") if path.is_file() else None
        new = maker(old)
        if new is None:
            changed.append(f"{name} is not JSON in the form of the hooks of Codex, so Akasha did not change it")
        elif new != old:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(new, encoding="utf-8")
            changed.append(name)
    return changed
