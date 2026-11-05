"""A quick task: a small change that no other area of the code uses, for example a typo or one setting.

It needs no preview of the result and no plan. The agent engine makes the change first, then writes impact.md in the
records folder: each changed file, who uses it, and why no other screen changes. The akasha-reviewer agent reviews
the change with impact.md. Then `akasha preview` makes the preview from the change itself, and the person approves
it in the chat, as for each task. The review and the approval hold the digest of the change: a later change needs
both again.

Akasha decides from what the change touches, not from its size: one line of a button that many screens use is not a
quick change. A quick change only changes existing files; it adds and deletes no file, so a new screen never comes
in without a preview. The server check examines the same rules on GitHub for each pull request whose records have
impact.md."""

from __future__ import annotations

import hashlib
import html
import re
from pathlib import Path

from akasha import core
from akasha.checks import ADMIN_PATHS, matches, touches
from akasha.config import Team
from akasha.repo import default_branch, git, names
from akasha.task import Task, record, records

IMPACT = "impact.md"
DOCS = ("**/*.md", "**/*.txt", "**/*.rst", "**/*.adoc")      # text for people: no code imports it
CHANGE_META = re.compile(r'<meta name="akasha-change" content="([0-9a-f]{12})">')
MOST = 200_000                       # characters of the change that the preview shows


def is_quick(task: Task) -> bool:
    return task.kind == "quick"


def base(tree: Path) -> str:
    """The commit where the changes of the task start: after a merge of the default branch, its newer commits are
    not changes of the task."""
    found = git(tree, "merge-base", "HEAD", f"origin/{default_branch(tree)}").stdout.strip()
    return found or git(tree, "rev-parse", "HEAD").stdout.strip()


def _outside(path: str, folder: str) -> bool:
    return not (path + "/").startswith(folder.rstrip("/") + "/")


def changes(tree: Path, start: str, records_dir: str, end: str = "") -> dict[str, str]:
    """The files that the task changed since `start`, without its records: path -> A (added), D (deleted), or M.
    Without `end`, the work copy as it is, also new files that git does not track; with `end`, only that commit."""
    listed = names(tree, "diff", "--name-status", "--no-renames", start, *([end] if end else []))
    found = {listed[at + 1]: listed[at][:1] for at in range(0, len(listed) - 1, 2)}
    if not end:
        found.update({path: "A" for path in names(tree, "ls-files", "--others", "--exclude-standard")})
    return {path: kind for path, kind in sorted(found.items()) if _outside(path, records_dir)}


def problems(team: Team, tree: Path, start: str, end: str = "") -> list[str]:
    """Why the change of the work copy since `start` (or up to the commit `end`) is not a quick change, or [] when it
    is one. The same rules hold for each person: an administrator who needs more makes a full task."""
    changed = changes(tree, start, team.records_dir, end)
    found = [f"{path}: {'a new file' if kind == 'A' else 'a deleted file'}. A quick change only changes existing "
             "files" for path, kind in changed.items() if kind in "AD"]
    edited = [path for path, kind in changed.items() if kind not in "AD"]
    if not edited:
        return found
    locked = set(touches(edited, ADMIN_PATHS + team.risk_paths))
    graph = core.Graph(tree, start)
    for path in edited:
        if path in locked:
            found.append(f"{path}: only an administrator changes it")
        elif any(matches(path, item) for item in team.data_paths):
            found.append(f"{path}: it makes data that people see, so the preview defines its values")
        elif why := core.reason(path, team, graph):
            found.append(f"{path}: {why}, so the change can reach other screens")
        elif not path.endswith(core.PY + core.JS) and not any(matches(path, item) for item in DOCS + team.quick_paths):
            found.append(f"{path}: Akasha cannot tell which screens use this kind of file. An administrator can "
                         "allow it in [quick] paths of akasha.toml")
    return found


def marked(team: Team, changed: list[str]) -> list[str]:
    """The tasks that a pull request marks as quick: their records in the changed files have impact.md."""
    folder = team.records_dir.rstrip("/") + "/"
    return sorted({path[len(folder):].split("/")[0] for path in changed
                   if path.startswith(folder) and path[len(folder):].count("/") == 1 and path.endswith("/" + IMPACT)})


