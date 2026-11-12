"""The consistency check: new code that the repository has already, under the same name or with the same body.

`akasha check` and the server check run the same function. It looks only at what this change makes new. A new
public name with a grounded candidate (an existing name that it may copy) needs an answer: use the existing code, or
one row in the table "Public changes" of plan.md that tells why the new one is there. The reviewer judges the reason
(R10); the machine sees only that the row is there.

A grounded candidate, for a new public name N and a name E that was there before the change:

- G1, the same body: Python only. The bodies of N and E have the same digest, and three statements or more.
- G2, the same area: E is in another file of the same area, with the same name.
- G3, shared code: E is in a file that other areas use (core.reason), with the same name.

Python and JavaScript/TypeScript are never candidates of each other. A name that this change removed elsewhere with
the same body is a move, not a candidate. One case is only a note: a pair of G3 where the name is in three areas or
more at the same place (the same file name or folder name) and N is at that place too, such as the `api.py::boot` of
each domain.

All else is advice (`note —`), and never stops a task: the same name in another area, a new public function of shared
code without a description, and what the name of a new function tells against the nearby code (7-5)."""

from __future__ import annotations

import posixpath
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from akasha import boundaries, codemap, core, definitions, pins
from akasha.checks import matches
from akasha.codemap import Map, Symbol
from akasha.config import Team
from akasha.repo import git, names, paths, paths_at

CHECK = "consistency"
ANSWERS = ("different", "wraps", "replaces")
TABLE = re.compile(r"^#{1,6}[ \t]*Public changes[ \t]*$", re.I | re.M)
ROW = re.compile(r"^\s*\|\s*([A-Za-z]+)\s*\|\s*([^|\n]+?)\s*\|\s*([^|\n]*?)\s*\|\s*$", re.M)
SHOWN = 8                      # the candidates and the notes that the output names
TRUE_OR_FALSE = ("is", "has", "can", "should")


@dataclass
class Candidate:
    path: str                  # of the new name
    new: Symbol
    other: str                 # the file of the existing name
    old: Symbol
    ground: str                # G1, G2, or G3

    @property
    def why(self) -> str:
        return {"G1": "the same body is", "G2": "the same name is in this area:",
                "G3": "the same name is in code that other areas use:"}[self.ground]


def _family(path: str) -> str:
    """The language family of a file: a name of one family is no candidate of a name of another."""
    if path.endswith(core.PY):
        return "python"
    return "script" if path.endswith(core.JS) else posixpath.splitext(path)[1]


def rows(plan: str) -> list[tuple[str, str, str]]:
    """The rows of the table "Public changes" of a plan: (change, where, note)."""
    found = TABLE.search(plan or "")
    if not found:
        return []
    table = plan[found.end():]
    end = re.search(r"^#{1,6}[ \t]", table, re.M)
    return [(change.lower(), where.strip("` "), note.strip()) for change, where, note in
            ROW.findall(table[:end.start()] if end else table) if where.strip().lower() != "where"]


def answered(candidate: Candidate, table: Iterable[tuple[str, str, str]]) -> bool:
    """True when a row names the new name or the existing one and gives a reason."""
    wanted = {f"{candidate.path}::{candidate.new.name}", f"{candidate.other}::{candidate.old.name}"}
    return any(change in ANSWERS and where in wanted and note for change, where, note in table)


def _place(path: str) -> tuple[str, str]:
    return posixpath.basename(path), posixpath.basename(posixpath.dirname(path))


def _usual_place(before: Map, name: str, path: str) -> bool:
    """True when the name is in three areas or more at the same place as `path`: the same file name, or the same
    folder name."""
    file, folder = _place(path)
    areas_by_file, areas_by_folder = set(), set()
    for other, held in before.files.items():
        if any(symbol.name == name for symbol in held.symbols):
            if _place(other)[0] == file:
                areas_by_file.add(before.area(other))
            if _place(other)[1] == folder:
                areas_by_folder.add(before.area(other))
    return len(areas_by_file) >= 3 or len(areas_by_folder) >= 3


