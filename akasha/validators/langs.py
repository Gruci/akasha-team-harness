"""Language packs: the file extensions and the usual test and lint commands of each language."""

from __future__ import annotations

import subprocess
import tomllib
from dataclasses import dataclass
from pathlib import Path

PACKS = Path(__file__).parent / "packs"


@dataclass(frozen=True)
class Pack:
    name: str
    extensions: tuple[str, ...]
    tests: str
    lint: str
    setup: str          # the usual command that installs the dependencies in a new copy
    ignore: tuple[str, ...] = ()    # the files that tests and builds make, which must not go into a commit


def packs() -> list[Pack]:
    found = []
    for path in sorted(PACKS.glob("*.toml")):
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        found.append(Pack(data["name"], tuple(data["extensions"]), data.get("tests", ""), data.get("lint", ""),
                          data.get("setup", ""), tuple(data.get("ignore", ()))))
    return found


def detect(root: Path) -> list[Pack]:
    """The packs whose extensions occur in the files that git tracks in the repository."""
    listed = subprocess.run(["git", "ls-files"], cwd=root, capture_output=True, text=True, encoding="utf-8")
    suffixes = {Path(name).suffix for name in listed.stdout.splitlines()}
    return [pack for pack in packs() if suffixes.intersection(pack.extensions)]
