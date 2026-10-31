"""The files that Claude Code reads: the shared settings of the repository, which register the marketplace of Akasha
and turn the plugin on, so that a teammate who opens the repository gets Akasha after one install; and the Akasha
block of CLAUDE.md, which Claude reads in each session. Other keys and other text stay."""

from __future__ import annotations

import json
from pathlib import Path

from akasha.codex import END, PRECEDENCE, START, with_block

SETTINGS = ".claude/settings.json"
INSTRUCTIONS = "CLAUDE.md"
MARKETPLACE, REPOSITORY, PLUGIN = "akasha", "Gruci/akasha-team-harness", "akasha@akasha"
RULES = f"""{START}
## Akasha

This repository uses Akasha. Each change is an Akasha task: use the akasha-build skill for each request to add,
change, or repair something, also for a small fix. {PRECEDENCE}

Never merge a pull request yourself, never force a push, and never change .akasha/state.
{END}
"""


def settings_text(text: str | None) -> str | None:
    """The settings with the marketplace and the plugin of Akasha, or None when the file is not a JSON object."""
    try:
        data = json.loads(text) if text and text.strip() else {}
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    places = data.setdefault("extraKnownMarketplaces", {})
    plugins = data.setdefault("enabledPlugins", {})
    if not isinstance(places, dict) or not isinstance(plugins, dict):
        return None
    places[MARKETPLACE] = {"source": {"source": "github", "repo": REPOSITORY}}
    plugins[PLUGIN] = True
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def write(root: Path) -> list[str]:
    """Write the Akasha part of each file. Return the files that changed and the problems."""
    changed = []
    for name, maker in ((SETTINGS, settings_text), (INSTRUCTIONS, lambda text: with_block(text, RULES))):
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
