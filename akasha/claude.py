"""The files that Claude Code reads: the shared settings of the repository, which register the marketplace of Akasha
at the version of the team and turn the plugin on, so that a teammate who opens the repository gets that Akasha after
one install; and the Akasha block of CLAUDE.md, which Claude reads in each session. Other keys and other text stay."""

from __future__ import annotations

import json
from pathlib import Path

from akasha import REPOSITORY, VERSION
from akasha.codex import END, PRECEDENCE, START, with_block
from akasha.guide import ARCHIVE, CORE

SETTINGS = ".claude/settings.json"
INSTRUCTIONS = "CLAUDE.md"
MARKETPLACE, PLUGIN = "akasha", "akasha@akasha"
# Commands that only read, so that a teammate sees no permission prompt for them. The hooks of Akasha already allow
# its own safe commands, and still stop each edit and command that a task must not make.
READ_ONLY = tuple(f"Bash({command}:*)" for command in (
    "git status", "git diff", "git log", "git show", "git grep", "git ls-files", "git rev-parse", "git branch --show-current",
    "git worktree list", "gh pr view", "gh pr diff", "gh pr list", "gh pr checks", "gh run view", "gh run list",
    "gh issue view", "gh issue list"))
MODE = "acceptEdits"            # edits need no prompt: Akasha stops an edit before the approval, and outside the task
RULES = f"""{START}
## Akasha

This repository uses Akasha. Each change is an Akasha task: use the akasha-build skill for each request to add,
change, or repair something, also for a small fix. {PRECEDENCE}

{CORE}

{ARCHIVE}

If the akasha-build skill is
not there, the plugin is missing: stop, and ask the person to run `/plugin marketplace add {REPOSITORY}#v{VERSION}` and
`/plugin install {PLUGIN}`, then to restart.
{END}
"""


def settings_text(text: str | None, wanted: str = VERSION) -> str | None:
    """The settings with the marketplace of Akasha pinned to the version `wanted`, the plugin, the read-only commands,
    and the mode of edits when the team set none, or None when the file is not a JSON object."""
    try:
        data = json.loads(text) if text and text.strip() else {}
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    places = data.setdefault("extraKnownMarketplaces", {})
    plugins = data.setdefault("enabledPlugins", {})
    permissions = data.setdefault("permissions", {})
    if not all(isinstance(item, dict) for item in (places, plugins, permissions)):
        return None
    allow = permissions.setdefault("allow", [])
    if not isinstance(allow, list):
        return None
    places[MARKETPLACE] = {"source": {"source": "github", "repo": REPOSITORY, "ref": f"v{wanted}"}}
    plugins[PLUGIN] = True
    allow += [rule for rule in READ_ONLY if rule not in allow]
    permissions.setdefault("defaultMode", MODE)
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def write(root: Path, wanted: str = VERSION) -> list[str]:
    """Write the Akasha part of each file, at the version `wanted` of the team. Return the files that changed and the
    problems."""
    changed = []
    rules = RULES.replace(f"#v{VERSION}", f"#v{wanted}")
    for name, maker in ((SETTINGS, lambda text: settings_text(text, wanted)),
                        (INSTRUCTIONS, lambda text: with_block(text, rules))):
        path = root / name
        old = path.read_text(encoding="utf-8") if path.is_file() else None
        new = maker(old)
        if new is None:
            changed.append(f"{name} is not a JSON object, so Akasha did not change it")
        elif new != old:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(new, encoding="utf-8")
            changed.append(name)
    return changed
