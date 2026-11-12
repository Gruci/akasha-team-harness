"""The sheets of the areas: the map of the product, one sheet for each area.

An area is a folder of [core] areas. Its sheet is the file area.toml in that folder:

    purpose = "Takes an order and changes its state"    # one line: what the area keeps
    owners = ["mina"]                                   # GitHub names. Optional
    uses = ["catalog", "payments"]                      # the areas that its code calls
    contracts = ["openapi.yaml"]                        # files of the area that other parts rely on
    tables = ["orders", "order_items"]                  # the tables that only this area writes

A sheet is with its area, so two tasks in two areas never change the same file. `akasha map` joins the sheets with
the code: what each area keeps, its entry, whom it uses, and how large it is. The sheets say what the structure is
meant to be, and the code says what it is. The check `map` holds them together. It looks only at what a change makes
new, so a repository with old code can draw its map at any time:

- A new area has a sheet with a purpose.
- New code in a new folder outside each area fails: it goes into the area that keeps that work, or into a new area.
- A new import from one area to another fails when the sheet of the first one does not name the second in `uses`.
- A new public name of an entry file, or of a file that other areas use, has a description of one line.
- New code of an area does not write a table of another area.

A change of a sheet, and a change of existing lines of a contract, wait for the approval of an administrator at the
landing, as a change of core code does (`changed`): they change the structure. All else in an area is free. A
repository without a sheet has no map yet: `akasha map --draft` writes the first sheets from the code, and an
administrator corrects and merges them.

The sheets and the folders make the map in any language. The imports and the public names come from the code of the
languages that Akasha reads (core.READ: Python, JavaScript, TypeScript, Java, Kotlin, and Go); for another language
the rule of `uses` and the rule of the descriptions do not hold, and all else does."""

from __future__ import annotations

import json
import posixpath
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

from akasha import core, diff
from akasha.boundaries import _in_area as home, imports_of
from akasha.checks import matches
from akasha.config import Team
from akasha.repo import git, paths, paths_at

AREA_FILE = "area.toml"
CHECK = "map"                  # the name of the check
KEYS = ("purpose", "owners", "uses", "contracts", "tables")
TODO = "TODO"
SHOWN = 8                      # the problems and the notes that the output names
# The files that count as code for the place of a new folder. The names and the imports are read only of core.READ
CODE = core.READ + (".rs", ".rb", ".php", ".cs", ".swift", ".scala")
WRITE = re.compile(r"\b(?:insert\s+into|update|delete\s+from|truncate(?:\s+table)?|alter\s+table|drop\s+table)"
                   r"\s+[\"`\[]?([A-Za-z_][\w.]*)", re.I)


@dataclass(frozen=True)
class Sheet:
    area: str
    purpose: str = ""
    owners: tuple[str, ...] = ()
    uses: tuple[str, ...] = ()
    contracts: tuple[str, ...] = ()
    tables: tuple[str, ...] = ()
    problem: str = ""              # why the sheet is incorrect, or ""


def place(area: str) -> str:
    return f"{area}/{AREA_FILE}"


def parse(area: str, text: str) -> Sheet:
    """The sheet of an area from its text. An incorrect sheet keeps what Akasha could read, and tells the problem."""
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        return Sheet(area, problem=f"it is no TOML: {error}")
    problems = [f"it has the key {key}, and a sheet has only {', '.join(KEYS)}"
                for key in sorted(set(data) - set(KEYS))]
    lists = {}
    for key in KEYS[1:]:
        value = data.get(key, [])
        if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
            problems.append(f"{key} is a list of text values")
            value = []
        lists[key] = tuple(item.strip().strip("/") for item in value)
    purpose = data.get("purpose", "")
    purpose = purpose.strip() if isinstance(purpose, str) else ""
    if not purpose or purpose.upper().startswith(TODO) or "\n" in purpose:
        problems.append("purpose is one line that tells what the area keeps")
    return Sheet(area, purpose, tuple(name.lstrip("@").lower() for name in lists["owners"]), lists["uses"],
                 lists["contracts"], tuple(name.lower() for name in lists["tables"]), "; ".join(problems))


def areas_of(team: Team, files: list[str]) -> list[str]:
    """The areas that hold a file, in their order."""
    return sorted({area for path in files if (area := home(path, team))})


def read(team: Team, tree: Path, files: list[str]) -> dict[str, Sheet]:
    """area -> its sheet in the work copy, for each area that has one."""
    found = {}
    for path in files:
        area = posixpath.dirname(path)
        if posixpath.basename(path) == AREA_FILE and home(path, team) == area:
            try:
                found[area] = parse(area, (tree / path).read_text(encoding="utf-8", errors="replace"))
            except OSError as error:
                found[area] = Sheet(area, problem=f"Akasha cannot read it: {error}")
    return found


