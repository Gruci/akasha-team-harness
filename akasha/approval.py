"""The one decision of a person: the approval of the preview of a task, at the start of the work.

The person approves in their own words, in any language. Two parts make it an approval:

- The hook of the prompt (UserPromptSubmit) keeps the message that the person typed after `akasha preview` showed the
  preview, in the session that showed it, within a day. Only that hook writes it, so the agent engine cannot make
  one up. The hook also runs for prompts that the person did not type, for example the notice of a background task:
  Akasha does not keep those.
- The agent engine reads the message. When it approves the preview as it is, the agent engine runs `akasha approve`,
  which records the approval with the exact words of the person and the digest of the preview that they saw.

When the preview changes after the approval, the task needs a new approval.

An agent task (agent.py) has no preview: the person approves its result before the merge, in the same way. The
approval holds the digest of the change and of summary.md, and the relay can name the person on the first line of the
prompt: `[akasha-from: <name>]`.

A task without a screen (screen.py) of an administrator has no preview either: the person approves its plan after the
review, and the approval holds the digest of plan.md."""

from __future__ import annotations

import json
import os
import re
import shlex
import sys
import time
from pathlib import Path

from akasha import repo, screen
from akasha.config import STATE_DIR
from akasha.repo import write_whole
from akasha.task import PREVIEW, Task, all_local, digest, record, save

MAX_AGE = 24 * 3600          # a preview that the person saw more than a day ago is shown again before an approval
# Prompts that no person typed. Claude Code sends the hook of the prompt for them too: the notice of a background
# task, and the report of a subagent (`<agent-message from="…">`, measured with Claude Code 2.1.322). A prompt
# that starts with a tag of this form is never the words of a person: a report of a subagent after a preview
# would else approve it
AUTOMATIC = ("<task-notification", "<agent-message", "<system-reminder", "<local-command", "<command-",
             "<bash-", "<user-prompt-submit-hook")
CALLS = STATE_DIR / "calls.json"         # the Akasha commands that the hooks let through, each with its session
WORDS_KEPT = 200             # the characters of the message that the approval keeps
SESSION = STATE_DIR / "session.json"     # the session of the last Akasha command, as its hook saw it
SESSION_SECONDS = 120
# The relay of an agent session names the person whose words the prompt carries. Only the relay writes prompts
FROM = re.compile(r"^\[akasha-from:\s*([^\]\n]{1,80}?)\s*\]")


