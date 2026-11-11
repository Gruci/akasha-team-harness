"""The specification in a preview: the values of the screen and the rules of the screen, which the person approves
with the mockup. The person checks the specification and does not dictate it: the AI asks only what changes the
result and what it cannot decide, and proposes the rest.

A value of the screen that comes from data carries data-akasha-value="<key>". The box <section id="akasha-data"> has
one row <tr data-akasha-key="<key>"> for each key, with the cells data-akasha-field="source" (where it comes from),
"formula" (how it is computed from the source), "value" (its value now, as the source gives it), and "check" (the
query or the command that gives it again).

The box <section id="akasha-rules"> has one row <tr data-akasha-rule="<key>" data-akasha-from="person|ai"> for each
rule that the person can notice, with the cells data-akasha-field="when", "then", and "example" (one case that a test
can check). "person" marks a rule that the person decided in an answer, "ai" a rule that the AI proposes.

The boxes and the marks are the specification: they are not part of the screen that the task builds. The approval
holds the whole preview, so it holds the specification; the reviewer and the tests keep it."""

from __future__ import annotations

import re

VALUE_FIELDS = ("source", "formula", "value", "check")
RULE_FIELDS = ("when", "then", "example")
_VALUE = re.compile(r'\bdata-akasha-value="([^"]+)"', re.I)
_FIELD = re.compile(r'<td\b[^>]*\bdata-akasha-field="([a-z]+)"[^>]*>(.*?)</td>', re.I | re.S)
_FROM = re.compile(r'\bdata-akasha-from="(person|ai)"', re.I)
_TAG = re.compile(r"<[^>]+>")
_COMMENT = re.compile(r"<!--.*?-->", re.S)


def plain(text: str) -> str:
    """The page without its HTML comments: a row that a comment shows as an example is no row of the page."""
    return _COMMENT.sub("", text)


def _box(text: str, name: str) -> str | None:
    """The inside of the box <section id="akasha-<name>">, or None without it."""
    found = re.search(rf'<section\b[^>]*\bid="akasha-{name}"[^>]*>(.*?)</section>', text, re.I | re.S)
    return found.group(1) if found else None


def _rows(body: str, attribute: str) -> dict[str, dict[str, str]]:
    """The rows of a box: key -> field -> the visible text of its cell. The key "from" holds who decided the row
    (person or ai), from the attribute data-akasha-from of the row."""
    found = {}
    for attributes, key, row in re.findall(rf'<tr\b([^>]*\b{attribute}="([^"]+)"[^>]*)>(.*?)</tr>', body,
                                           re.I | re.S):
        cells = {name.lower(): _TAG.sub(" ", cell).strip() for name, cell in _FIELD.findall(row)}
        decided = _FROM.search(attributes)
        found[key] = {**cells, **({"from": decided.group(1).lower()} if decided else {})}
    return found


def _empty(rows: dict[str, dict[str, str]], fields: tuple[str, ...]) -> list[str]:
    return [f"{key}: the row has no {', '.join(missing)}" for key, cells in rows.items()
            if (missing := [name for name in fields if not cells.get(name)])]


def shown(text: str) -> list[str]:
    """The keys of the values that the preview marks, in their order."""
    return list(dict.fromkeys(_VALUE.findall(plain(text))))


def value_problems(text: str, required: bool = False) -> list[str]:
    """Why the values of the preview are not defined, or []. `required`: the task changes files that make data
    ([preview] data), so the preview must mark one value or more."""
    text = plain(text)
    keys = shown(text)
    if not keys:
        return (['the task changes files that make data, and the preview marks no value. Put data-akasha-value="<key>" '
                 "on each value of the screen that comes from data, and define it in the box of the values"]
                if required else [])
    body = _box(text, "data")
    if body is None:
        return [f'the preview shows {", ".join(keys[:3])} without the box of the values: add <section '
                'id="akasha-data"> with one row <tr data-akasha-key="<key>"> for each value, with the cells '
                'data-akasha-field="source", "formula", "value", and "check"']
    rows = _rows(body, "data-akasha-key")
    return [f"{key}: no row in the box of the values" for key in keys if key not in rows] + \
        _empty({key: rows[key] for key in keys if key in rows}, VALUE_FIELDS)


def rule_problems(text: str) -> list[str]:
    """Why the rules of the preview are missing, or []: one rule or more, each with when, then, an example, and who
    decided it (the person, or the AI that proposes it)."""
    body = _box(plain(text), "rules")
    rows = _rows(body, "data-akasha-rule") if body is not None else {}
    if not rows:
        return ['the preview has no rule: add <section id="akasha-rules"> with one row <tr data-akasha-rule="<key>" '
                'data-akasha-from="person|ai"> for each rule that the person can notice, with the cells '
                'data-akasha-field="when", "then", and "example"']
    unmarked = [f'{key}: the rule does not tell who decided it (data-akasha-from="person" or "ai")'
                for key, cells in rows.items() if "from" not in cells]
    return _empty(rows, RULE_FIELDS) + unmarked


def problems(text: str, data_required: bool = False) -> list[str]:
    """Why the preview does not specify the change yet, or []."""
    return rule_problems(text) + value_problems(text, data_required)
