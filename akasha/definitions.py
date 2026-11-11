"""The definitions of a team: the business values and the features that more than one place uses, each with one
meaning, the code that holds it, the way in from outside, and the test that confirms it.

The list is `akasha.definitions.toml` beside akasha.toml, and `[definitions] on = true` of akasha.toml turns it on.
A team registers a value that several places use (the count of companies, the sum of sales) and a feature that an
area gives to the outside (the login, an export; an address of the server, a public name of the entry of an area).
It does not register a value of one screen only (a row number), or a helper inside an area.

A definition is registered when it is born:

- each value row of a preview names a definition (`data-akasha-definition="<key>"`), or says `local`;
- each new public entry (a name that an entry file of an area newly gives out, a new address of the server) is in the
  `entry` of a definition, or has a row `entry` in "Public changes" of the plan with the reason;
- a new definition has a meaning, an implementation, and a test that are in the code.

Each person adds a definition. Only a task of an administrator changes or removes one, with a row `change` in the
plan. The policy (on or off, who is an administrator) comes from the base branch: a pull request cannot give itself
the right. The list that the checks use is: the definitions of the base, the allowed changes, and the new ones that
passed. A missing or broken file fails where the list is on; a file without an entry is a correct empty list."""

from __future__ import annotations

import fnmatch
import re
import tomllib
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path

from akasha import config
from akasha.codemap import Map
from akasha.config import Team
from akasha.repo import git

FILE = "akasha.definitions.toml"
KEY = re.compile(r"[a-z0-9][a-z0-9_-]*(\.[a-z0-9][a-z0-9_-]*)+")
ADDRESS = re.compile(r"(?:[A-Z]+ )?/\S*")
LOCAL = "local"
_ROW = re.compile(r'<tr\b([^>]*\bdata-akasha-key="([^"]+)"[^>]*)>', re.I)
_NAMED = re.compile(r'\bdata-akasha-definition="([^"]*)"', re.I)
HEAD = '''# The definitions of the team: one meaning for each business value and each feature that more than one place uses.
# Each person adds a block; only a task of an administrator changes or removes one. Keep the blocks in the order of
# their keys, so that two tasks that add at the same time do not meet at the end of the file.
#
# [[definition]]
# key = "corp.active_count"                     # <area>.<what it is>: one key for one meaning
# label = "Active companies"                    # the main word on each screen
# aliases = ["Companies"]                       # other words for the same thing: a button, another language
# meaning = "The companies that are active on the reference day. A company in liquidation does not count"
# area = "domains/corp"                         # the area that keeps this meaning
# implementation = ["domains/corp/queries/count.py::count_active"]      # the code to change
# entry = ["domains/corp/api.py::count_active", "GET /api/corp/count"]  # the way in from outside
# tests = ["tests/contracts/test_corp_count.py"]                        # the test that confirms the meaning
'''


@dataclass(frozen=True)
class Definition:
    key: str
    label: str = ""
    aliases: tuple[str, ...] = ()
    meaning: str = ""
    area: str = ""
    implementation: tuple[str, ...] = ()
    entry: tuple[str, ...] = ()
    tests: tuple[str, ...] = ()

    @property
    def words(self) -> tuple[str, ...]:
        return tuple(word for word in (self.label, *self.aliases) if word)


@dataclass
class Listing:
    """The list that the checks of one change use, and what the change did to it."""
    items: list[Definition] = field(default_factory=list)
    added: list[str] = field(default_factory=list)
    changed: list[str] = field(default_factory=list)          # changed or removed keys
    problems: list[str] = field(default_factory=list)

    def of(self, key: str) -> Definition | None:
        return next((item for item in self.items if item.key == key), None)


def _texts(value: object, where: str) -> tuple[str, ...]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{where} must be a list of text values")
    return tuple(item.strip() for item in value if item.strip())


def parse(text: str) -> list[Definition]:
    """The definitions of a file, in its order. ValueError when the file is no list of definitions."""
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        raise ValueError(f"{FILE}: {error}") from None
    blocks = data.get("definition", [])
    if not isinstance(blocks, list) or set(data) - {"definition"}:
        raise ValueError(f"{FILE} holds only [[definition]] blocks")
    found = []
    for block in blocks:
        if not isinstance(block, dict) or not isinstance(block.get("key"), str):
            raise ValueError(f"{FILE}: each [[definition]] has a key")
        key = block["key"].strip()
        found.append(Definition(key, str(block.get("label") or "").strip(),
                                _texts(block.get("aliases", []), f"{key}: aliases"),
                                str(block.get("meaning") or "").strip(), str(block.get("area") or "").strip("/ "),
                                _texts(block.get("implementation", []), f"{key}: implementation"),
                                _texts(block.get("entry", []), f"{key}: entry"),
                                _texts(block.get("tests", []), f"{key}: tests")))
    return found


def place(root: Path) -> Path:
    """The file of the definitions in a checkout: beside akasha.toml."""
    return config.place(root).parent / FILE


