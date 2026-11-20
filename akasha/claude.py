"""The files that Claude Code reads: the marketplace file of the team, which fixes the plugin of Akasha to the release
tag of the version of the team; the shared settings of the repository, which turn the plugin on; and the Akasha block
of CLAUDE.md, which Claude reads in each session. Other keys and other text stay.

Each computer registers the folder of the marketplace file once (`claude plugin marketplace add`). Claude Code reads
the file where it is: after a pull, `/plugin update akasha@akasha` takes the version that the file names, newer or
older, and without a change of the file nothing moves."""

from __future__ import annotations

import json
from pathlib import Path

from akasha import REPOSITORY, VERSION
from akasha.codex import END, PRECEDENCE, START, with_block
from akasha.guide import ARCHIVE, CORE

SETTINGS = ".claude/settings.json"
MARKET = ".github/akasha"                        # the marketplace of the team: only an administrator changes .github/
MARKET_FILE = f"{MARKET}/.claude-plugin/marketplace.json"
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
not there, the plugin is missing: stop, and ask the person to run `claude plugin marketplace add ./{MARKET}` in the
top folder of this repository and `claude plugin install {PLUGIN}`, then to restart.
{END}
"""


def market_text(wanted: str = VERSION) -> str:
    """The marketplace file of the team: it fixes the plugin of Akasha to the release tag of the version `wanted`. The
    source is an https address: at an update, Claude Code clones a `github` source over SSH, which fails without a
    key."""
    plugin = {"name": MARKETPLACE, "version": wanted,
              "description": "The Akasha of the team, at the version of [team] version in akasha.toml",
              "source": {"source": "url", "url": f"https://github.com/{REPOSITORY}.git", "ref": f"v{wanted}"}}
    return json.dumps({"name": MARKETPLACE, "owner": {"name": "Akasha"}, "plugins": [plugin]}, indent=2) + "\n"


def settings_text(text: str | None) -> str | None:
    """The settings with the plugin, the read-only commands, and the mode of edits when the team set none, or None
    when the file is not a JSON object. They name no marketplace of Akasha: an older Akasha wrote the public
    repository at a tag here, and that entry would stand against the folder that each computer registers."""
    try:
        data = json.loads(text) if text and text.strip() else {}
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    places = data.get("extraKnownMarketplaces", {})
    plugins = data.setdefault("enabledPlugins", {})
    permissions = data.setdefault("permissions", {})
    if not all(isinstance(item, dict) for item in (places, plugins, permissions)):
        return None
    allow = permissions.setdefault("allow", [])
    if not isinstance(allow, list):
        return None
    places.pop(MARKETPLACE, None)
    if not places:
        data.pop("extraKnownMarketplaces", None)
    plugins[PLUGIN] = True
    allow += [rule for rule in READ_ONLY if rule not in allow]
    permissions.setdefault("defaultMode", MODE)
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def write(root: Path, wanted: str = VERSION) -> list[str]:
    """Write the Akasha part of each file, at the version `wanted` of the team: only the marketplace file names it.
    Return the files that changed and the problems."""
    changed = []
    for name, maker in ((MARKET_FILE, lambda text: market_text(wanted)), (SETTINGS, settings_text),
                        (INSTRUCTIONS, lambda text: with_block(text, RULES))):
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
