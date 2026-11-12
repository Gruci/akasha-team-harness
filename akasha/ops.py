"""The check `ops`: what a change needs so that it goes live safely and stays visible there.

Akasha cannot see a server. It can see, in the lines that a change adds, the usual ways in which code that passes its
tests still fails in production. Each rule has a name, and an administrator can turn one off or allow one file:

    [ops]
    migrations = ["db/migrations/**"]     # the files that change the database. The default: a folder migrations
    env = [".env.example"]                # the files that name each setting of the server. The default: such a file
    off = ["timeout"]                     # rules that the team does not use
    allow = ["migration: db/migrations/0042_drop_old_table.sql"]     # one rule for some files

| Rule | It fails when a new line | Why |
| migration | removes or renames a table or a column, or a new file has the number of another migration | The code that runs now still reads the old shape while the deployment goes on. Data does not come back with a revert |
| env | reads a setting that no file of `env` names | The server does not have the setting after the deployment |
| timeout | calls another system without a time limit (Python: requests, httpx, urlopen) | One slow system then holds each worker of this one |
| silent | catches an error and does nothing with it | Nobody sees the failure in production |

It reads Python with `ast`, and JavaScript and TypeScript with patterns. The linter of the team sees more of each
language: `akasha setup` names the lint rules of this kind for the languages that it knows. The check looks only at
the lines that the change adds, and it is no proof: it finds what a machine can find."""

from __future__ import annotations

import ast
import posixpath
import re
from pathlib import Path

from akasha import core, diff
from akasha.checks import matches
from akasha.config import Team
from akasha.repo import paths

CHECK = "ops"
RULES = ("migration", "env", "timeout", "silent")
MIGRATIONS = ("**/migrations/**", "**/migrate/**")
ENV_FILES = (".env.example", ".env.sample", ".env.template", ".env.dist")
SHOWN = 8
DESTROYS = re.compile(r"\b(drop\s+(?:table|column|index|schema|database|view)|truncate\s|"
                      r"alter\s+table\s+\S+\s+(?:drop|rename)\b|rename\s+(?:table|column)|"
                      r"op\.drop_(?:table|column|index|constraint)|"
                      r"migrations\.(?:RemoveField|DeleteModel|RenameField|RenameModel))", re.I)
NUMBER = re.compile(r"^(\d+)[_\-.]")
ENV_READS = (re.compile(r"""os\.environ(?:\.get\(\s*|\[\s*)["']([A-Z][A-Z0-9_]*)["']"""),
             re.compile(r"""os\.getenv\(\s*["']([A-Z][A-Z0-9_]*)["']"""),
             re.compile(r"""process\.env\.([A-Z][A-Z0-9_]*)"""),
             re.compile(r"""process\.env\[\s*["']([A-Z][A-Z0-9_]*)["']"""),
             re.compile(r"""import\.meta\.env\.([A-Z][A-Z0-9_]*)"""))
ENV_NAME = re.compile(r"^\s*#?\s*(?:export\s+)?([A-Z][A-Z0-9_]*)\s*=", re.M)
# Settings that the system or the build tool gives: no file of the team names them
GIVEN = {"NODE_ENV", "PATH", "HOME", "CI", "MODE", "DEV", "PROD", "BASE_URL", "SSR", "PWD", "USER", "TZ", "LANG",
         "PYTHONPATH", "TMPDIR", "TEMP", "TMP", "SHELL", "HOSTNAME", "PORT"}
METHODS = ("get", "post", "put", "patch", "delete", "head", "options", "request", "stream")
CLIENTS = ("requests", "httpx")
EMPTY_CATCH = re.compile(r"\bcatch\s*(?:\([^)]*\))?\s*\{\s*\}")


def _allowed(team: Team, rule: str, path: str) -> bool:
    return any(name == rule and matches(path, item) for name, item in team.ops_allow)


def _on(team: Team) -> tuple[str, ...]:
    return tuple(rule for rule in RULES if rule not in team.ops_off)


def _migrations(team: Team, files: list[str], lines: dict[str, list[tuple[int, str]]], new: set[str]) -> list[str]:
    patterns = team.ops_migrations or MIGRATIONS
    found = []
    for path in sorted(lines):
        if not any(matches(path, item) for item in patterns) or _allowed(team, "migration", path):
            continue
        for at, text in lines[path]:
            hit = DESTROYS.search(text)
            if hit and not text.lstrip().startswith(("--", "#", "//")):
                found.append(f"migration — {path}:{at} `{' '.join(hit.group(1).split())}` removes or renames a part of "
                             "the database. The code that runs now still reads it while the deployment goes on, and a "
                             "revert does not bring data back. Add the new shape first, move the readers and the "
                             "data, and remove the old shape in a later task; an administrator allows that last "
                             f"file: [ops] allow = [\"migration: {path}\"]")
                break
    numbers: dict[tuple[str, str], list[str]] = {}
    for path in files:
        number = NUMBER.match(posixpath.basename(path))
        if number and any(matches(path, item) for item in patterns):
            numbers.setdefault((posixpath.dirname(path), number.group(1)), []).append(path)
    for (_folder, number), same in sorted(numbers.items()):
        fresh = [path for path in same if path in new and not _allowed(team, "migration", path)]
        if len(same) > 1 and fresh:
            others = ", ".join(path for path in same if path != fresh[0])
            found.append(f"migration — {fresh[0]} has the number {number} of {others}. Two migrations with one "
                         "number run in an order that nobody chose: take the next number")
    return found


