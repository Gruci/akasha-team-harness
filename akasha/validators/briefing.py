"""Examine the pull request briefing that the agent engine writes.

The briefing is a one-minute text in Simplified Technical English for a reviewer who has the diff. It becomes the body
of the squash commit, so a person who must revert a change later finds the reason, the scope, and the effects fast.
"""

from __future__ import annotations

import re

SECTIONS = ("Why", "What changed", "Scope", "Tradeoffs", "Blast Radius")
OPTIONAL = ("Tradeoffs",)
LIMITS = {"Why": (1, 3, "sentences"), "What changed": (1, 3, "items"), "Scope": (1, 3, "items"),
          "Tradeoffs": (1, 3, "items"), "Blast Radius": (1, 2, "sentences")}
MAX_LINES = 34          # Akasha adds the Verification section, and the commit body must stay under 40 lines
MAX_WORDS = 25          # the STE limit for a descriptive sentence
_ITEM = re.compile(r"^\s*(?:[-*]|\d+\.)\s+")
# A word of hexadecimal characters. Not after a hyphen: a task name ends with eight of them, for example -1f3a9c0b
_SHA = re.compile(r"(?<![\w-])(?=[0-9a-f]*\d)(?=[0-9a-f]*[a-f])[0-9a-f]{7,40}\b")
_HISTORY = re.compile(r"\bbased on (?:origin/)?(?:main|master)\b|\brebased?\b", re.I)


def _sentences(lines: list[str]) -> list[str]:
    text = " ".join(_ITEM.sub("", line).strip() for line in lines if line.strip())
    return [part for part in re.split(r"(?<=[.!?])\s+", re.sub(r"`[^`]*`", "X", text)) if part.strip()]


def examine(text: str) -> list[str]:
    """The problems of the briefing, in simple words. An empty list means that the briefing is correct."""
    problems = []
    lines = text.strip().splitlines()
    if len(lines) > MAX_LINES:
        problems.append(f"the briefing has {len(lines)} lines — use {MAX_LINES} lines or fewer")
    sections: list[tuple[str, list[str]]] = []
    for line in lines:
        if line.startswith("## "):
            sections.append((line[3:].strip(), []))
        elif sections:
            sections[-1][1].append(line)
        elif line.strip():
            problems.append("write no text before the first heading")
        if _ITEM.sub("", line).lstrip().startswith("**"):
            problems.append("use ## headings, not bold lead-ins")
    names = [name for name, _ in sections]
    if "Verification" in names:
        problems.append("remove ## Verification — Akasha writes it from the real results")
    problems += [f"remove the heading ## {name} — use {', '.join(SECTIONS)}"
                 for name in names if name not in SECTIONS and name != "Verification"]
    known = [name for name in names if name in SECTIONS]
    if known != sorted(set(known), key=SECTIONS.index):
        problems.append("put each section one time, in this order: " + ", ".join(SECTIONS))
    problems += [f"add the section ## {name}" for name in SECTIONS if name not in OPTIONAL and name not in names]
    for name, body in sections:
        if name not in LIMITS:
            continue
        low, high, unit = LIMITS[name]
        count = sum(1 for line in body if _ITEM.match(line)) if unit == "items" else len(_sentences(body))
        if not low <= count <= high:
            problems.append(f"## {name} needs {low} to {high} {unit} — it has {count}")
        problems += [f"## {name}: use {MAX_WORDS} words or fewer in this sentence: {sentence[:70]}"
                     for sentence in _sentences(body) if len(re.findall(r"[\w'’-]+", sentence)) > MAX_WORDS]
    if _SHA.search(text):
        problems.append("remove the commit hash — the reader has the diff")
    if _HISTORY.search(text):
        problems.append('remove the branch history, for example "based on main"')
    return list(dict.fromkeys(problems))
