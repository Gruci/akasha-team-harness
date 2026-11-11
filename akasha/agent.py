"""An agent task: an agent account ([team] agents) works from the request of a person, without a preview.

A teammate decides what to make at the start, on a preview. An agent account has no person in its session: a program
(the relay) runs the session, gives it the request of a person as a prompt, and sends the answers of the session to
that person. So the request decides what to make, and the person decides once at the end, on the result:

- The hook of the prompt (UserPromptSubmit) keeps each prompt of an agent session. Only the relay writes prompts, so
  the agent engine cannot make one up. `akasha start` writes the prompt of the last ten minutes of the session into
  request.md, word for word: the request takes the place of the preview.
- The plan, the review of the plan, the build, and the checks are as for each task.
- After the checks of GitHub pass, the landing stops with ASK. `akasha result` gives the text for the person: the
  summary, a link to the change at fixed commits, and the changed files. The answer of the person is the next prompt,
  and `akasha approve` records it with the digest of the change and of summary.md. A later change needs a new
  approval.

Akasha trusts the relay to give only the words of a person as prompts. The relay also keeps the keys and the last word
on the merge: the hooks keep a cooperative agent engine on the procedure, and they are not a sandbox."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

from akasha import approval, quick, repo
from akasha.config import STATE_DIR, Team
from akasha.repo import write_whole
from akasha.task import SUMMARY, Task, own_records, record, records

REQUEST = "request.md"
PROMPT = STATE_DIR / "prompt.json"     # the last prompt of an agent session, as its hook saw it
KEEP_SECONDS = 600                     # akasha start takes a prompt of the last ten minutes
WORDS_KEPT = 8000
FILES_SHOWN = 15


def is_agent(task: Task) -> bool:
    return task.kind == "agent"


def account(team: Team, me: str) -> bool:
    """True when this GitHub name is an agent account."""
    return bool(me) and me in team.agents


def keep_prompt(root: Path, session: str, prompt: str) -> None:
    """Keep the prompt of an agent session for `akasha start`. A notice of a background task is no request."""
    if not prompt.strip() or prompt.lstrip().startswith(approval.AUTOMATIC):
        return
    (root / PROMPT).parent.mkdir(parents=True, exist_ok=True)
    write_whole(root / PROMPT, json.dumps({"session": session, "at": time.time(),
                                           "words": prompt.strip()[:WORDS_KEPT]}, ensure_ascii=False))


def kept_request(root: Path, session: str) -> str:
    """The request of the person: the last prompt of this session in the last ten minutes, or ""."""
    try:
        kept = json.loads((root / PROMPT).read_text(encoding="utf-8"))
        fresh = time.time() - float(kept.get("at") or 0) < KEEP_SECONDS
    except (OSError, ValueError, TypeError, AttributeError):
        return ""
    same = not session or kept.get("session") == session
    return str(kept.get("words") or "") if fresh and same else ""


def write_request(task: Task, text: str) -> None:
    path = record(task, REQUEST)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# Request\n\n{text.strip()}\n", encoding="utf-8")


def digest(task: Task) -> str:
    """The digest of the change of the task and of summary.md, or "" before summary.md. The approval holds it. The
    change starts where the task meets the default branch, so a merge of the default branch keeps it."""
    note = record(task, SUMMARY)
    if not task.workcopy or not note.is_file():
        return ""
    tree = Path(task.workcopy)
    change = quick._diff(tree, quick.base(tree), own_records(task))
    text = note.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n")
    return hashlib.sha256(f"{change}\n--- summary.md ---\n{text}".encode()).hexdigest()[:12]


def link(root: Path, task: Task) -> str:
    """The address of the change on GitHub between two fixed commits, or "" without GitHub. A later push does not
    change what it shows, unlike the page of the pull request."""
    tree, slug = Path(task.workcopy), repo.origin(root)
    head = repo.git(tree, "rev-parse", "HEAD").stdout.strip()
    return f"https://github.com/{slug}/compare/{quick.base(tree)}...{head}" if slug and head else ""


def missing(task: Task) -> str:
    """What an agent task still needs before the merge, or ""."""
    now = digest(task)
    if task.approval.get("source") == "result" and task.approval.get("change_sha") == now:
        return ""
    return (f"the person did not approve this version of the result (digest {now}). Run `akasha result {task.id}`, "
            "give its text as your whole answer, and end the turn: the relay sends it to the person")


def result_text(root: Path, task: Task) -> str:
    """The text for the person: the summary, the change at fixed commits, and the changed files."""
    tree = Path(task.workcopy)
    files = list(quick.changes(tree, quick.base(tree), own_records(task)))
    listed = "\n".join(f"- {path}" for path in files[:FILES_SHOWN])
    if len(files) > FILES_SHOWN:
        listed += f"\n- … {len(files) - FILES_SHOWN} more"
    summary = record(task, SUMMARY).read_text(encoding="utf-8", errors="replace").strip()
    address = link(root, task)
    lines = [f"[{task.id}] {task.title}", "", summary, ""]
    if address:
        lines += [f"Change: {address}", ""]
    lines += [f"Changed files ({len(files)}):", listed]
    if task.pr:
        lines += ["", f"Pull request: {task.pr}"]
    return "\n".join(lines)


def show(root: Path, task: Task, session: str) -> str:
    """Keep the digest of the result that the person sees now, and give the text. Only a message of this session,
    after now, approves it. It writes nothing into the work copy: a new commit would start the checks again."""
    now = digest(task)
    if not now:
        raise ValueError(f"write {records(task)}/{SUMMARY} first: the problem, the cause, what changed, what other "
                         "areas it reaches, and how to undo it when a revert is not enough")
    task.preview_sha, task.shown_at, task.shown_in, task.heard = now, time.time(), session, {}
    return result_text(root, task)