def at(root: Path, commit: str) -> str | None:
    """The text of the definitions in a commit, or None when the commit has no file."""
    for name in config.PLACES:
        folder = name.rsplit("/", 1)[0] + "/" if "/" in name else ""
        shown = git(root, "show", f"{commit}:{folder}{FILE}")
        if shown.returncode == 0:
            return shown.stdout
    return None


def split(where: str) -> tuple[str, str]:
    """`path::name` -> (path, name); a path alone -> (path, "")."""
    path, _, name = where.partition("::")
    return path.strip(), name.strip()


def _new_problems(item: Definition, team: Team, now: Map | None, exists: Callable[[str], bool]) -> list[str]:
    """Why a new definition is not complete, or []."""
    found = []
    if not KEY.fullmatch(item.key):
        found.append(f"{item.key}: a key is <area>.<what it is> in lower case, for example corp.active_count")
    missing = [name for name in ("label", "meaning", "implementation", "tests") if not getattr(item, name)]
    if team.core_areas and not item.area:
        missing.append("area")
    if missing:
        found.append(f"{item.key}: the definition has no {', '.join(missing)}")
    for where in item.implementation + tuple(entry for entry in item.entry if not ADDRESS.fullmatch(entry)):
        path, name = split(where)
        if not exists(path):
            found.append(f"{item.key}: {path} is not in the code")
        elif name and now is not None and path in now.files and not now.files[path].unread and \
                name not in [symbol.name for symbol in now.files[path].symbols] + now.files[path].exports:
            found.append(f"{item.key}: {path} has no public name {name}")
    found += [f"{item.key}: the test {path} is not in the code" for path in item.tests if not exists(path)]
    return found


def listing(team: Team, base_text: str | None, head_text: str | None, admin: bool, table: Iterable[tuple[str, str, str]],
            now: Map | None, exists: Callable[[str], bool], is_task: bool = True,
            was: Callable[[str], bool] = lambda path: True) -> Listing:
    """The list for this change: the definitions of the base, the allowed changes, and the new ones that passed.

    `base_text` and `head_text`: the file before and after the change (None: no file). `admin`: the change is of an
    administrator. `table`: the rows of "Public changes" of the plan. `was`: True for a file that the base had: a
    definition whose code this change moved or removed names its new place in the same change."""
    found = Listing()
    try:
        base = parse(base_text) if base_text is not None else []
    except ValueError:
        base = []                                     # a broken file on the base: an administrator repairs it here
    if head_text is None:
        found.items = base
        found.problems.append(f"{FILE} is gone. The definitions stay on while [definitions] on of akasha.toml is "
                              "true on the default branch: restore the file. Only an administrator turns them off")
        return found
    try:
        head = parse(head_text)
    except ValueError as error:
        found.items = base
        found.problems.append(f"Akasha cannot read the definitions: {error}")
        return found
    keys = [item.key for item in head]
    doubles = sorted({key for key in keys if keys.count(key) > 1})
    if doubles:
        found.problems.append(f"{', '.join(doubles)}: the key is in {FILE} twice. One key, one meaning")
    if keys != sorted(keys):
        found.problems.append(f"the blocks of {FILE} are not in the order of their keys: put each new block at its "
                              "place, so that two tasks that add at the same time do not meet at the end")
    before = {item.key: item for item in base}
    after = {item.key: item for item in head}
    change_rows = {where for change, where, note in table if change == "change" and note}
    for key, item in before.items():
        if after.get(key) == item:
            continue
        found.changed.append(key)
        what = "changes" if key in after else "removes"
        if not admin:
            found.problems.append(f"{key}: the change {what} an existing definition, and only a task of an "
                                  "administrator does that. Add a new definition, or ask an administrator: `akasha "
                                  "help <task> \"<what the definition needs>\"`")
        elif is_task and key not in change_rows:
            found.problems.append(f"{key}: the change {what} an existing definition. Add a row to \"Public changes\" "
                                  f"of plan.md: | change | {key} | <what stays the same for the places that use "
                                  "it> |")
    for key, item in after.items():
        if key in before:
            if before[key] != item:                   # a changed block is complete, as a new one
                found.problems += _new_problems(item, team, now, exists)
            else:                                     # the change took away what the block names
                places = [split(where)[0] for where in item.implementation + item.entry
                          if not ADDRESS.fullmatch(where)] + list(item.tests)
                found.problems += [f"{key}: {path} is not in the code any more. Write its new place into {FILE} "
                                   "in this change (a task of an administrator, with a row `change`)"
                                   for path in dict.fromkeys(places) if not exists(path) and was(path)]
            continue
        found.added.append(key)
        found.problems += _new_problems(item, team, now, exists)
        mine = {word.lower() for word in item.words}
        for other in base:
            same = mine & {word.lower() for word in other.words}
            answered = any(change == "different" and where in (key, other.key) and note for change, where, note in table)
            if same and not answered:
                found.problems.append(f"{key}: the word \"{sorted(same)[0]}\" is the word of the definition "
                                      f"{other.key} already. Use that definition, or add a row to \"Public changes\" "
                                      f"of plan.md: | different | {key} | <the difference of meaning> |")
    found.items = head
    return found


