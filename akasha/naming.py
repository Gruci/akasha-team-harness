"""The names card: the usual rules for names, and the lines of it that a task needs.

A card that only a command shows depends on the memory of the AI. So `akasha start` and the input of the plan
review give the few lines that fit the languages of the task, with what the names of nearby code tell (codemap.py).
`akasha names` shows the whole card.

The order: what a language, a framework, or an outside API fixes; then the rules of the team and its linter; then
the nearby code, only where one word is usual; then this card. Akasha judges no name and stops no task for a name:
the linter of the team enforces how a name is written, and the reviewer judges what it means (R10)."""

from __future__ import annotations

import posixpath
from pathlib import Path

CARD = Path(__file__).parent / "templates" / "names.md"
# The language of a file, as the card names it
LANGUAGES = {".py": "Python", ".ts": "TypeScript, JavaScript", ".tsx": "TypeScript, JavaScript",
             ".js": "TypeScript, JavaScript", ".jsx": "TypeScript, JavaScript", ".mjs": "TypeScript, JavaScript",
             ".cjs": "TypeScript, JavaScript", ".java": "Java, Kotlin", ".kt": "Java, Kotlin", ".go": "Go",
             ".swift": "Swift", ".c": "C", ".h": "C"}
FRAMEWORKS = {".tsx": "React", ".jsx": "React"}
MEANING = ("a name tells what the code does", "one word for one kind of work in the same area",
           "is_/has_/can_/should_ gives only true or false", "get must find its value, find can give nothing")


def card() -> str:
    return CARD.read_text(encoding="utf-8")


def _entries() -> dict[str, str]:
    """Each list entry of the card by its first words: "Python" -> the rule."""
    found, name = {}, ""
    for line in card().splitlines():
        if line.startswith("- ") and ":" in line:
            name, rule = line[2:].split(":", 1)
            found[name] = rule.strip()
        elif line.startswith("  ") and name:
            found[name] += " " + line.strip()
        else:
            name = ""
    return found


def of_language(language: str) -> str:
    """The card, or only the entries of one language (`akasha names python`)."""
    wanted = language.lower()
    hits = [f"- {name}: {rule}" for name, rule in _entries().items()
            if wanted in [part.strip().lower() for part in name.split(",")]]
    return "\n".join(hits) if hits else card()


def languages(files: list[str]) -> list[str]:
    """The languages and the frameworks of the card that the files are in, the most used first."""
    counts: dict[str, int] = {}
    for path in files:
        extension = posixpath.splitext(path)[1]
        for name in (LANGUAGES.get(extension), FRAMEWORKS.get(extension)):
            if name:
                counts[name] = counts.get(name, 0) + 1
    return sorted(counts, key=lambda name: -counts[name])


def lines(files: list[str]) -> list[str]:
    """The `names` lines of the card for a task that plans these files."""
    entries = _entries()
    found = [f"names — {name}: {entries[name]}" for name in languages(files) if name in entries]
    return found + ["names — " + " · ".join(MEANING) + " · `akasha names` shows each rule"]
