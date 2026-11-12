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
2. Look at the map before you make code: `akasha map` shows what each area of the product keeps, and `akasha find
   <words>` the code that exists. New code goes into the area that keeps that work. Use the code that is there:
   never write it a second time. A name tells what the code does (`akasha names` shows the rules).
3. Ask the person only what changes the result and what you cannot decide: at most three questions, in simple
   words. Decide the rest and show it in the preview.
4. A value and an expected result come from a source that you read. Never make one up.
5. Only a message that the person types approves. Never approve for the person. When the approved meaning changes,
   show it again.
6. Change files only in the work copy of the task. Run `akasha check`, then `akasha land`. Never merge a pull
   request yourself, never force a push, and never change .docs/state.
7. When a check stops the task, do what its message tells. Never make a check weaker, and never go around it. When
   the task needs a file that only an administrator changes, run `akasha help`."""

ARCHIVE = """\
The records of merged tasks are in the archive ([work] archive). Never read the archive to find how to
do a task: it is no input of a new task, and no work copy holds it. Read one folder of it only when the
person names an earlier task, with `git show origin/<default branch>:<folder>/<file>`."""