def _fits(entry: str, method: str, address: str) -> bool:
    """True when an entry of a definition names this address: `GET /api/x`, `/api/x`, or a pattern `/api/funds/*`."""
    wanted_method, _, wanted = entry.rpartition(" ")
    return (not wanted_method or wanted_method == method) and fnmatch.fnmatchcase(address, wanted)


def entry_problems(found: Listing, before: Map, now: Map, public: tuple[str, ...],
                   table: Iterable[tuple[str, str, str]], matches: Callable[[str, str], bool]) -> list[str]:
    """The new public entries of the change that no definition holds and no row `entry` of the plan answers: a new
    address of the server, and a name that an entry file of an area (`public`, the patterns of the boundaries) newly
    gives out. A row answers one entry only, and names it exactly."""
    rows = {where for change, where, note in table if change == "entry" and note}
    entries = [entry for item in found.items for entry in item.entry]
    old_routes = {(method, address) for held in before.files.values() for method, address, _h, _l in held.routes}
    problems = []
    for path, held in sorted(now.files.items()):
        for method, address, _handler, line in held.routes:
            if (method, address) in old_routes or f"{method} {address}" in rows:
                continue
            if not any(ADDRESS.fullmatch(entry) and _fits(entry, method, address) for entry in entries):
                problems.append(f"{path}:{line} {method} {address} — a new address of the server that no definition "
                                f"holds. Put it into the entry of its definition in {FILE}, or add a row to "
                                f"\"Public changes\" of plan.md: | entry | {method} {address} | <why it has no "
                                "business meaning> |")
        if not any(matches(path, item) for item in public):
            continue
        if held.unread:
            continue                                  # boundaries.unread_entries names it
        was = before.files.get(path)
        old = {symbol.name for symbol in was.symbols} | set(was.exports) if was else set()
        lines = {symbol.name: symbol.line for symbol in held.symbols}
        for name in dict.fromkeys([symbol.name for symbol in held.symbols] + held.exports):
            where = f"{path}::{name}"
            if name not in old and where not in entries and where not in rows:
                problems.append(f"{path}:{lines.get(name, 1)} {name} — a new public name of an entry file that no "
                                f"definition holds. Put {where} into the entry of its definition in {FILE}, or add "
                                f"a row to \"Public changes\" of plan.md: | entry | {where} | <why it has no business "
                                "meaning> |")
    return problems


def change_problems(found: Listing, changed: Iterable[str], table: Iterable[tuple[str, str, str]]) -> list[str]:
    """The registered implementation files that the change edits without a row `change` in the plan."""
    rows = {split(where)[0] for change, where, note in table if change == "change" and note} | \
        {where for change, where, note in table if change == "change" and note}
    problems = []
    for path in sorted(set(changed)):
        held = [item for item in found.items if item.key not in found.added
                and any(split(where)[0] == path for where in item.implementation)]
        if held and path not in rows and not any(item.key in rows for item in held):
            item = held[0]
            problems.append(f"{path} holds the definition {item.key} ({item.label}), which {', '.join(item.entry) or 'other code'} "
                            f"gives out. Add a row to \"Public changes\" of plan.md: | change | {path} | <what "
                            "stays the same for the places that use it> |")
    return problems


def preview_problems(text: str, keys: Iterable[str]) -> list[str]:
    """The value rows of a preview that name no definition: each row has data-akasha-definition="<key>" of a
    definition of the list, or "local" for a value of this screen only."""
    from akasha import spec
    known, problems = set(keys), []
    for attributes, key in _ROW.findall(spec.plain(text)):
        named = _NAMED.search(attributes)
        if not named or not named.group(1).strip():
            problems.append(f'{key}: the value row names no definition. Add data-akasha-definition="<key of '
                            f'{FILE}>" to the row, or "local" for a value of this screen only')
        elif named.group(1).strip() != LOCAL and named.group(1).strip() not in known:
            problems.append(f"{key}: {named.group(1).strip()} is no key of {FILE}. Use a key of the list, add the "
                            'definition in this task, or write "local" for a value of this screen only')
    return problems


def touching(items: Iterable[Definition], scope: Iterable[str], title: str,
             matches: Callable[[str, str], bool]) -> list[Definition]:
    """The definitions that a task touches: a planned file is their code, or the title holds their word."""
    scope, low = list(scope), title.lower()
    return [item for item in items
            if any(word.lower() in low for word in item.words)
            or any(matches(split(where)[0], pattern) for where in item.implementation + item.entry
                   if not ADDRESS.fullmatch(where) for pattern in scope)]


def line_of(item: Definition) -> str:
    return (f"{item.key} \"{item.label}\": {item.meaning} · code {', '.join(item.implementation) or '—'}"
            + (f" · entry {', '.join(item.entry)}" if item.entry else "")
            + (f" · tests {', '.join(item.tests)}" if item.tests else ""))
