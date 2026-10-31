"""Language packs: the file extensions and the usual commands of each language, for the first akasha.toml."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from akasha.repo import git

PACKS = Path(__file__).parent / "packs"


@dataclass(frozen=True)
class Pack:
    name: str
    extensions: tuple[str, ...]
    tests: str
    lint: str
    setup: str
    ignore: tuple[str, ...] = ()


def packs() -> list[Pack]:
    found = []
    for path in sorted(PACKS.glob("*.toml")):
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        found.append(Pack(data["name"], tuple(data["extensions"]), data.get("tests", ""), data.get("lint", ""),
                          data.get("setup", ""), tuple(data.get("ignore", ()))))
    return found


def detect(root: Path) -> list[Pack]:
    """The packs whose extensions occur in the files that git tracks, the most used language first."""
    listed = git(root, "ls-files").stdout.splitlines()
    counts = {pack: sum(1 for name in listed if Path(name).suffix in pack.extensions) for pack in packs()}
    return [pack for pack, count in sorted(counts.items(), key=lambda item: -item[1]) if count]
