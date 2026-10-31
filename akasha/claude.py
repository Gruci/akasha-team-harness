"""The shared Claude Code settings of the repository: they register the marketplace of Akasha and turn the plugin on,
so that a teammate who opens the repository gets Akasha after one install. Other keys stay."""

from __future__ import annotations

import json
from pathlib import Path

SETTINGS = ".claude/settings.json"
MARKETPLACE, REPOSITORY, PLUGIN = "akasha", "Gruci/akasha-team-harness", "akasha@akasha"


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
    path = root / SETTINGS
    old = path.read_text(encoding="utf-8") if path.is_file() else None
    new = settings_text(old)
    if new is None:
        return [f"{SETTINGS} is not a JSON object, so Akasha did not change it"]
    if new == old:
        return []
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(new, encoding="utf-8")
    return [SETTINGS]