def server(team: Team, root: Path, base: str, changed: list[str]) -> tuple[str, str] | None:
    """The quick check of the server: None when the pull request marks no quick task, else PASS or FAIL and why."""
    tasks = marked(team, changed)
    if not tasks:
        return None
    start = git(root, "merge-base", base, "HEAD").stdout.strip()
    if not start:
        return "FAIL", f"git cannot find where the pull request starts from {base}"
    found = problems(team, root, start, "HEAD")
    if found:
        return "FAIL", (f"task {', '.join(tasks)} is marked quick ({IMPACT}), but its change is not a quick change: "
                        + "; ".join(found[:10]))
    return "PASS", ""


def _diff(tree: Path, start: str, records_dir: str) -> str:
    """The text of the change, without the records. The line ends do not count, as in the digest of a file."""
    shown = git(tree, "-c", "core.quotePath=false", "diff", "--no-renames", "--no-color", "--no-ext-diff", start, "--",
                ".", f":(exclude){records_dir.rstrip('/')}/**")
    return shown.stdout.replace("\r\n", "\n")


def digest(task: Task) -> str:
    """The digest of the change and of impact.md, or "" before impact.md. The review and the approval hold it."""
    note = record(task, IMPACT)
    if not task.workcopy or not note.is_file():
        return ""
    tree = Path(task.workcopy)
    text = note.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n")
    change = _diff(tree, base(tree), task.records_dir)
    return hashlib.sha256(f"{change}\n--- impact.md ---\n{text}".encode()).hexdigest()[:12]


def preview_text(task: Task) -> str:
    """The preview of a quick task: impact.md and the change itself. The digest of the change is in the page."""
    tree = Path(task.workcopy)
    start = base(tree)
    impact = record(task, IMPACT).read_text(encoding="utf-8", errors="replace")
    change = _diff(tree, start, task.records_dir)
    if len(change) > MOST:
        change = change[:MOST] + "\n…"
    files = "".join(f"<li><code>{html.escape(path)}</code></li>" for path in changes(tree, start, task.records_dir))
    return (f'<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="akasha-change" '
            f'content="{digest(task)}"><title>{html.escape(task.title)}</title>'
            '<body style="font-family:sans-serif;max-width:960px;margin:32px auto;padding:0 16px;line-height:1.6">'
            f'<h1>{html.escape(task.title)}</h1>'
            '<section id="akasha-decisions"><h2>경량 과업 · Quick change</h2>'
            f'<pre style="white-space:pre-wrap">{html.escape(impact)}</pre></section>'
            f'<h2>Files</h2><ul>{files}</ul><h2>Change</h2>'
            '<pre style="background:#f6f8fa;padding:12px;overflow:auto;font-size:13px">'
            f'{html.escape(change)}</pre></body></html>\n')


def shown_change(task: Task) -> str:
    """The digest of the change in the preview as Akasha made it, or ""."""
    try:
        found = CHANGE_META.search(record(task, "preview.html").read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return ""
    return found.group(1) if found else ""


def missing(team: Team, task: Task) -> str:
    """What the quick task still needs before the landing, or "". The checks and the summary come after."""
    tree = Path(task.workcopy)
    found = problems(team, tree, base(tree))
    if found:
        return ("this is not a quick change: " + "; ".join(found[:5]) + f". Run `akasha upgrade {task.id}`: the "
                "task becomes a full task with a preview and a plan")
    now = digest(task)
    if not now:
        return (f"write {records(task)}/{IMPACT}: each changed file, which screens use it, and why no other screen "
                "changes")
    if task.review.get("verdict") != "PASS" or task.review.get("plan_sha") != now:
        return (f"the akasha-reviewer agent did not pass this version of the change (digest {now}). Ask it to "
                f"review the quick task {task.id}")
    if not task.approval or task.approval.get("change_sha") != now:
        return (f"the person did not approve this version of the change. Show it with `akasha preview {task.id}` "
                "and ask the person in the chat")
    return ""
