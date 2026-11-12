"""The lines that a change adds. The checks of the product (sheets.py, ops.py, size.py) look only at what a change
makes new, so that a repository with old code can turn each rule on."""

from __future__ import annotations

import re
from pathlib import Path

from akasha.repo import git

HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")


def added(tree: Path, base: str, paths: list[str]) -> dict[str, list[tuple[int, str]]]:
    """path -> the lines that the work copy has and the base commit does not: (line number, text). One process of
    git reads each file. A binary file has no lines."""
    if not paths:
        return {}
    done = git(tree, "-c", "core.quotePath=false", "diff", "-U0", "--no-renames", "--no-color", base, "--", *paths)
    if done.returncode:
        raise RuntimeError(f"git diff failed: {done.stderr.strip()[:300]}")
    found: dict[str, list[tuple[int, str]]] = {}
    path, at = "", 0
    for line in done.stdout.splitlines():
        if line.startswith("+++ "):
            path = line[6:] if line.startswith("+++ b/") else ""
            continue
        hunk = HUNK.match(line)
        if hunk:
            at = int(hunk.group(1))
        elif path and line.startswith("+"):
            found.setdefault(path, []).append((at, line[1:]))
            at += 1
    return found


def counts(tree: Path, base: str, renames: bool = False) -> dict[str, tuple[int, int]]:
    """path -> (added lines, deleted lines) of each file that the work copy changed since the base commit. A binary
    file counts as (0, 0). `renames`: a file that moved counts only the lines that changed in it, under its new
    path."""
    done = git(tree, "-c", "core.quotePath=false", "diff", "--numstat", "-z", "-M" if renames else "--no-renames", base)
    if done.returncode:
        raise RuntimeError(f"git diff failed: {done.stderr.strip()[:300]}")
    found = {}
    items = done.stdout.split("\0")
    at = 0
    while at < len(items):
        parts = items[at].split("\t")
        at += 1
        if len(parts) != 3:
            continue
        path = parts[2]
        if not path and at + 1 < len(items):          # a move: the old path and the new path follow
            path, at = items[at + 1], at + 2
        found[path] = (int(parts[0]) if parts[0].isdigit() else 0, int(parts[1]) if parts[1].isdigit() else 0)
    return found
