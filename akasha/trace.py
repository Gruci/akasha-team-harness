"""A record of what stopped the work on this computer: failed checks, stopped commands, and plan reviews that asked
for changes. The retro reads it with the records of the merged pull requests, so that a repeated problem becomes a
new check of the team."""

from __future__ import annotations

import json
import time
from pathlib import Path

from akasha.config import STATE_DIR

TRACE = STATE_DIR / "trace.jsonl"


def note(root: Path, kind: str, **data: object) -> None:
    """Add one line. A failure to write never stops the work."""
    try:
        path = root / TRACE
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as file:
            file.write(json.dumps({"at": time.strftime("%Y-%m-%d %H:%M:%S"), "kind": kind, **data},
                                  ensure_ascii=False) + "\n")
    except OSError:
        pass


def read(root: Path) -> list[dict]:
    try:
        lines = (root / TRACE).read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    found = []
    for line in lines:
        try:
            item = json.loads(line)
        except ValueError:
            continue
        if isinstance(item, dict):
            found.append(item)
    return found
