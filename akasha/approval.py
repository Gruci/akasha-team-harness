"""The one decision of a person: the approval of the preview of a task, at the start of the work.

The hook of the prompt of the person (UserPromptSubmit) records it. Claude Code and Codex run that hook only for what
the person sends, so the agent engine cannot make an approval: it can only show the preview and ask. The approval
holds the digest of the preview that the person saw. When the preview changes after the approval, the task needs a
new approval."""

from __future__ import annotations

import re
import time
from pathlib import Path

from akasha import repo
from akasha.task import PREVIEW, Task, all_local, digest, record, save

APPROVE = ("승인", "좋아", "좋습니다", "좋네", "진행", "오케이", "ㅇㅋ", "괜찮", "ok", "okay", "approve", "approved",
           "lgtm", "go ahead", "looks good", "ship it", "sounds good")
SHORT_YES = ("네", "예", "응", "ㅇㅇ", "yes", "yep", "y", "그래", "그래요", "좋아요")
REFUSE = ("말고", "아니", "안돼", "안 돼", "수정", "고쳐", "바꿔", "빼고", "다시", "추가", "대신", "근데", "그런데", "하지만",
          "그러나", "no", "not", "don't", "dont", "change", "fix", "but", "instead", "?")
MAX_LENGTH = 40              # a longer message is feedback, not an approval


def is_approval(text: str) -> bool:
    """True for a short message that approves and does not ask for a change, for example "승인" or "ok, go ahead"."""
    words = text.strip().lower()
    if not words or len(words) > MAX_LENGTH:
        return False
    if any(item in words for item in REFUSE):
        return False
    plain = re.sub(r"[\s.!~,]+", " ", words).strip()
    return plain in SHORT_YES or any(item in words for item in APPROVE)


def waiting(root: Path) -> list[Task]:
    """The tasks on this computer whose preview the person saw and did not approve yet, the newest first."""
    found = [task for task in all_local(root) if task.status == "preview" and task.shown_at and task.workcopy]
    return sorted(found, key=lambda task: -task.shown_at)


def _target(tasks: list[Task], cwd: Path) -> Task | None:
    here = [task for task in tasks if repo.inside(cwd, Path(task.workcopy))]
    return (here or tasks or [None])[0]


def on_prompt(root: Path, cwd: Path, prompt: str) -> str:
    """Record an approval in the prompt of the person, and tell the agent engine what happens next. "" when no task
    waits for an approval."""
    task = _target(waiting(root), cwd)
    if task is None:
        return ""
    if not is_approval(prompt):
        return (f"[AKASHA] Task {task.id} ({task.title}) waits for the approval of its preview. Read this message as "
                f"feedback on the preview: change the preview, show it again with `akasha preview {task.id}`, and ask "
                "the person again. Only the person approves.")
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