def read_at(team: Team, tree: Path, commit: str, files: list[str]) -> dict[str, Sheet]:
    """area -> its sheet in a commit. `files`: the files of that commit."""
    found = {}
    for path in files:
        area = posixpath.dirname(path)
        if posixpath.basename(path) == AREA_FILE and home(path, team) == area:
            shown = git(tree, "show", f"{commit}:{path}")
            if shown.returncode == 0:
                found[area] = parse(area, shown.stdout)
    return found


def resolve(name: str, areas: list[str]) -> str:
    """The area that a name of `uses` means: its whole folder, or the end of it when one area only has that end."""
    name = name.strip("/")
    if name in areas:
        return name
    hits = [area for area in areas if area.endswith("/" + name)]
    return hits[0] if len(hits) == 1 else ""


def short(area: str, areas: list[str]) -> str:
    """The shortest name of an area that `uses` can hold: its last folder when no other area ends with it."""
    last = area.rsplit("/", 1)[-1]
    return last if resolve(last, areas) == area else area


def edges(team: Team, users: dict[str, set[str]]) -> dict[tuple[str, str], tuple[str, str]]:
    """The imports between areas: (area, area that it imports) -> one pair of files that shows it. `users`: which
    files import each file (core.Graph)."""
    found: dict[tuple[str, str], tuple[str, str]] = {}
    for target, importers in sorted(users.items()):
        other = home(target, team)
        for user in sorted(importers):
            one = home(user, team)
            if one and other and one != other:
                found.setdefault((one, other), (user, target))
    return found


def _code(path: str) -> bool:
    return path.endswith(CODE) and not core.TEST.search(path)


def _entries(team: Team, area: str, files: list[str]) -> list[str]:
    public = [item for rule in team.boundaries for item in rule.public]
    return [path for path in files if path.startswith(area + "/") and any(matches(path, item) for item in public)]


def data(team: Team, tree: Path, found) -> dict:
    """The map of the product as data: each area with its sheet and what the code shows. `found`: codemap.Map of the
    work copy. Another program reads this form (`akasha map --json`)."""
    skip = team.record_roots + (team.work_dir,)
    files = paths(tree, skip, others=True)
    areas = areas_of(team, files)
    sheets = read(team, tree, files)
    seen = edges(team, found.graph.users) if areas else {}
    counted = found.areas()
    listed = []
    for area in areas:
        sheet = sheets.get(area)
        entries = _entries(team, area, files)
        said = next((line for path in entries if (line := _module_doc(tree, path))), "")
        observed = sorted(other for one, other in seen if one == area)
        declared = [resolve(name, areas) or name for name in sheet.uses] if sheet else []
        listed.append({"area": area, "sheet": bool(sheet), "purpose": sheet.purpose if sheet else "",
                       "entry_says": said, "owners": list(sheet.owners) if sheet else [],
                       "entries": entries, "uses": declared, "observed_uses": observed,
                       "contracts": list(sheet.contracts) if sheet else [],
                       "tables": list(sheet.tables) if sheet else [],
                       "problem": sheet.problem if sheet else "",
                       "files": sum(1 for path in files if path.startswith(area + "/") and _code(path)),
                       "public_names": counted.get(area, (0, 0))[0]})
    outside = sorted({path.split("/")[0] + ("/" if "/" in path else "") for path in files
                      if _code(path) and not home(path, team)})
    return {"areas": listed, "outside": outside,
            "unread": {kind: len(names) for kind, names in found.unread().items()}}


def _module_doc(tree: Path, path: str) -> str:
    """The first line of the description at the top of a file: a docstring of Python, or a comment at the top."""
    try:
        text = (tree / path).read_text(encoding="utf-8", errors="replace")[:4000]
    except OSError:
        return ""
    if path.endswith(core.PY):
        hit = re.match(r'\s*(?:#[^\n]*\n\s*)*(?:[rRuU]?)("""|\'\'\')(.*?)\1', text, re.S)
        return _first(hit.group(2)) if hit else ""
    hit = re.match(r"\s*/\*\*?(.*?)\*/", text, re.S) or re.match(r"\s*((?://[^\n]*\n)+)", text)
    return _first(re.sub(r"(?m)^\s*(?://+|\*)\s?", "", hit.group(1))) if hit else ""


def _first(text: str) -> str:
    for line in text.strip().splitlines():
        line = line.strip(" *\t")
        if line and not line.startswith("@"):
            return line[:160]
    return ""


def drawn(team: Team, files: list[str]) -> bool:
    """True when the repository has a sheet: its map is drawn, and the check `map` holds."""
    return any(posixpath.basename(path) == AREA_FILE and home(path, team) == posixpath.dirname(path)
               for path in files)