def compare(team: Team, before: Map, now: Map, changed: list[str],
            registered: frozenset = frozenset()) -> tuple[list[Candidate], list[str]]:
    """The grounded candidates of the new public names, and the notes. `registered`: the (path, name) pairs that
    hold a definition of the team: the same name as one of them is a candidate (G3), as for shared code."""
    old_names = {(path, symbol.name) for path, held in before.files.items() for symbol in held.symbols}
    new = [(path, symbol) for path in changed if path in now.files for symbol in now.files[path].symbols
           if (path, symbol.name) not in old_names]
    if not new:
        return [], []
    still = {(path, symbol.name) for path, held in now.files.items() for symbol in held.symbols}
    gone = [(path, symbol) for path, held in before.files.items() for symbol in held.symbols
            if (path, symbol.name) not in still]
    existing = [(path, symbol) for path, held in before.files.items() for symbol in held.symbols
                if (path, symbol.name) in still]
    by_name: dict[str, list[tuple[str, Symbol]]] = {}
    by_body: dict[str, list[tuple[str, Symbol]]] = {}
    for path, symbol in existing:
        by_name.setdefault(symbol.name, []).append((path, symbol))
        if symbol.digest and symbol.size >= 3:
            by_body.setdefault(symbol.digest, []).append((path, symbol))
    found, notes = [], []
    for path, symbol in new:
        family = _family(path)
        moved = any(other.name == symbol.name and _family(where) == family and
                    (other.digest == symbol.digest if family == "python" else other.signature == symbol.signature)
                    for where, other in gone)
        if moved:
            continue
        pairs = []
        if family == "python" and symbol.digest and symbol.size >= 3:
            pairs += [(where, other, "G1") for where, other in by_body.get(symbol.digest, [])]
        for where, other in by_name.get(symbol.name, []):
            if _family(where) != family or any(where == seen and other is same for seen, same, _ground in pairs):
                continue
            if before.area(where) == now.area(path) and where != path:
                pairs.append((where, other, "G2"))
            elif (where, other.name) in registered or core.reason(where, team, before.graph):
                if before.area(where) != now.area(path) and _usual_place(before, symbol.name, path) \
                        and _place(where)[0] == _place(path)[0]:
                    notes.append(f"note — {path}:{symbol.line} {symbol.name}: the same name is in {where}, as in "
                                 "three areas or more at this place. If it does the same work, use one of them")
                else:
                    pairs.append((where, other, "G3"))
            else:
                notes.append(f"note — {path}:{symbol.line} {symbol.name}: the same name is in another area: "
                             f"{where}:{other.line} {other.name}{other.signature}. If it does the same work, use it")
        found += [Candidate(path, symbol, where, other, ground) for where, other, ground in pairs]
        if symbol.kind == "function" and not symbol.doc and core.reason(path, team, now.graph):
            notes.append(f"note — {path}:{symbol.line} {symbol.name}: other areas use this file, and the new public "
                         "function has no description. Its first line is what `akasha map` and `akasha find` show")
        notes += _name_notes(before, now, path, symbol)
    return found, notes


def _name_notes(before: Map, now: Map, path: str, symbol: Symbol) -> list[str]:
    """What the name of a new public function tells against the nearby code, as a question: never a verdict, and
    never a reason to stop. The count comes from the code before the change, so a task makes no usual word of its
    own."""
    words = codemap._words(symbol.name)
    if symbol.kind != "function" or not words:
        return []
    notes, first, area = [], words[0], now.area(path)
    for work, group in codemap.WORK.items():
        if first not in group:
            continue
        for place, enough in ((area, 3), ("", 15)):
            counted = codemap.verbs(before, place)
            near = {word: counted[word] for word in group if counted[word]}
            total = sum(near.values())
            if total < enough:
                continue
            top, most = max(near.items(), key=lambda item: item[1])
            if most * 5 >= total * 4 and top != first:
                where = area if place else "the repository"
                small = " (few names: a weak count)" if total < 10 else ""
                notes.append(f"note — {path}:{symbol.line} {symbol.name}: {where} names {work} {top}_ ({most} of "
                             f"{total}){small}. Is this the same kind of work? When the work differs, let the name "
                             "show the difference")
            break
    if path.endswith(core.PY):
        if first in TRUE_OR_FALSE and (not symbol.gives or (symbol.returns and symbol.returns not in ("bool",
                                                                                                    "'bool'"))):
            notes.append(f"note — {path}:{symbol.line} {symbol.name}: a name with {first}_ gives true or false, and "
                         "this one may not (a doubt, not an error)")
        elif first == "get" and not symbol.gives:
            notes.append(f"note — {path}:{symbol.line} {symbol.name}: a name with get_ gives a value, and this one "
                         "may not (a doubt, not an error)")
    return notes


def problem(found: list[Candidate], plan: str | None) -> str:
    """Why the change does not pass, or "". `plan`: the text of plan.md, or None for a task without a plan (a quick
    task)."""
    table = rows(plan or "")
    open_ones = [candidate for candidate in found if not answered(candidate, table)]
    if not open_ones:
        return ""
    lines = []
    for candidate in open_ones[:SHOWN]:
        old = candidate.old
        lines.append(f"{candidate.path}:{candidate.new.line} {candidate.new.name} — {candidate.why}\n"
                     f"    {candidate.other}:{old.line} {old.name}{old.signature}"
                     + (f" — {old.doc}" if old.doc else ""))
    more = f"\n… and {len(open_ones) - SHOWN} more" if len(open_ones) > SHOWN else ""
    first = open_ones[0]
    if plan is None:
        return ("\n".join(lines) + more + "\nA quick task has no plan for an answer. Use that code, or run `akasha "
                "upgrade <task>` for a full task with a plan")
    return ("\n".join(lines) + more + "\nUse that code, or add a row to \"Public changes\" of plan.md and ask the "
            f"reviewer again:\n    | different | {first.path}::{first.new.name} | <the difference of meaning> |\n"
            "(different: the same name, another meaning · wraps: it calls the existing code · replaces: it takes "
            "the place of the existing code, and tells when that one goes)")


