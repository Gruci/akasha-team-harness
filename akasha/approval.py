"""The one decision of a person: the approval of the preview of a task, at the start of the work.

The person approves in their own words, in any language. Two parts make it an approval:

- The hook of the prompt (UserPromptSubmit) keeps the message that the person typed after `akasha preview` showed the
  preview, in the session that showed it, within a day. Only that hook writes it, so the agent engine cannot make
  one up. The hook also runs for prompts that the person did not type, for example the notice of a background task:
  Akasha does not keep those.
- The agent engine reads the message. When it approves the preview as it is, the agent engine runs `akasha approve`,
  which records the approval with the exact words of the person and the digest of the preview that they saw.

When the preview changes after the approval, the task needs a new approval."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from akasha import repo
from akasha.config import STATE_DIR
from akasha.repo import write_whole
from akasha.task import PREVIEW, Task, all_local, digest, record, save

MAX_AGE = 24 * 3600          # a preview that the person saw more than a day ago is shown again before an approval
AUTOMATIC = ("<task-notification>",)
WORDS_KEPT = 200             # the characters of the message that the approval keeps
SESSION = STATE_DIR / "session.json"     # the session of the last Akasha command, as its hook saw it
SESSION_SECONDS = 120


def note_session(root: Path, session: str) -> None:
    """Keep the session of the Akasha command that is about to run. The hook gets it from the agent engine, also after
    /clear and in Codex, where the environment of the command does not tell it."""
    (root / SESSION).parent.mkdir(parents=True, exist_ok=True)
    write_whole(root / SESSION, json.dumps({"session": session, "at": time.time()}))


def session(root: Path) -> str:
    """The session of this Akasha command: the one that its hook kept a moment ago, else the one of Claude Code."""
    try:
        kept = json.loads((root / SESSION).read_text(encoding="utf-8"))
        if time.time() - float(kept["at"]) < SESSION_SECONDS and kept.get("session"):
            return str(kept["session"])
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return os.environ.get("CLAUDE_CODE_SESSION_ID", "")


def waiting(root: Path) -> list[Task]:
    """The tasks on this computer whose preview the person saw in the last day and did not approve yet, the newest
    first."""
    now = time.time()
    found = [task for task in all_local(root)
             if task.status == "preview" and task.shown_at and task.workcopy and now - task.shown_at < MAX_AGE]
    return sorted(found, key=lambda task: -task.shown_at)


def _target(tasks: list[Task], cwd: Path, session: str) -> Task | None:
    """The task that this prompt answers. A preview that a session of Claude Code showed belongs to that session.
    Elsewhere (Codex) the work copy of the session decides, and only when one task waits."""
    mine = [task for task in tasks if task.shown_in and task.shown_in == session]
    if mine:
        return mine[0]
    loose = [task for task in tasks if not task.shown_in]
    here = [task for task in loose if repo.inside(cwd, Path(task.workcopy))] or loose
    return here[0] if len(here) == 1 else None


def on_prompt(root: Path, cwd: Path, prompt: str, session: str = "") -> str:
    """Keep the message of the person for the task whose preview waits in this session, and tell the agent engine what
    to do with it. "" when no task of this session waits for an approval."""
    if not prompt.strip() or prompt.lstrip().startswith(AUTOMATIC):
        return ""
    task = _target(waiting(root), cwd, session)
    if task is None:
        old = [item for item in all_local(root) if item.status == "preview" and session and item.shown_in == session]
        return (f"[AKASHA] The preview of task {old[0].id} is more than a day old. If the person answers it, show it "
                f"again with `akasha preview {old[0].id}` and ask again." if old else "")
    task.heard = {"words": prompt.strip()[:WORDS_KEPT], "at": time.time(), "session": session}
    save(root, task)
    return (f"[AKASHA] Task {task.id} ({task.title}) waits for the approval of its preview. If this message of the "
            f"person approves the preview as it is, in any language and without asking for a change, run `akasha "
            f"approve {task.id}`. If it asks for a change or asks a question, it is feedback: change the preview, show "
            f"it again with `akasha preview {task.id}`, and ask again. When you cannot tell, ask the person. Never "
            "approve for the person.")


def approve(root: Path, task: Task, session: str) -> str:
    """Record the approval from the last message of the person. Return what is missing, or ""."""
    heard = task.heard or {}
    if task.status != "preview" or not task.shown_at:
        return f"task {task.id} does not wait for an approval of its preview"
    if time.time() - task.shown_at > MAX_AGE:
        return f"the person saw the preview more than a day ago. Show it again with `akasha preview {task.id}`"
    if task.shown_in and session != task.shown_in:
        return f"another session showed the preview. Show it here with `akasha preview {task.id}` and ask again"
    # Without a session (the agent engine gave none), the hook kept the message only for the one waiting task
    if not heard or float(heard.get("at") or 0) < task.shown_at or (task.shown_in and heard.get("session") != session):
        return ("the person wrote nothing in this session after the preview was shown. Ask the person in the chat, "
                "and run this command only after their own message approves it")
    now = digest(record(task, PREVIEW))
    if now != task.preview_sha:
        return f"the preview changed after it was shown. Show it again with `akasha preview {task.id}` and ask again"
    task.approval = {"by": repo.person(root), "at": time.strftime("%Y-%m-%d %H:%M"), "preview_sha": now,
                     "words": str(heard.get("words") or ""), "source": "prompt"}
    task.status, task.heard = "approved", {}
    save(root, task)
    return ""