def overview(team: Team, tree: Path, found) -> list[str]:
    """The top of `akasha map` when the map is drawn: one area in two lines."""
    held = data(team, tree, found)
    areas = [item["area"] for item in held["areas"]]
    lines = []
    for item in held["areas"]:
        purpose = item["purpose"] or item["entry_says"]
        lines.append(f"{item['area']} — " + (purpose or "no purpose yet") + ("" if item["sheet"] else
                                                                           " (no sheet: `akasha map --draft`)"))
        declared = [short(area, areas) for area in item["uses"]]
        extra = [short(area, areas) for area in item["observed_uses"] if area not in item["uses"]]
        uses = ", ".join(declared) or "none"
        if extra and item["sheet"]:
            uses += f" (the code also imports {', '.join(extra)}, which the sheet does not name)"
        elif extra:
            uses = ", ".join(extra)
        parts = [f"entry {', '.join(item['entries'])}" if item["entries"] else "no entry file",
                 f"uses {uses}", f"{item['files']} files", f"{item['public_names']} public names"]
        if item["owners"]:
            parts.append("owners " + ", ".join(f"@{name}" for name in item["owners"]))
        if item["tables"]:
            parts.append("writes " + ", ".join(item["tables"]))
        lines.append("  " + " · ".join(parts))
        if item["problem"]:
            lines.append(f"  the sheet is incorrect: {item['problem']}")
    if held["outside"]:
        lines.append("outside each area: " + ", ".join(held["outside"]))
    lines += [f"not read ({kind}): {count} files" for kind, count in held["unread"].items()]
    lines.append("`akasha map <folder>` shows the public names of an area · `akasha find <words>` searches them")
    return lines


def as_json(team: Team, tree: Path, found) -> str:
    return json.dumps(data(team, tree, found), ensure_ascii=False, indent=2)


def draft(team: Team, tree: Path, found) -> list[str]:
    """Write a first sheet for each area that has none, from what the code shows, and give their paths. The purpose
    comes from the top of the entry file; without one it is a TODO that the check `map` refuses, so a person or the
    AI writes it after a look at the code."""
    held = data(team, tree, found)
    areas = [item["area"] for item in held["areas"]]
    written = []
    for item in held["areas"]:
        if item["sheet"]:
            continue
        purpose = item["entry_says"] or f"{TODO}: one line that tells what this area keeps"
        uses = ", ".join(json.dumps(short(area, areas)) for area in item["observed_uses"])
        text = (f"# The sheet of the area {item['area']}: `akasha map` joins the sheets into the map of the product.\n"
                "# A change of this file waits for the approval of an administrator.\n"
                f"purpose = {json.dumps(purpose, ensure_ascii=False)}\n"
                f"uses = [{uses}]                # the areas that this code calls, as the imports show now\n"
                "# owners = []                 # GitHub names\n"
                "# contracts = []              # files of this area that other parts rely on, for example an API file\n"
                "# tables = []                 # the tables that only this area writes\n")
        path = tree / place(item["area"])
        path.write_text(text, encoding="utf-8", newline="\n")
        written.append(place(item["area"]))
    return written


def changed(team: Team, tree: Path, base: str) -> dict[str, str]:
    """The files of the structure that the work copy changed since the base commit, with the reason: each sheet, and
    each contract whose existing lines changed. The landing waits for an administrator, as for core code."""
    if not team.core_areas:
        return {}
    found, sheets = {}, None
    for path, (_added, deleted) in diff.counts(tree, base).items():
        area = home(path, team)
        if not area:
            continue
        if path == place(area):
            found[path] = f"the sheet of the area {area}: the map of the product"
        elif deleted:
            if sheets is None:
                skip = team.record_roots + (team.work_dir,)
                sheets = read_at(team, tree, base, paths_at(tree, base, skip))
            sheet = sheets.get(area)
            if sheet and any(matches(path[len(area) + 1:], item) for item in sheet.contracts):
                found[path] = f"a contract of the area {area}"
    return found


