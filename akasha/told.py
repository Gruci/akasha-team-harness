"""What the main session told the person of the progress of a task: the stage and the state that it gave last.

The skill asks the main session for the four lines of the progress each time the stage changes (progress.py). A text
in a skill stops nothing, so the hook at the end of a turn (hooks.on_stop) compares the stage of each task of the
session with the one here. When it differs, the hook keeps the new one and sends the lines back to the session,
which then gives them to the person before the turn ends.

The stage is in a file of its own, one for each task, and not in the record of the task. The hook runs at the end of
each turn, also while a command or a worker of the same task writes that record: a second writer of the record would
lose their change. The file is on this computer only: the next computer of a task starts with nothing told."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from akasha.config import STATE_DIR
from akasha.repo import write_whole
from akasha.task import Task


def _place(root: Path, task_id: str) -> Path:
    return root / STATE_DIR / "told" / f"{task_id}.txt"


def key(found) -> str:
    """The stage and the state of a progress (progress.Progress) in one word: `build|work`. The steps of the plan
    that are done and the number of a repair are not in it: they change in most turns of a build."""
    return f"{found.stage}|{found.state}"


def read(root: Path, task_id: str) -> str | None:
    """The stage that the session told last, or None when nothing is kept: a task that an Akasha before 2.0.6
    started, or one that came from another computer."""
    try:
        return _place(root, task_id).read_text(encoding="utf-8").strip()
    except OSError:
        return None


def write(root: Path, task_id: str, told: str) -> None:
    place = _place(root, task_id)
    place.parent.mkdir(parents=True, exist_ok=True)
    write_whole(place, told + "\n")


def start(root: Path, task: Task, progress: Callable[[], object]) -> None:
    """Keep the stage of a task that starts now, so that its first new stage is told. A failure never stops the
    start: without the file, the first end of a turn keeps the stage and tells nothing."""
    try:
        write(root, task.id, key(progress()))
    except Exception:     # noqa: BLE001 — the progress is no part of the start
        pass


def forget(root: Path, task_id: str) -> None:
    _place(root, task_id).unlink(missing_ok=True)
