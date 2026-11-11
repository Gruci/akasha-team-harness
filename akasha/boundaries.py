"""The boundaries of a team: which code may import which.

akasha.toml names them:

    [boundaries.areas]
    private = ["domains/*/**"]                              # the files of an area
    public = ["domains/*/api.py", "domains/*/index.ts"]     # are open to the outside only through these entries
    except = ["app/main.py -> domains/billing/jobs/nightly.py"]     # one exact pair

    [boundaries.screen-data]
    from = ["frontend/**"]                                  # these files
    not = ["db/**"]                                         # do not import these files

One question decides the first kind: is the target of an import that crosses an area the public entry of that area?
Imports inside an area are free. `public` names the files that may be a target; it frees no import that leaves such a
file. An area is a folder of [core] areas; a file outside each area (app.py at the top) is no part of this rule.

    [boundaries.no-cycles]
    acyclic = ["domains/*"]                                # the imports between these areas make no circle

The check looks only at the imports that the change makes new, with the import graph of the code now. It holds for
static imports. It does not see a call through an address, a query that a screen runs, or an access while the code
runs. Two public entries that import each other pass the first kind: a rule with `acyclic` stops those."""

from __future__ import annotations

from akasha import core
from akasha.checks import matches
from akasha.config import Boundary, Team


def _in_area(path: str, team: Team) -> str:
    """The area of a file, or "" for a file outside each folder of [core] areas."""
    folders = path.split("/")[:-1]
    for pattern in team.core_areas:
        size = pattern.count("/") + 1
        if len(folders) >= size and matches("/".join(folders[:size]), pattern):
            return "/".join(folders[:size])
    return ""


def _imports(graph: core.Graph, path: str) -> set[str]:
    return {target for target, users in graph.users.items() if path in users}


def imports_of(graph: core.Graph, texts: dict[str, str]) -> dict[str, set[str]]:
    """What each file imported before the change: its text of then, read against the files of now."""
    return {path: graph._imports(path, text) - {path} for path, text in texts.items()}


def _allowed(rule: Boundary, source: str, target: str) -> bool:
    return any(matches(source, one) and matches(target, other) for one, other in rule.exceptions)


def crossing(team: Team, rule: Boundary, source: str, target: str) -> str:
    """Why the import of `target` by `source` crosses the boundary, or ""."""
    if rule.acyclic or _allowed(rule, source, target):
        return ""
    if rule.sources or rule.forbidden:
        if any(matches(source, item) for item in rule.sources) and any(matches(target, item) for item in
                                                                       rule.forbidden):
            return f"[boundaries.{rule.name}]: {source} imports {target}, and these files do not import those"
        return ""
    area = _in_area(target, team)
    if not area or area == _in_area(source, team) or not any(matches(target, item) for item in rule.private) \
            or any(matches(target, item) for item in rule.public):
        return ""
    return (f"[boundaries.{rule.name}]: {source} imports {target}, which is inside the area {area}. Go through "
            f"its public entry ({', '.join(rule.public)})")


def problems(team: Team, before: dict[str, set[str]], now: core.Graph, changed: list[str]) -> list[str]:
    """The boundaries that the change newly crosses: only an import that was not there before the change.
    `before`: what each changed file imported before (imports_of)."""
    found = []
    for path in changed:
        old = before.get(path, set())
        for target in sorted(_imports(now, path) - old):
            found += [why for rule in team.boundaries if (why := crossing(team, rule, path, target))]
    return found


def unresolved(graph: core.Graph, texts: dict[str, str]) -> list[str]:
    """The relative imports of JavaScript and TypeScript files that Akasha cannot follow to a file: the rules see
    nothing of them. A style sheet or an image is no code."""
    found = []
    for path, text in sorted(texts.items()):
        if not path.endswith(core.JS):
            continue
        for spec in core.JS_IMPORT.findall(text):
            extension = spec.rsplit("/", 1)[-1].rpartition(".")[2] if "." in spec.rsplit("/", 1)[-1] else ""
            if spec.startswith(".") and (not extension or "." + extension in core.JS) \
                    and graph._script(path, spec) is None:
                found.append(f"note — {path}: Akasha cannot follow the import {spec}, so no boundary sees it")
    return found


