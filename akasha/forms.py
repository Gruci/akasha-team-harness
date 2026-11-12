"""The forms of the records: Akasha writes the frame of a record at the moment that the AI needs it, with how to
fill it, so that the instructions of each session stay short.

The first line of a form is a mark. A file that still has the mark is not written yet: the next step, the preview,
the digest of a review, and the evidence of the server treat it as a file that is not there. The AI fills the file
and deletes the line.

| Form | When | What it holds |
| preview.html | `akasha start` (a full task) | the decisions, the look, the values, and the rules, each with how to fill it |
| plan.md | `akasha approve` (a full task), `akasha start` (a task without a screen, an agent task) | the approach, the steps (steps.py), and the table "Public changes" |
| impact.md | `akasha start --quick` | each changed file, who uses it, and why no other screen changes |

summary.md has no form: its text goes as it is into the pull request and the commit."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

MARK = "<!-- akasha:form — fill this file, then delete this line -->"

PREVIEW = """\
<!doctype html>
<html>
<head><meta charset="utf-8"><title>{title}</title></head>
<body>
<!-- One file, with no link to another file or site. It specifies what to make: the person approves it, and the task
     builds it as it is, words included. The boxes and the marks are the specification, not the screen: the task
     never builds them into the app. Read the files of [guides] preview first. -->

<!-- 1. The decisions, at the very top: a title of one line (what changes), then each question that you asked with
     the answer of the person, one line each, in plain words and never as a quote (this file goes into git). -->
<section id="akasha-decisions">
</section>

<!-- 2. The look. A screen: a mockup with the real words of the screen and the states that matter (empty, loading,
     error), drawn with the parts, the colors, and the controls that the app already has. No screen: a diagram of
     the flow, and a table of the result before and after. -->
<main>
</main>

<!-- 3. The values. Never make up a value that comes from data: read the source first. Mark each such value of the
     look with data-akasha-value="KEY", and give it one row here: where it comes from, how the source becomes the
     value, its value now with the time that you read it, and the query or the command that gives it again.{definition} -->
<section id="akasha-data"><table>
<!-- <tr data-akasha-key="KEY"{named}><td data-akasha-field="source"></td><td data-akasha-field="formula"></td>
     <td data-akasha-field="value"></td><td data-akasha-field="check"></td></tr> -->
</table></section>

<!-- 4. The rules: one row for each behavior that the person can notice (who sees it, a filter, an order, no data, a
     wrong entry), with one real case that a test can check as it is. data-akasha-from="person" marks a rule that
     the person decided in an answer, "ai" a rule that you propose: show which is which on the page. -->
<section id="akasha-rules"><table>
<!-- <tr data-akasha-rule="KEY" data-akasha-from="person|ai"><td data-akasha-field="when"></td>
     <td data-akasha-field="then"></td><td data-akasha-field="example"></td></tr> -->
</table></section>

<!-- The words of this file are the words of the product. Follow the rules for words of [guides] preview first. Write
     in the language of the person and in the tone of the screens of the team. One name for one thing in the whole
     file{words}. One fact in a sentence, no filler, no praise. A label names what the person gets, not what the code
     does. A number has its unit and its date. Hide personal data. Then delete these comments that you do not
     need, and run `akasha preview {task}`. -->
</body>
</html>
"""

PLAN = """\
# Plan

<!-- The plan is a work order. An AI that never saw this conversation builds from this file alone, so write what it
     must know: where the code is, what to call, and what each step makes. It keeps each rule and each value of what
     the person approved, also the ones that you proposed. No "TBD". Read the files of [guides] plan first. -->

## Approach

<!-- A few lines: what the change does and why this way. Then the facts that the steps stand on, each with its file
     and line: how the code and the data work now, each caller and reader of what will change, and what `akasha map`
     and `akasha find <words>` showed of code that exists. Use that code: do not write it a second time. -->

## Steps

<!-- The work in the order to build it. One step is small enough for one go. Akasha reads `files`, `rules`, and
     `tests` (the check `scope`): each file of code that the task changes is in a step, and each rule of the preview
     is in a step. A test file needs no step. Nobody marks a step as done: Akasha sees it in the change.

     ### S1 <what the step makes>
     - files: `path/of/file.py`, `path/of/other.py`
     - uses: `existing_name(arguments)` in path/of/it.py:44, and what it gives
     - rules: the keys of the rules and the values of the preview that this step builds
     - tests: `path/of/test_file.py`, with the example of the preview as the expected value
     - done when: what shows that the step is complete -->

## Public changes

<!-- One row for each of these, and no row when none applies. `akasha check` tells when a row is missing.
     different | path::name | a new public name that the repository has already, with another meaning: the difference
     wraps     | path::name | it calls the existing code: what it adds
     replaces  | path::name | it takes the place of the existing code: when that one goes
     change    | path or key | a change of registered code or of a definition: what stays the same for its users
     entry     | path::name, or GET /address | a new public entry without a definition: why it has no business meaning -->
| Change | Where | Note |
|:--|:--|:--|

## Risks

<!-- What can break in another area or after the deployment, and what the plan does against it: each other caller of
     what changes, a change of data, a new setting of the server. -->

## Undo

<!-- Only when `git revert` is not enough: what else to do. Else delete this part. -->

## Steps of an administrator

<!-- Each step that only an administrator can do, for example a new secret value on the server. summary.md repeats
     them. Else delete this part. -->
"""

IMPACT = """\
# Impact

<!-- One line for each changed file: who uses it (which screens, which code), and why no other screen changes. The
     reviewer reads this with the change itself. -->
"""


def is_form(data: bytes | str | None) -> bool:
    """True for the text of a form that nobody filled: its first line is the mark."""
    if data is None:
        return False
    text = data.decode("utf-8", errors="replace") if isinstance(data, bytes) else data
    return text.lstrip("﻿ \t\r\n").startswith(MARK)


def written(path: Path) -> bool:
    """True when the record is there and is no form that still waits."""
    try:
        with path.open("rb") as file:
            return not is_form(file.read(len(MARK.encode("utf-8")) + 16))
    except OSError:
        return False


def put(path: Path, text: str) -> bool:
    """Write a form where no file is. True when it wrote one."""
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{MARK}\n{text}", encoding="utf-8")
    return True


def preview(title: str, task: str, definitions_on: bool = False, words: Iterable[tuple[str, tuple[str, ...]]] = ()) -> str:
    """The form of a preview. With the definitions on, a value row names its definition, and the form names the main
    word and the other words of each definition that the task touches."""
    named = [f"{label} ({', '.join(aliases)})" if aliases else label for label, aliases in words]
    return PREVIEW.format(
        title=title.replace("<", "&lt;"), task=task,
        definition=(" Each row names its definition: the key of akasha.definitions.toml, a new key that this task "
                    "adds, or \"local\" for a value of this screen only." if definitions_on else ""),
        named=' data-akasha-definition="KEY-OR-local"' if definitions_on else "",
        words=(f"; the main word of each definition, and its other words where a button or a title needs them: "
               f"{'; '.join(named)}" if named else ""))