@dataclass
class Found:
    """What the check found beside its verdict: the keys of the definitions that the change adds and changes."""
    added: list[str]
    changed: list[str]


def examine(team: Team, tree: Path, base: str, keep: Path | None, plan: str | None, candidates: bool = True,
            admin: bool = False, found_out: Found | None = None, maps: codemap.Pair | None = None)         -> tuple[str, str, list[str]]:
    """The check: (PASS or FAIL, what to do, the notes). `base`: the commit before the change. `candidates`: False
    for a pull request that is no task (the own procedure of the repository): it has no plan for an answer, and
    only the list of the definitions and the boundaries hold for it. `admin`: the change is of an administrator.
    The rules of the team come from the base branch: a pull request cannot make the check weaker. `maps`: the maps
    of the change, when another check of the same run reads them too."""
    edited = names(tree, "diff", "--name-only", "--no-renames", "--diff-filter=AM", base)
    changed = [path for path in edited if path.endswith(core.PY + core.JS) and not core.TEST.search(path)]
    pinned = _pins(team, tree, base)                  # also for a pull request that is no task
    if not changed and not team.definitions_on:
        return ("FAIL" if pinned else "PASS"), "\n".join(pinned), []
    maps = maps or codemap.Pair(tree, team, keep, base)
    now, before = maps.now, maps.before
    table = rows(plan or "")
    stops: list[str] = list(pinned)
    loose: list[str] = []
    registered: frozenset = frozenset()
    if team.definitions_on:
        place = definitions.place(tree)
        listed = definitions.listing(team, definitions.at(tree, base), _text(place) if place.is_file() else None,
                                     admin, table, now, lambda path: (tree / path).is_file(), candidates,
                                     lambda path: git(tree, "cat-file", "-e", f"{base}:{path}").returncode == 0)
        stops += listed.problems
        if candidates:
            public = tuple(item for rule in team.boundaries for item in rule.public)
            stops += definitions.entry_problems(listed, before, now, public, table, matches)
            modified = names(tree, "diff", "--name-only", "--no-renames", "--diff-filter=MD", base)
            stops += definitions.change_problems(listed, modified, table)
        registered = frozenset(definitions.split(where) for item in listed.items if item.key not in listed.added
                               for where in item.implementation)
        if found_out is not None:
            found_out.added, found_out.changed = listed.added, listed.changed
    if team.boundaries:
        circles = any(rule.acyclic for rule in team.boundaries)       # they need each file of before, not only
        was = boundaries.imports_of(now.graph, _texts_at(tree, base, list(before.files) if circles else changed))
        stops += boundaries.problems(team, was, now.graph, changed)
        stops += boundaries.unread_entries(team, now.files)
        loose = boundaries.unresolved(now.graph, {path: _text(tree / path) for path in changed
                                                  if (tree / path).is_file()})
        stops += boundaries.cycles(team, was, now.graph)
    found, notes = compare(team, before, now, changed, registered)
    notes += loose
    unread = [f"note — {path}: Akasha could not read it ({now.files[path].unread}), so it compared no name of it"
              for path in changed if path in now.files and now.files[path].unread]
    why = problem(found, plan) if candidates else ""
    why = "\n".join(item for item in ("\n".join(stops[:SHOWN * 2]), why) if item)
    return ("FAIL" if why else "PASS"), why, (notes + unread)[:SHOWN * 2]


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def structure(team: Team, tree: Path, base: str) -> tuple[list[str], list[str], bool]:
    """The new areas and the new folder names of a change, and whether it makes the first area
    (boundaries.new_structure)."""
    if not team.core_areas:
        return [], [], False
    skip = team.record_roots + (team.work_dir,)
    return boundaries.new_structure(team, paths_at(tree, base, skip), paths(tree, skip, others=True))


def _pins(team: Team, tree: Path, base: str) -> list[str]:
    """The pins that the change does not keep ([pins] policy = "new" or "all"), or []."""
    if team.pins_policy not in ("new", "all"):
        return []
    def now(path: str) -> str | None:
        try:
            return _text(tree / path)
        except OSError:
            return None

    def then(path: str) -> str | None:
        shown = git(tree, "show", f"{base}:{path}")
        return shown.stdout if shown.returncode == 0 else None

    skip = team.record_roots + (team.work_dir,)
    before = pins.observe(paths_at(tree, base, skip), then) if team.pins_policy == "new" else []
    return pins.problems(team.pins_policy, before, pins.observe(paths(tree, skip, others=True), now),
                         names(tree, "diff", "--name-only", "--no-renames", "--diff-filter=AM", base),
                         names(tree, "diff", "--name-only", "--no-renames", "--diff-filter=D", base))


def _texts_at(tree: Path, commit: str, paths: list[str]) -> dict[str, str]:
    """The text of each file in a commit. A file that was not there has none."""
    found = {}
    for path in paths:
        shown = git(tree, "show", f"{commit}:{path}")
        if shown.returncode == 0:
            found[path] = shown.stdout
    return found