def unread_entries(team: Team, files: dict) -> list[str]:
    """The entry files of the areas whose public names Akasha cannot tell: the rule cannot hold for them."""
    public = [item for rule in team.boundaries for item in rule.public]
    return [f"{path}: Akasha cannot tell which names this entry file gives out ({held.unread}). Name them: a plain "
            "__all__ list in Python, `export { a, b } from` in TypeScript"
            for path, held in sorted(files.items()) if held.unread and any(matches(path, item) for item in public)]


def _area_edges(rule: Boundary, imports: dict[str, set[str]]) -> dict[tuple[str, str], tuple[str, str]]:
    """The imports between the areas of an acyclic rule: (area, area that it imports) -> one pair of files that
    shows it. An exact pair of `except` does not count."""
    def area(path: str) -> str:
        folders = path.split("/")[:-1]
        for item in rule.acyclic:
            size = item.count("/") + 1
            if len(folders) >= size and matches("/".join(folders[:size]), item):
                return "/".join(folders[:size])
        return ""

    edges: dict[tuple[str, str], tuple[str, str]] = {}
    for user, targets in sorted(imports.items()):
        one = area(user)
        for target in sorted(targets):
            other = area(target)
            if one and other and one != other and not _allowed(rule, user, target):
                edges.setdefault((one, other), (user, target))
    return edges


def cycles(team: Team, before: dict[str, set[str]], now: core.Graph) -> list[str]:
    """The new imports between areas that are on a cycle: an acyclic rule names the areas. A relation between two
    areas that was there before the change passes; a new one fails when the imports lead back from its target to its
    source, also when that cycle was there already. `before`: what each file imported before the change
    (imports_of, of each file). The graph is of static imports: an import of a type only counts too."""
    after: dict[str, set[str]] = {}
    for target, users in now.users.items():
        for user in users:
            after.setdefault(user, set()).add(target)
    found = []
    for rule in team.boundaries:
        if not rule.acyclic:
            continue
        old, edges = _area_edges(rule, before), _area_edges(rule, after)
        reach: dict[str, set[str]] = {}
        for source, target in edges:
            reach.setdefault(source, set()).add(target)
        for (source, target), (user, used) in sorted(edges.items()):
            if (source, target) in old:
                continue
            path = _path(reach, target, source)
            if path:
                found.append(f"[boundaries.{rule.name}]: {user} imports {used}, a new relation {source} -> {target} "
                             f"on a cycle of areas ({' -> '.join([source, *path])}). The areas of this rule do not "
                             "import each other in a circle")
    return found


def _path(reach: dict[str, set[str]], start: str, goal: str) -> list[str]:
    """The areas from `start` to `goal` along the imports, or [] when no path leads there."""
    seen, stack = {start}, [[start]]
    while stack:
        path = stack.pop()
        if path[-1] == goal:
            return path
        for following in sorted(reach.get(path[-1], ())):
            if following not in seen:
                seen.add(following)
                stack.append([*path, following])
    return []


def new_structure(team: Team, before: list[str], now: list[str]) -> tuple[list[str], list[str], bool]:
    """What a change makes new in the structure: the areas that were not there, the folder names inside an area
    that no area had before, and whether it makes the first area of the repository. `before` and `now`: the files of
    the repository before and after the change. It is a fact for the reviewer and a notice, never a stop: a folder
    that a framework makes is no new policy."""
    old_areas = {area for path in before if (area := _in_area(path, team))}
    old_folders = {part for path in before if (area := _in_area(path, team))
                   for part in path[len(area) + 1:].split("/")[:-1]}
    areas, folders = [], []
    for path in sorted(set(now) - set(before)):
        area = _in_area(path, team)
        if not area:
            continue
        if area not in old_areas and area not in areas:
            areas.append(area)
        for part in path[len(area) + 1:].split("/")[:-1]:
            if part not in old_folders and part not in folders:
                folders.append(part)
    return areas, folders, bool(areas) and not old_areas
