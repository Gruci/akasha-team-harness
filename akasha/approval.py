"""The one decision of a person: the approval of the preview of a task, at the start of the work.

The hook of the prompt of the person (UserPromptSubmit) records it. That hook also runs for prompts that the person did
not type, for example the notice of a background task or a scheduled prompt. So only a whole message from a short
closed list approves, and only in the session that showed the preview, within a day. The approval holds the digest of
the preview that the person saw: when the preview changes after the approval, the task needs a new approval."""

from __future__ import annotations

import re
import time
from pathlib import Path

from akasha import repo
from akasha.task import PREVIEW, Task, all_local, digest, record, save

# A whole message, without spaces, marks, and a polite end, is an approval only when it is in this list
WORDS = frozenset((
    "승인", "승인합", "승인해", "승인해주세", "네", "넵", "넹", "네네", "예", "응", "ㅇㅇ", "ㅇㅋ", "오케이", "좋아", "좋습",
    "진행", "진행해", "진행해주세", "이대로진행", "이대로진행해", "이대로진행해주세", "그대로진행", "그대로진행해",
    "그대로진행해주세", "그대로해주세", "그렇게해주세", "좋아진행해", "좋아진행", "ok", "okay", "okgoahead", "yes", "lgtm",
    "goahead", "approve", "approved", "shipit"))
_MARKS = re.compile(r"[\s.!~,]+|[\U0001F300-\U0001FAFF☀-➿]+")
_POLITE = re.compile(r"(?:요|니다)$")
MAX_AGE = 24 * 3600          # an approval of a preview that the person saw more than a day ago does not count
SHORT = 15                   # a short message that is not an approval can be a "yes" in other words
AUTOMATIC = ("<task-notification>",)


def is_approval(text: str) -> bool:
    """True when the whole message approves, for example "승인", "넵", or "ok, go ahead". A message that also asks
    for something, for example "좋아요, 표는 아래로", is feedback."""
    words = _POLITE.sub("", _MARKS.sub("", text.strip().lower()))
    return words in WORDS


def waiting(root: Path) -> list[Task]:
    """The tasks on this computer whose preview the person saw in the last day and did not approve yet, the newest
    first."""
    now = time.time()
    found = [task for task in all_local(root)
             if task.status == "preview" and task.shown_at and task.workcopy and now - task.shown_at < MAX_AGE]
    return sorted(found, key=lambda task: -task.shown_at)


def _target(tasks: list[Task], cwd: Path, session: str) -> tuple[Task | None, str]:
    """The task that this prompt answers, or a note why Akasha cannot tell. A preview that a session of Claude Code
    showed belongs to that session. Elsewhere (Codex) the work copy of the session decides, and only one task can
    wait."""
    mine = [task for task in tasks if task.shown_in and task.shown_in == session]
    if mine:
        return mine[0], ""
    loose = [task for task in tasks if not task.shown_in]
    here = [task for task in loose if repo.inside(cwd, Path(task.workcopy))] or loose
    if len(here) == 1:
        return here[0], ""
    if not tasks:
        return None, ""
    names = ", ".join(task.id for task in tasks[:3])
    return None, (f"[AKASHA] The person approved, but Akasha cannot tell which preview: task {names} waits for an "
                  "approval, and this session did not show it. Show the preview here with `akasha preview <task>` "
                  "and ask again.")


def on_prompt(root: Path, cwd: Path, prompt: str, session: str = "") -> str:
    """Record an approval in the prompt of the person, and tell the agent engine what happens next. "" when no task
    of this session waits for an approval."""
    if prompt.lstrip().startswith(AUTOMATIC):
        return ""
    task, note = _target(waiting(root), cwd, session)
    approves = is_approval(prompt)
    if task is None:
        return note if approves else ""
    if not approves:
        hint = (" If the person meant yes in other words, ask them to answer '승인'; do not change the preview."
                if len(prompt.strip()) <= SHORT else "")
        return (f"[AKASHA] Task {task.id} ({task.title}) waits for the approval of its preview. Read this message as "
                f"feedback on the preview: change the preview, show it again with `akasha preview {task.id}`, and ask "
                f"the person again. Only the person approves.{hint}")
    now = digest(record(task, PREVIEW))
    if now != task.preview_sha:
        return (f"[AKASHA] The person approved, but the preview of task {task.id} changed after `akasha preview` "
                f"showed it. Show the current preview with `akasha preview {task.id}` and ask again.")
    task.approval = {"by": repo.person(root), "at": time.strftime("%Y-%m-%d %H:%M"), "preview_sha": now,
                     "words": prompt.strip()[:80], "source": "prompt"}
    task.status = "approved"
    save(root, task)
    return (f"[AKASHA] {task.approval['by']} approved the preview of task {task.id} ({task.title}). Do not ask the "
            "person anything more unless the plan must change what they approved. Next, without stopping: write "
            "research.md and plan.md in the records folder of the task, ask the akasha-reviewer agent to review the "
            "plan until it passes, then build, run `akasha check`, write summary.md, and run `akasha land`.")
