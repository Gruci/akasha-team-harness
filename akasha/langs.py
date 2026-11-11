"""Language packs: the file extensions and the usual commands of each language, for the first akasha.toml."""

from __future__ import annotations

import fnmatch
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
    manifests: tuple[str, ...] = ()        # the files that tell that a repository uses the language
    rules: tuple[str, ...] = ()            # the files that hold the rules of its lint: an administrator keeps them

    @property
    def patterns(self) -> tuple[str, ...]:
        """The files of the language, as patterns of `only_when`."""
        return tuple(f"**/*{extension}" for extension in self.extensions)


def packs() -> list[Pack]:
    found = []
    for path in sorted(PACKS.glob("*.toml")):
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        found.append(Pack(data["name"], tuple(data["extensions"]), data.get("tests", ""), data.get("lint", ""),
                          data.get("setup", ""), tuple(data.get("ignore", ())),
                          tuple(data.get("manifests", ())), tuple(data.get("rules", ()))))
    return found


def detect(root: Path) -> list[Pack]:
    """The packs whose extensions or manifests occur in the files that git tracks, the most used language
    first. A manifest alone counts: a new repository has its pyproject.toml before its first module."""
    listed = git(root, "ls-files").stdout.splitlines()
    counts = {}
    for pack in packs():
        files = sum(1 for name in listed if Path(name).suffix in pack.extensions)
        named = any(fnmatch.fnmatchcase(Path(name).name, item) for name in listed for item in pack.manifests)
        counts[pack] = files or (0.5 if named else 0)
    return [pack for pack, count in sorted(counts.items(), key=lambda item: -item[1]) if count]


def chosen(root: Path, stack: tuple[str, ...] = ()) -> list[Pack]:
    """The packs of `akasha setup --stack python,typescript`, in that order; without it, what detect finds."""
    if not stack:
        return detect(root)
    known = {pack.name: pack for pack in packs()}
    unknown = [name for name in stack if name not in known]
    if unknown:
        raise ValueError(f"Akasha has no pack for {', '.join(unknown)}. The packs: {', '.join(sorted(known))}")
    return [known[name] for name in stack]