def _env(team: Team, tree: Path, files: list[str], lines: dict[str, list[tuple[int, str]]]) -> list[str]:
    templates = [path for path in files if any(matches(path, item) for item in team.ops_env)] if team.ops_env else \
        [path for path in files if posixpath.basename(path) in ENV_FILES]
    if not templates:
        return []                                     # the team keeps no list of its settings in the repository
    named = set(GIVEN)
    for path in templates:
        try:
            named |= set(ENV_NAME.findall((tree / path).read_text(encoding="utf-8", errors="replace")))
        except OSError:
            pass
    found, seen = [], set()
    for path in sorted(lines):
        if core.TEST.search(path) or path in templates or _allowed(team, "env", path):
            continue
        for at, text in lines[path]:
            for name in (hit for pattern in ENV_READS for hit in pattern.findall(text)):
                if name not in named and name not in seen:
                    seen.add(name)
                    found.append(f"env — {path}:{at} reads the setting {name}, and {', '.join(templates)} does not "
                                 f"name it: the server will not have it after the deployment. Add `{name}=` there, "
                                 "and name it in the steps of an administrator")
    return found


def _lines_of(node: ast.AST) -> range:
    return range(node.lineno, (getattr(node, "end_lineno", None) or node.lineno) + 1)


def _python(team: Team, path: str, text: str, added: set[int], rules: tuple[str, ...]) -> list[str]:
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError, RecursionError):
        return []
    found = []
    for node in ast.walk(tree):
        if "timeout" in rules and isinstance(node, ast.Call) and added.intersection(_lines_of(node)):
            where = node.func
            client = isinstance(where, ast.Attribute) and where.attr in METHODS and \
                isinstance(where.value, ast.Name) and where.value.id in CLIENTS
            opens = (where.attr if isinstance(where, ast.Attribute) else getattr(where, "id", "")) == "urlopen"
            limited = any(keyword.arg in ("timeout", None) for keyword in node.keywords) or \
                (opens and len(node.args) >= 3)
            if (client or opens) and not limited and not _allowed(team, "timeout", path):
                found.append(f"timeout — {path}:{node.lineno} calls another system without a time limit. A slow "
                             "answer then holds this code for ever: pass `timeout=<seconds>`")
        if "silent" in rules and isinstance(node, ast.ExceptHandler) and node.lineno in added:
            quiet = all(isinstance(item, (ast.Pass, ast.Continue)) or (isinstance(item, ast.Expr) and isinstance(
                item.value, ast.Constant)) for item in node.body)
            if quiet and not _allowed(team, "silent", path):
                found.append(f"silent — {path}:{node.lineno} catches an error and does nothing with it. Nobody "
                             "sees the failure in production: log what failed, or let the error rise")
    return found


def examine(team: Team, tree: Path, base: str, changed: list[str]) -> tuple[str, str, list[str]]:
    """The check: (PASS or FAIL, what to do, the notes)."""
    rules = _on(team)
    if not rules:
        return "NOT_NEEDED", "the team turned each rule of [ops] off", []
    skip = team.record_roots + (team.work_dir,)
    files = paths(tree, skip, others=True)
    listed = set(files)
    lines = diff.added(tree, base, [path for path in changed if path in listed])
    new = {path for path in changed if path in listed and not _there(tree, base, path)}
    found: list[str] = []
    if "migration" in rules:
        found += _migrations(team, files, lines, new)
    if "env" in rules:
        found += _env(team, tree, files, lines)
    for path in sorted(lines):
        if core.TEST.search(path):
            continue
        added = {at for at, _text in lines[path]}
        if path.endswith(core.PY) and ("timeout" in rules or "silent" in rules):
            try:
                found += _python(team, path, (tree / path).read_text(encoding="utf-8", errors="replace"), added, rules)
            except OSError:
                pass
        elif path.endswith(core.JS) and "silent" in rules and not _allowed(team, "silent", path):
            found += [f"silent — {path}:{at} catches an error and does nothing with it. Nobody sees the failure in "
                      "production: log what failed, or let the error rise"
                      for at, text in lines[path] if EMPTY_CATCH.search(text)]
    more = f"\n… and {len(found) - SHOWN} more" if len(found) > SHOWN else ""
    return ("FAIL" if found else "PASS"), "\n".join(found[:SHOWN]) + more, []


def _there(tree: Path, commit: str, path: str) -> bool:
    from akasha.repo import git
    return git(tree, "cat-file", "-e", f"{commit}:{path}").returncode == 0
