"""`akasha map --report`: what an administrator sees before the team turns on a rule.

A repository that has code starts with the definitions and the boundaries off. This report shows what is there: the
files that several areas import, the addresses that screens call, the names that are in more than one file of an
area, the words of the names, the cycles between areas, the path of the lint of names, the languages without a
required check, and the versions that float. It makes no rule: the direction of the imports of today is not the right
structure for that reason. An administrator reads it and decides, in a task without a screen.

Each line says what it is: `observed` (a fact of the code now) or `policy` (what the team wrote into akasha.toml)."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from akasha import boundaries, codemap, core, langs
from akasha.checks import matches
from akasha.codemap import Map
from akasha.config import Boundary, Team

MOST = 8
LINT_FILES = ("ruff.toml", ".ruff.toml", "pyproject.toml")


def _shared(found: Map, team: Team) -> list[str]:
    hits = []
    for path in found.files:
        users = found.graph.users.get(path, set())
        areas = {found.area(user) for user in users} - {found.area(path)}
        if len(areas) >= team.core_used_by:
            hits.append((len(areas), path, len(users)))
    lines = [f"observed — {path}: {users} files of {areas} other areas import it" for areas, path, users in
             sorted(hits, reverse=True)[:MOST]]
    return lines + ([f"observed — … {len(hits) - MOST} more files that several areas import"] if len(hits) > MOST
                    else []) or ["observed — no file that several areas import"]


def _addresses(found: Map) -> list[str]:
    busy = [(len(screens), method, address, handler) for method, address, handler, _line, screens in found.routes()
            if len(screens) >= 2]
    return [f"observed — {method} {address} ({handler}): {count} screen files call it"
            for count, method, address, handler in sorted(busy, reverse=True)[:MOST]]


def _twins(found: Map) -> list[str]:
    """The names that more than one file of the same area holds, and the Python bodies that are there twice."""
    by_name: dict[tuple[str, str], list[str]] = {}
    by_body: dict[str, list[str]] = {}
    for path, held in found.files.items():
        for symbol in held.symbols:
            by_name.setdefault((found.area(path), symbol.name), []).append(path)
            if symbol.digest and symbol.size >= 3:
                by_body.setdefault(symbol.digest, []).append(f"{path}::{symbol.name}")
    names = sorted((key, files) for key, files in by_name.items() if len(set(files)) > 1)
    bodies = sorted(places for places in by_body.values() if len(places) > 1)
    lines = [f"observed — {len(names)} names are in more than one file of one area, for example "
             + "; ".join(f"{name} in {', '.join(sorted(set(files))[:2])}" for (_area, name), files in names[:3])] \
        if names else []
    lines += [f"observed — {len(bodies)} bodies of Python are there more than once, for example "
              + "; ".join(" = ".join(places[:2]) for places in bodies[:3])] if bodies else []
    return lines or ["observed — no name that is twice in one area, and no body that is there twice"]


def _words(found: Map) -> list[str]:
    usual, open_ones = [], []
    for area in found.areas():
        for line in codemap.usual_words(found, area):
            (usual if "the usual word" in line else open_ones if "no usual word" in line else []).append(line)
    return [f"observed — {line}" for line in usual[:MOST]] + \
        [f"observed — {line.split(': one word')[0]} (the count is small or divided: this is no defect and no task)"
         for line in open_ones[:MOST]]


def _cycles(found: Map, team: Team) -> list[str]:
    if not team.core_areas:
        return []
    after: dict[str, set[str]] = {}
    for target, users in found.graph.users.items():
        for user in users:
            after.setdefault(user, set()).add(target)
    edges = boundaries._area_edges(Boundary("", acyclic=team.core_areas), after)
    pairs = sorted(f"{user} imports {used}, and {edges[(other, area)][0]} imports {edges[(other, area)][1]}"
                   for (area, other), (user, used) in edges.items() if area < other and (other, area) in edges)
    return [f"observed — two areas import each other: {text}" for text in pairs[:MOST]] or \
        ["observed — no two areas import each other"]


def _crossings(found: Map, team: Team) -> list[str]:
    """The imports of now that cross a boundary of the team: the check stops only a new one."""
    hits = []
    for target, users in found.graph.users.items():
        for user in sorted(users):
            hits += [why for rule in team.boundaries if (why := boundaries.crossing(team, rule, user, target))]
    if not team.boundaries:
        return ["policy — no boundary is on ([boundaries])"]
    return [f"policy — {len(team.boundaries)} boundaries are on; {len(hits)} imports of now cross one"] + \
        [f"observed — {why.split('. Go through')[0]}" for why in hits[:MOST]]


def lint_path(root: Path, team: Team, files: list[str]) -> list[str]:
    """How the lint of names reaches a change, in four steps that Akasha can see: installed, the rule of names is
    on, wired to a required check, or not confirmed. It never says that the rule holds when it could not see it."""
    lines = []
    commands = " ".join(f"{check.command} {check.command_windows}" for name, check in team.checks.items()
                        if name in team.required_checks)
    if any(path.endswith(".py") for path in files):
        on = False
        for name in LINT_FILES:
            try:
                text = (root / name).read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            on = on or bool(re.search(r"(extend-)?select\s*=\s*\[[^\]]*\"N\d*\"", text))
        on = on or "--extend-select N" in commands or "--select N" in commands
        wired = "ruff" in commands
        lines.append("observed — Python names (ruff, the rules N): "
                     + ("installed" if shutil.which("ruff") else "not confirmed on this computer") + " · "
                     + ("the rule of names is on" if on else "the rule of names is not on") + " · "
                     + ("wired to a required check" if wired else "not confirmed in a required check"))
        if not (on and wired):
            lines.append("proposal — a required check `python -m ruff check --extend-select N .` with only_when = "
                         "[\"**/*.py\"], in a task of an administrator")
    if any(path.endswith(core.JS) for path in files):
        has_config = any(re.search(r"(^|/)(eslint\.config\.[cm]?[jt]s|\.eslintrc[^/]*)$", path) for path in files)
        wired = "eslint" in commands
        lines.append("observed — TypeScript and JavaScript names (ESLint, naming-convention): "
                     + ("a config of ESLint is in the repository" if has_config else "no config of ESLint") + " · "
                     + "the rule of names is not confirmed (Akasha does not run ESLint) · "
                     + ("wired to a required check" if wired else "not confirmed in a required check"))
        if not (has_config and wired):
            lines.append("proposal — @typescript-eslint/naming-convention and react/jsx-handler-names in the config "
                         "of ESLint, and a required check that runs it, in a task of an administrator")
    return lines


def unchecked(team: Team, files: list[str]) -> list[str]:
    """The languages of the repository whose files no required check with a command names."""
    patterns = [item for name, check in team.checks.items() if name in team.required_checks
                for item in check.only_when]
    open_checks = any(not check.only_when for name, check in team.checks.items() if name in team.required_checks)
    found = []
    for pack in langs.packs():
        mine = [path for path in files if path.endswith(pack.extensions) and not core.TEST.search(path)]
        if mine and not open_checks and not any(matches(path, item) for path in mine[:200] for item in patterns):
            found.append(f"observed — {len(mine)} files of {pack.name} have no required check: add its tests and "
                         "its lint to [checks] required")
    return found


def lines(root: Path, team: Team, keep: Path | None = None) -> list[str]:
    from akasha import setup
    found = Map(root, team, keep)
    files = list(found.files)
    pins = setup.pin_listings(root, team)
    said = [
        "# What Akasha observes in this repository. It is what the code is now, and no rule.",
        "## Files that several areas import (which of them hold a definition of the team?)", *_shared(found, team),
        *_addresses(found),
        "## Names and bodies that are there more than once (a task to make them one?)", *_twins(found),
        "## The words of the names (what does the guide of the team say?)", *_words(found),
        "## Imports between areas (a boundary, an exception, or a repair?)", *_crossings(found, team),
        *_cycles(found, team),
        "## The lint of names", *lint_path(root, team, files),
        "## Languages without a required check", *(unchecked(team, files) or ["observed — each language has one"]),
        "## Versions ([pins] policy)",
        f"policy — [pins] policy = \"{team.pins_policy}\"" if team.pins_policy else
        "policy — not answered yet: observe, new, or all",
        *([f"observed — {item.line}" for item in pins] or ["observed — no list of libraries and no Dockerfile"]),
        "## The definitions",
        "policy — the definitions are on" if team.definitions_on else
        "policy — the definitions are off: an administrator turns them on with [definitions] on = true, and "
        "registers first the values that disagreed before",
    ]
    unread = found.unread()
    if unread:
        said += ["## What Akasha could not read"] + [f"observed — {kind}: {len(paths)} files, for example "
                                                     f"{', '.join(paths[:3])}" for kind, paths in unread.items()]
    return said
