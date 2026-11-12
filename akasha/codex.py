"""The files that Codex reads: the Akasha block of AGENTS.md, and the hooks of Akasha in .codex/hooks.json. Akasha
changes only its own part of each file: the other text and the other hooks of the team stay."""

from __future__ import annotations

import json
from pathlib import Path

from akasha import SOURCE, VERSION, source
from akasha.guide import ARCHIVE, CORE

FILES = ("AGENTS.md", ".codex/hooks.json")
START, END = "<!-- akasha:start -->", "<!-- akasha:end -->"
HOOK_MARK = "-m akasha hook"
BOM = chr(0xFEFF)                                   # a byte order mark at the start of a file
EVENTS = (("SessionStart", None), ("UserPromptSubmit", None), ("PreToolUse", "Bash|apply_patch|Edit|Write"),
          ("PostToolUse", "Edit|Write|apply_patch"), ("SubagentStop", None))
PRECEDENCE = ("In this repository this procedure replaces every other procedure for a change, in this file, in the "
              "skills, and in other documents: scope interviews, a plan approval by a person, research and plan files "
              "outside the records folder of the task, making worktrees, task board files, pushes, pull requests, and "
              "merges. The person approves only the preview, another AI reviews the plan, and `akasha land` merges. "
              "Keep the records of a task where Akasha puts them: never move, rename, or archive them. Only the "
              "people of [team] own_procedure in akasha.toml keep the own procedure of the repository.")
RULES = f"""{START}
## Akasha

This repository uses Akasha. Each change is an Akasha task. The command is `py -3 -X utf8 -m akasha` on Windows and
`python3 -m akasha` elsewhere; this text writes it as `akasha`. Install it into that Python with
`pip install "{SOURCE}"`. The session start notice tells the tasks of this person and the open tasks of the team.
{PRECEDENCE}

The core:

{CORE}

The steps of a task with a preview. `akasha status <task> --brief` names the next one at each moment, with how far
the build is and what stops it: follow it, not this list.

1. Ask the person only what changes the result and what you cannot decide from the code, the data, and the guides of
   the team: at most three questions. Decide the rest, and propose it in the preview. Run
   `akasha start "<title>" --scope <file patterns>`.
2. Fill the form of the preview that `akasha start` wrote in the records folder, and delete its first line: the
   decisions, the look, each value from data with its source, formula, value now, and check, and each rule with an
   example. The form tells how. Run `akasha preview <task>` and ask the person whether to build it like this, or what
   to change. When their own message approves it, in any language and without asking for a change, run
   `akasha approve <task>`: it records the words of the person that the hook kept. Never approve for the person.
3. After the approval, do the rest without asking. Fill the form plan.md that `akasha approve` wrote: the approach,
   and the work as steps, each with its files, the rules of the preview that it builds, and its tests. Then a
   separate reviewer reviews the plan. With a reviewer command of the team, run `akasha review <task>`. With a
   reviewer agent, it judges each item of agents/akasha-reviewer.md in the plugin, one row each
   (`| R1 | PASS | <evidence> |`), and ends with `AKASHA-REVIEW: <task> <digest> PASS` or `CHANGES`
   (`akasha status <task>` shows the digest). Without both, review the plan yourself and run
   `akasha review <task> --verdict pass`: the pull request tells that it was a self-review.
4. Build the steps of the plan in the work copy of the task. Write a test for each rule and each value of the
   preview, with the example of the preview as its expected value and the mark `akasha: rule=<key>` in a comment.
   Run `akasha check <task>` and repair each failure as its message tells: it examines the proof of the rules, the
   steps of the plan, the map of the product, the rules of operation, and the sizes.
5. The reviewer reviews the result, the change itself, in the same way as the plan (`akasha review <task>` runs the
   review that the task needs now). Repair what it finds, and check again.
6. Write summary.md (why, what changed, how to undo it when a revert is not enough), run the check again, then
   `akasha land <task> --wait 540` with a shell timeout of 10 minutes. Run it again while it says WAITING or
   DEPLOYING. Repair a FAILED or a CONFLICT, and do what a BLOCKED says. When a BLOCKED says that an administrator
   approves a change of the structure first, Akasha already asked the administrators: tell the person in one simple
   sentence, and land again later. Only an administrator changes akasha.toml, `.github/`, and the paths of [risk]:
   when the task needs them, run `akasha help <task> "<what it needs>"`.
7. Tell the person the result in simple words: MERGED, or DEPLOYED when the team deploys each merge. VERIFY_FAILED
   means the change is live, but the check of the team after the deployment failed: tell the person in simple words,
   run `akasha help <task> "<the check after the deployment failed>"`, and offer to undo the change with a new task.

{ARCHIVE}

A long task fills the conversation. `akasha status <task> --brief` shows the task on one screen, and names a safe
point where a new session loses nothing: that session runs `akasha status <task> --resume` first. Without a hook
for the words of the person, the person approves in their own terminal: `akasha approve <task> --here`.

Never merge a pull request yourself, never force a push, and never change .docs/state. When a check fails again
and again and you cannot repair it, tell the person in simple words what blocks the task. An administrator takes only
what is theirs: a file that only they change, and a check or a deployment that is broken for each task
(`akasha help <task> "<what it needs>"`).
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
    """The text of an instruction file with the Akasha block `rules` in place of the old one, or at its end. Not at its
    top: a repository can require that each document opens with its own heading or summary. The session start and the
    prompt hook tell the precedence again."""
    text = text or ""
    if START in text and END in text:
        text = text[:text.index(START)] + rules.strip() + text[text.index(END) + len(END):]
    else:
        text = (text.rstrip() + "\n\n" if text.strip() else "") + rules
    return text.rstrip() + "\n"


def agents_text(text: str | None, wanted: str = VERSION) -> str:
    """AGENTS.md with the Akasha block, whose pip line installs the version `wanted` of the team."""
    return with_block(text, RULES.replace(SOURCE, source(wanted)))


def write(root: Path, wanted: str = VERSION) -> list[str]:
    """Write the Akasha part of each file, at the version `wanted` of the team. Return the files that changed and the
    problems."""
    changed = []
    for name, maker in (("AGENTS.md", lambda text: agents_text(text, wanted)), (".codex/hooks.json", hooks_text)):
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