def _calls(root: Path) -> list[dict]:
    try:
        found = json.loads((root / CALLS).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    now = time.time()
    return [item for item in found if isinstance(item, dict) and now - float(item.get("at") or 0) < SESSION_SECONDS] \
        if isinstance(found, list) else []


def note_session(root: Path, session: str, line: str) -> None:
    """Keep the session of the Akasha command `line` that is about to run. The hook gets it from the agent engine,
    also after /clear and in Codex, where the environment of the command does not tell it. Each call has its own
    entry: two sessions that run commands at the same time do not write over each other."""
    try:
        words = shlex.split(line)
    except ValueError:
        return
    (root / CALLS).parent.mkdir(parents=True, exist_ok=True)
    write_whole(root / CALLS, json.dumps(_calls(root) + [{"session": session, "at": time.time(), "words": words}]))


def session(root: Path, sure: bool = False) -> str:
    """The session of this Akasha command: the one that its hook kept a moment ago for this very command line, else
    the one of Claude Code. Another session can run an Akasha command at the same time, so the words must match.

    `sure`: for a command that changes which session holds a task. When two sessions ran the same command line
    within the same moment, Akasha cannot tell which one this is: the answer is "" (the session is not known),
    never the later one."""
    mine = sys.argv[1:]
    calls = _calls(root)
    fits = [item for item in calls if mine and item.get("session") and list(item.get("words") or [])[-len(mine):] == mine]
    if fits:
        if sure and len({item["session"] for item in fits}) > 1:
            return ""
        taken = fits[0]                               # once: a later command has its own entry
        try:
            write_whole(root / CALLS, json.dumps([item for item in calls if item is not taken]))
        except OSError:
            pass
        return str(taken["session"])
    return os.environ.get("CLAUDE_CODE_SESSION_ID", "")


def _wanted(task: Task) -> str:
    """The status of a task that waits for the person: the preview, or the result of an agent task (agent.py)."""
    return "landing" if task.kind == "agent" else "preview"


def waiting(root: Path) -> list[Task]:
    """The tasks on this computer whose preview (or result) the person saw in the last day and did not approve yet,
    the newest first."""
    now = time.time()
    found = [task for task in all_local(root)
             if task.status == _wanted(task) and task.shown_at and task.workcopy and now - task.shown_at < MAX_AGE]
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
        old = [item for item in all_local(root) if item.status == _wanted(item) and session and item.shown_in == session]
        if not old:
            return ""
        what, again = shown(old[0])
        return (f"[AKASHA] The {what} of task {old[0].id} is more than a day old. If the person answers it, show it "
                f"again with `{again}` and ask again.")
    named = FROM.match(prompt.strip())
    task.heard = {"words": prompt.strip()[:WORDS_KEPT], "at": time.time(), "session": session,
                  **({"from": named.group(1)} if named else {})}
    save(root, task)
    if task.kind == "agent":
        return (f"[AKASHA] Task {task.id} ({task.title}) waits for the approval of its result before the merge. If "
                f"this message of the person approves the result as it is, in any language and without asking for a "
                f"change, run `akasha approve {task.id}`, then `akasha land {task.id} --wait 540`. If it asks for a "
                f"change or asks a question, it is feedback: change the work, run `akasha check {task.id}`, and land "
                "again, which asks the person again. When you cannot tell, ask the person in your answer. Never "
                "approve for the person.")
    if screen.is_no_screen(task):
        return (f"[AKASHA] Task {task.id} ({task.title}) waits for the approval of its plan. If this message of the "
                f"person approves the plan as it is, in any language and without asking for a change, run `akasha "
                f"approve {task.id}`. If it asks for a change or asks a question, it is feedback: change the plan, ask "
                f"the akasha-reviewer agent again, show it again with `akasha preview {task.id}`, and ask again. When "
                "you cannot tell, ask the person. Never approve for the person.")
    return (f"[AKASHA] Task {task.id} ({task.title}) waits for the approval of its preview. If this message of the "
            f"person approves the preview as it is, in any language and without asking for a change, run `akasha "
            f"approve {task.id}`. If it asks for a change or asks a question, it is feedback: change the preview, show "
            f"it again with `akasha preview {task.id}`, and ask again. When you cannot tell, ask the person. Never "
            "approve for the person.")


def shown(task: Task) -> tuple[str, str]:
    """What the person approves, and the command that shows it again."""
    if task.kind == "agent":
        return "result", f"akasha result {task.id}"
    if screen.is_no_screen(task):
        return "plan", f"akasha preview {task.id}"
    return "preview", f"akasha preview {task.id}"


def approve(root: Path, task: Task, session: str, current: str = "", typed: bool = False) -> str:
    """Record the approval from the last message of the person. `current` is the digest of what the person approves
    now: the result of an agent task, the plan of a task without a screen, else the preview file. Return what is
    missing, or "". `typed`: the person approved in their own terminal (`akasha approve <task> --here`), where no
    hook keeps a message: the conditions of the kept message and of the session do not hold, and the others do:
    the preview was shown, within a day, and it is the same now."""
    heard = task.heard or {}
    what, again = shown(task)
    if task.status != _wanted(task) or not task.shown_at:
        return f"task {task.id} does not wait for an approval of its {what}"
    if time.time() - task.shown_at > MAX_AGE:
        return f"the person saw the {what} more than a day ago. Show it again with `{again}`"
    if task.shown_in and session != task.shown_in and not typed:
        return f"another session showed the {what}. Show it here with `{again}` and ask again"
    # Without a session (the agent engine gave none), the hook kept the message only for the one waiting task
    if not typed and (not heard or float(heard.get("at") or 0) < task.shown_at
                      or (task.shown_in and heard.get("session") != session)):
        return (f"the person wrote nothing in this session after the {what} was shown. Ask the person in the chat, "
                "and run this command only after their own message approves it")
    now = current or digest(record(task, PREVIEW))
    if now != task.preview_sha:
        return f"the {what} changed after it was shown. Show it again with `{again}` and ask again"
    me, words, at = repo.person(root), str(heard.get("words") or ""), time.strftime("%Y-%m-%d %H:%M")
    if typed:
        heard, words = {}, ""
    if task.kind == "agent":
        # The landing merges next, so the task stays in landing
        task.approval = {"by": str(heard.get("from") or me), "through": me, "at": at, "change_sha": now,
                         "words": words, "source": "result"}
    elif screen.is_no_screen(task):
        task.approval = {"by": me, "at": at, "plan_sha": now, "words": words, "source": "plan"}
        task.status = "approved"
    else:
        task.approval = {"by": me, "at": at, "preview_sha": now, "words": words, "source": "prompt"}
        task.status = "approved"
    if typed:                                         # the record tells how the person approved
        task.approval["source"] = "terminal" if task.kind in ("full", "quick") else task.approval["source"]
        task.approval["typed"] = True
    task.heard = {}
    save(root, task)
    return ""
