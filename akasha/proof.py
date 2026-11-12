"""The proof of a task: each rule and each value that the person approved has a test.

The preview names its rules and its values by a key (spec.py). A test tells which one it proves, in a comment:

    # akasha: rule=csv-filter
    def test_the_csv_keeps_the_filter(): ...

    // akasha: value=total-amount, rule=empty-list

The check `proof` fails for each key of the preview without such a mark in a test file of the work copy. It sees
that the test is there. The checks of the team run it, and the reviewer of the result judges that it proves the rule:
its expected value is the example of the preview, not what the new code gives.

A task without a preview has no keys, so the check is NOT_NEEDED: a quick task, an agent task, and a task without a
screen. To add a test never needs a new approval: a test changes nothing that the person approved."""

from __future__ import annotations

import posixpath
import re
from pathlib import Path

from akasha import core, spec
from akasha.repo import _without, git

CHECK = "proof"
MARK = re.compile(r"akasha:\s*((?:rule|value)\s*=\s*[\w.\-]+(?:\s*,\s*(?:rule|value)\s*=\s*[\w.\-]+)*)", re.I)
PAIR = re.compile(r"(rule|value)\s*=\s*([\w.\-]+)", re.I)
SHOWN = 8


def keys(preview: str) -> tuple[list[str], list[str]]:
    """The keys of the rules and of the values of a preview."""
    text = spec.plain(preview)
    body = spec._box(text, "rules")
    return (list(spec._rows(body, "data-akasha-rule")) if body is not None else []), spec.shown(text)


def is_test(path: str) -> bool:
    """A test file of any language: a path that the import graph leaves out as a test, or a file name with test or
    spec in it (OrderTest.java, order_test.go)."""
    return bool(core.TEST.search(path)) or bool(re.search(r"(?i)(test|spec)", posixpath.basename(path)))


def marks(tree: Path, skip: tuple[str, ...] = ()) -> dict[tuple[str, str], list[str]]:
    """(kind, key) -> the test files of the work copy that carry its mark. New files that git does not track count
    too; the records of the tasks do not."""
    done = git(tree, "-c", "core.quotePath=false", "grep", "-n", "-I", "--untracked", "-i", "-e", "akasha:",
               *_without(skip))
    found: dict[tuple[str, str], list[str]] = {}
    for line in done.stdout.splitlines():
        path, _, rest = line.partition(":")
        if not is_test(path):
            continue
        for said in MARK.findall(rest):
            for kind, key in PAIR.findall(said):
                files = found.setdefault((kind.lower(), key), [])
                if path not in files:
                    files.append(path)
    return found


def examine(tree: Path, preview: str | None, skip: tuple[str, ...] = ()) -> tuple[str, str, list[str]]:
    """The check: (PASS, FAIL, or NOT_NEEDED, what to do, the notes). `preview`: the text of preview.html of the
    task, or None for a task without one. `skip`: the folders of the records."""
    if preview is None:
        return "NOT_NEEDED", "the task has no preview, so no rule and no value has a key", []
    rules, values = keys(preview)
    if not rules and not values:
        return "NOT_NEEDED", "the preview names no rule and no value", []
    found = marks(tree, skip)
    missing = [f"rule={key}" for key in rules if ("rule", key) not in found] + \
        [f"value={key}" for key in values if ("value", key) not in found]
    if not missing:
        return "PASS", "", []
    more = f" … and {len(missing) - SHOWN} more" if len(missing) > SHOWN else ""
    return "FAIL", (f"no test proves {', '.join(missing[:SHOWN])}{more}. Write a test for each one, with the example "
                    "of the preview as its expected value, and put the mark in a comment of the test: `akasha: "
                    f"{missing[0]}`. To add a test needs no new approval"), []
