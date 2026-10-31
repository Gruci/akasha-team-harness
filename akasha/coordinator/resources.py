"""Give the preview of each task its own database name and port, so that two previews never collide.

The port of a task is a reservation of the person on this computer, in ~/.akasha/ports.json: the previews of all
copies of all repositories of the person use the ports of one computer. A preview starts only at the inspection, so
a port that no program uses now can be the port of another task. Thus the reservations come first, and Akasha also
skips a port that a program uses now. The port stays on this computer: the issue never holds it."""

from __future__ import annotations

import json
import os
import re
import socket
import time
import zlib
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from akasha.core import task as tasks
from akasha.core.task import Task
from akasha.repo import write_whole

PORT_FIRST = 4100
PORT_COUNT = 800
PORT_LAST = PORT_FIRST + PORT_COUNT - 1
PORTS = Path("~") / ".akasha" / "ports.json"      # repository -> task -> port, for the person on this computer
LOCK_SECONDS = 10                                 # how long a command waits for the lock of the reservations
STALE_SECONDS = 60                                # a lock that is this old is from a command that stopped
CONNECT_SECONDS = 0.2                             # a program that listens on this computer answers at once


def in_range(port: object) -> bool:
    """True for a port of the previews of Akasha: an integer from PORT_FIRST to PORT_LAST."""
    return type(port) is int and PORT_FIRST <= port <= PORT_LAST


def _first(task_id: str) -> int:
    """The first port to try for the task. It comes from the task id, so that a task gets the same port again."""
    return PORT_FIRST + zlib.crc32(task_id.encode("utf-8")) % PORT_COUNT


def busy(port: int) -> bool:
    """True when a program on this computer uses the port: Akasha cannot bind it on 127.0.0.1 or 0.0.0.0, or a
    program answers on 127.0.0.1 or ::1. A computer without IPv6 skips ::1."""
    for host in ("127.0.0.1", "0.0.0.0"):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            try:
                probe.bind((host, port))
            except OSError:
                return True
    for family, host in ((socket.AF_INET, "127.0.0.1"), (socket.AF_INET6, "::1")):
        try:
            with socket.socket(family, socket.SOCK_STREAM) as probe:
                probe.settimeout(CONNECT_SECONDS)
                if probe.connect_ex((host, port)) == 0:
                    return True
        except OSError:
            continue                                  # no IPv6 on this computer
    return False


def _key(root: Path) -> str:
    """The key of a copy of the repository in the reservations: its folder."""
    return os.path.normcase(str(root.resolve()))


def _lock(lock: Path) -> None:
    """Make the lock file of the reservations. A lock file that is older than STALE_SECONDS is from a command that
    stopped: Akasha removes it."""
    deadline = time.monotonic() + LOCK_SECONDS
    while True:
        try:
            os.close(os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
            return
        except FileExistsError:
            pass
        try:
            stale = time.time() - lock.stat().st_mtime > STALE_SECONDS
        except OSError:
            stale = False                             # the other command removed its lock now
        if stale:
            lock.unlink(missing_ok=True)
        elif time.monotonic() > deadline:
            raise RuntimeError(f"another Akasha command holds the lock of the preview ports, {lock}. Do the step "
                               f"again. If no other Akasha command runs, remove {lock}")
        else:
            time.sleep(0.05)


def _read(path: Path) -> dict[str, dict[str, int]]:
    """The reservations in the file. A damaged file or entry is no reservation: the test of busy ports still keeps a
    preview that runs safe."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {repository: {task_id: port for task_id, port in ports.items() if in_range(port)}
            for repository, ports in data.items() if isinstance(ports, dict)}


@contextmanager
def _reservations() -> Iterator[dict[str, dict[str, int]]]:
    """The reservations of the person on this computer, under a lock, so that two commands at the same time never
    reserve one port. The changes go into the file when the block ends without an error."""
    path = PORTS.expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = path.with_name(f"{path.name}.lock")
    _lock(lock)
    try:
        reserved = _read(path)
        yield reserved
        write_whole(path, json.dumps(reserved, indent=2, sort_keys=True) + "\n")
    finally:
        lock.unlink(missing_ok=True)


def _needed(repository: str, task_id: str) -> bool:
    """True while a reservation can be in use: the task in that copy of the repository has its work copy. A copy of
    the repository that a person removed, a finished task, and a task that went to another computer free the port. A
    task file that Akasha cannot read keeps it."""
    try:
        task = tasks.load(Path(repository), task_id)
        if not isinstance(task.workcopy, str):
            raise TypeError(f"the work copy of {task_id} is not a folder name")
        return bool(task.workcopy) and Path(task.workcopy).is_dir()
    except LookupError:
        return False
    except (OSError, ValueError, TypeError):
        return True


def _prune(reserved: dict[str, dict[str, int]], key: str, task_id: str) -> None:
    """Remove the reservations that nothing needs now (_needed), apart from the reservation of the task itself."""
    for repository, ports in list(reserved.items()):
        for name in [name for name in ports if (repository, name) != (key, task_id) and not _needed(repository, name)]:
            del ports[name]
        if not ports:
            del reserved[repository]


def port(root: Path, task: Task) -> int:
    """The preview port of the task on this computer. It also goes into task.port: the caller saves the task.

    A task keeps its port. Else Akasha starts at the port that the task id gives and goes through the range. It skips
    each port that another task of the person reserved, and each port that a program uses now (busy)."""
    key = _key(root)
    with _reservations() as reserved:
        _prune(reserved, key, task.id)
        mine = reserved.setdefault(key, {})
        others = {number for repository, ports in reserved.items() for name, number in ports.items()
                  if (repository, name) != (key, task.id)}
        kept = task.port if in_range(task.port) else mine.get(task.id, 0)
        if kept and kept not in others and (mine.get(task.id) == kept or not busy(kept)):
            mine[task.id] = task.port = kept          # the preview of the task itself can use its port now
            return kept
        for step in range(PORT_COUNT):
            candidate = PORT_FIRST + (_first(task.id) - PORT_FIRST + step) % PORT_COUNT
            if candidate not in others and not busy(candidate):
                mine[task.id] = task.port = candidate
                return candidate
    raise RuntimeError(f"each preview port from {PORT_FIRST} to {PORT_LAST} on this computer is reserved or in use. "
                       "Stop the previews that you do not need, and finish or remove the work copies of old tasks")


def release(root: Path, task: Task) -> None:
    """Free the preview port of the task on this computer, when its work copy goes away. When Akasha cannot write the
    reservations now, the next reservation frees the port: the task has no work copy then (_needed)."""
    if task.port:
        key = _key(root)
        try:
            with _reservations() as reserved:
                ports = reserved.get(key, {})
                ports.pop(task.id, None)
                if not ports:
                    reserved.pop(key, None)
        except (OSError, RuntimeError):
            pass
    task.port = 0


def fill(template: str, task_id: str, port: int = 0) -> str:
    """Put the task name and the port into a value of [preview], for example "app_{task}" or "--port {port}". The
    port goes in only as an integer in the range: the commands of the preview run in a shell."""
    if "{port}" in template and not in_range(port):
        raise ValueError(f"the preview port {port!r} is not from {PORT_FIRST} to {PORT_LAST}. Reserve the port of the "
                         "task with akasha preview <task>")
    safe = re.sub(r"[^A-Za-z0-9_]", "_", task_id)
    return template.replace("{task}", safe).replace("{port}", str(port))
