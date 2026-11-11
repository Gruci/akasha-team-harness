"""The core guidance of Akasha for an agent engine, in one place.

The skill of Claude Code, the Akasha block of AGENTS.md (Codex), and the Akasha block of CLAUDE.md are made from this
text, and a test keeps the three the same. What differs between engines is only how a command is written, how the
reviewer is called, and how the words of the person arrive: each instruction tells those in a few lines of its own.
The detail of a step comes from the command of that step, at the moment that it is needed: `akasha start`,
`akasha status`, and the forms that they write."""

from __future__ import annotations

CORE = """\
1. Each change of this repository is an Akasha task. `akasha status` names the next step of your task: do that
   step. Each command prints what to write next, and where.
2. Ask the person only what changes the result and what you cannot decide: at most three questions, in simple
   words. Decide the rest and show it in the preview.
3. Use the code that exists. `akasha start` prints the rules to follow first, then what is near your task and where
   it is; `akasha find <words>` searches it. The list shows the code as it is now. It is not a model: the guides of
   the team, the definitions, and the entries of an area tell which path to use and how to build. A name tells what
   the code does: follow the rules for names that `akasha start` prints (`akasha names` shows each rule).
4. A value and an expected result come from a source that you read. Never make one up.
5. Only a message that the person types approves. Never approve for the person. When the approved meaning changes,
   show it again.
6. Change files only in the work copy of the task. Run `akasha check`, then `akasha land`. Never merge a pull
   request yourself, never force a push, and never change .docs/state.
7. After three failed tries, or when the task needs a file that only an administrator changes, run `akasha help`."""

ARCHIVE = """\
The records of merged tasks are in the archive ([work] archive). Never read the archive to find how to
do a task: it is no input of a new task, and no work copy holds it. Read one folder of it only when the
person names an earlier task, with `git show origin/<default branch>:<folder>/<file>`."""