def examine(team: Team, tree: Path, base: str, changed_files: list[str], maps, admin: bool = False) \
        -> tuple[str, str, list[str]]:
    """The check `map`: (PASS, FAIL, or NOT_NEEDED, what to do, the notes). `maps`: codemap.Pair, the maps of the
    work copy and of the base commit; it reads the code only when the check needs it. `admin`: the change is of an
    administrator, who can make a new folder outside each area."""
    if not team.core_areas:
        return "NOT_NEEDED", "akasha.toml names no areas ([core] areas), so the product has no map", []
    skip = team.record_roots + (team.work_dir,)
    now_files, old_files = paths(tree, skip, others=True), paths_at(tree, base, skip)
    if not drawn(team, now_files) and not drawn(team, old_files):
        return "NOT_NEEDED", "the map is not drawn yet: an administrator runs `akasha map --draft` in a task", []
    sheets, areas = read(team, tree, now_files), areas_of(team, now_files)
    stops: list[str] = []
    notes: list[str] = []
    # 1. Each sheet is correct, and no two areas write the same table
    for area, sheet in sorted(sheets.items()):
        if sheet.problem:
            stops.append(f"{place(area)}: {sheet.problem}")
        stops += [f"{place(area)}: uses names {name}, and no area has that folder (`akasha map` shows the areas)"
                  for name in sheet.uses if not resolve(name, areas)]
    owner: dict[str, str] = {}
    for area, sheet in sorted(sheets.items()):
        for table in sheet.tables:
            if table in owner:
                stops.append(f"{place(area)}: the table {table} is also in {place(owner[table])}. One area writes "
                             "a table")
            owner.setdefault(table, area)
    # 2. A new area has a sheet
    old_areas = set(areas_of(team, old_files))
    stops += [f"{area} is a new area without a sheet. Write {place(area)} with `purpose = \"<one line: what the area "
              "keeps>\"`; an administrator approves a new area at the landing" for area in areas
              if area not in old_areas and area not in sheets]
    # 3. New code in a new folder outside each area
    old_folders = {posixpath.dirname(path) for path in old_files}
    new_code = [path for path in sorted(set(now_files) - set(old_files)) if _code(path) and not home(path, team)]
    loose = sorted({posixpath.dirname(path) for path in new_code
                    if (folder := posixpath.dirname(path)) and folder not in old_folders
                    and not any(old.startswith(folder + "/") for old in old_folders)})
    for folder in loose:
        line = (f"{folder}/ is a new folder with code outside each area ([core] areas: {', '.join(team.core_areas)}). "
                "Put the code into the area that keeps this work (`akasha map` shows what each area keeps), or make "
                "a new area there with a sheet")
        (notes if admin else stops).append(("note — " if admin else "") + line)
    # 4 and 5 need the code
    code = [path for path in changed_files if path.endswith(core.READ) and not core.TEST.search(path)
            and (tree / path).is_file()]
    if code:
        now, before = maps.now, maps.before
        was = imports_of(now.graph, {path: shown.stdout for path in code
                                     if (shown := git(tree, "show", f"{base}:{path}")).returncode == 0})
        after: dict[str, set[str]] = {}
        for target, users in now.graph.users.items():
            for user in users:
                if user in code:
                    after.setdefault(user, set()).add(target)
        silent = set()
        for path in code:
            one = home(path, team)
            for target in sorted(after.get(path, set()) - was.get(path, set())):
                other = home(target, team)
                if not one or not other or one == other:
                    continue
                sheet = sheets.get(one)
                if sheet is None:
                    silent.add(one)
                elif other not in {resolve(name, areas) for name in sheet.uses}:
                    stops.append(f"{path} imports {target}: the area {one} starts to use {other}, and its sheet does "
                                 f"not name it. Use an area that {place(one)} names in `uses`, or add "
                                 f"\"{short(other, areas)}\" there; an administrator approves a change of a sheet")
        notes += [f"note — the area {area} has no sheet, so the map does not hold its new imports: `akasha map "
                  "--draft`" for area in sorted(silent)]
        public = [item for rule in team.boundaries for item in rule.public]
        old_names = {(path, symbol.name) for path, held in before.files.items() for symbol in held.symbols}
        for path in code:
            held = now.files.get(path)
            if held is None or not (any(matches(path, item) for item in public) or core.reason(path, team, now.graph)):
                continue
            stops += [f"{path}:{symbol.line} {symbol.name}: a new public name of a file that other areas call has "
                      "no description. Write one line that tells what it gives: `akasha map` and `akasha find` show "
                      "that line" for symbol in held.symbols
                      if (path, symbol.name) not in old_names and not symbol.doc]
    # 6. A write of a table of another area
    if owner:
        for path, lines in diff.added(tree, base, [path for path in changed_files if _code(path)]).items():
            one = home(path, team)
            for at, text in lines:
                for table in WRITE.findall(text):
                    table = table.rsplit(".", 1)[-1].lower()
                    if one and owner.get(table, one) != one:
                        stops.append(f"{path}:{at} writes the table {table}, which the area {owner[table]} keeps "
                                     f"({place(owner[table])}). Call the entry of that area")
    why = "\n".join(stops[:SHOWN * 2]) + (f"\n… and {len(stops) - SHOWN * 2} more" if len(stops) > SHOWN * 2 else "")
    return ("FAIL" if stops else "PASS"), why, notes[:SHOWN]
