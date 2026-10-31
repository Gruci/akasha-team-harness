"""Find the main checkout of the repository, also from inside the work copy of a task, run the GitHub command line,
and tell who and where this person is."""

from __future__ import annotations

import json
import os
import re
import secrets
import subprocess
import time
from pathlib import Path

from akasha.config import STATE_DIR

# The GitHub repository in an address of origin: https://github.com/a/b.git, git@github.com:a/b.git, ssh://...
_GITHUB = re.compile(r"^(?:[a-z][a-z0-9+.-]*://)?(?:[^@/]+@)?(?:www\.|ssh\.)?github\.com(?::\d+)?[:/]+"
                     r"([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?/*$", re.I)
_ME_FILE = STATE_DIR / "me.json"               # the GitHub name of this person, for the hooks
_MACHINE_FILE = STATE_DIR / "machine.json"     # the random mark of this copy of the repository
_ME_AGE = 3600                                 # one hour, in seconds
_logins: dict[Path, str] = {}                  # one question to gh in each process


def main_root(cwd: Path) -> Path | None:
    """The main checkout. A work copy is a git worktree, so its common git folder points to the main checkout."""
    found = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=cwd,
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
    if found.returncode:
        return None
    return Path(found.stdout.strip()).parent


def github_slug(address: str) -> str:
    """owner/name when the git address is a GitHub repository, else ""."""
    found = _GITHUB.match(address.strip())
    return f"{found.group(1)}/{found.group(2)}" if found else ""


def origin(root: Path) -> str:
    """owner/name of the GitHub repository of the git remote origin, or "" when origin is not on GitHub."""
    try:
        found = subprocess.run(["git", "remote", "get-url", "origin"], cwd=root, capture_output=True, text=True,
                               encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return github_slug(found.stdout) if found.returncode == 0 else ""


def gh_repo(root: Path) -> str:
    """The repository that gh uses: the GH_REPO that the person set, else the repository of origin, else ""."""
    return os.environ.get("GH_REPO") or origin(root)


def gh(root: Path, *args: str, payload: dict | None = None, timeout: float = 60) -> subprocess.CompletedProcess:
    """Run the GitHub command line. When gh is missing or does not answer, the return code is not zero.

    gh gets the repository of origin, so that gh and git always use the same repository. Without this, gh can
    select another remote, for example upstream, and the issues and pull requests go to another repository than the
    branches. A GH_REPO that the person set stays. `gh repo view` does not read GH_REPO, so its callers give the
    repository from gh_repo."""
    env = None
    if not os.environ.get("GH_REPO") and (slug := origin(root)):
        env = {**os.environ, "GH_REPO": slug}
    try:
        return subprocess.run(["gh", *args], cwd=root, input=json.dumps(payload) if payload is not None else None,
                              capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout,
                              env=env)
    except (OSError, subprocess.TimeoutExpired) as error:
        return subprocess.CompletedProcess(["gh", *args], 127, "", str(error))


def me(root: Path, fresh: bool = False, timeout: float = 60) -> str:
    """The GitHub name of the person on this computer in lower case, or "" when gh does not answer in `timeout`.

    Akasha asks gh once in each process. Each hook is a new process, so Akasha also keeps the name for one hour.
    With `fresh`, Akasha asks gh and does not read the kept name: a person can edit the file."""
    if root in _logins and not fresh:
        return _logins[root]
    path = root / _ME_FILE
    try:
        known = {} if fresh else json.loads(path.read_text(encoding="utf-8"))
        login = str(known["login"]).lower() if time.time() - float(known["checked"]) < _ME_AGE else ""
    except (OSError, ValueError, KeyError, TypeError):
        login = ""
    if not login:
        asked = gh(root, "api", "user", "--jq", ".login", timeout=timeout)
        login = asked.stdout.strip().lower() if asked.returncode == 0 else ""
        if login:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"login": login, "checked": time.time()}), encoding="utf-8")
    _logins[root] = login
    return login


def write_whole(path: Path, text: str, replace: bool = True) -> bool:
    """Write the file in one step, so that no other process reads it empty or half written. Without replace, the
    file must be new: False when it is already there.

    The text goes into a temporary file first. os.replace puts it in place of any file. A rename on Windows and a
    hard link elsewhere fail when the file is already there."""
    temporary = path.with_name(f"{path.name}.{secrets.token_hex(4)}.tmp")
    temporary.write_text(text, encoding="utf-8")
    try:
        if replace:
            os.replace(temporary, path)
        elif os.name == "nt":
            os.rename(temporary, path)
        else:
            os.link(temporary, path)
        return True
    except FileExistsError:
        return False
    finally:
        temporary.unlink(missing_ok=True)


def host(root: Path) -> str:
    """The random mark of this copy of the repository on this computer. Akasha makes it at the first call.

    When two processes make the mark at the same time, both get the mark of the process that wrote it first."""
    path = root / _MACHINE_FILE
    missing = False
    try:
        mark = json.loads(path.read_text(encoding="utf-8")).get("host")
    except FileNotFoundError:
        mark, missing = "", True
    except (OSError, ValueError, AttributeError):
        mark = ""                                     # a damaged file gets a new mark
    if isinstance(mark, str) and mark:
        return mark
    made = secrets.token_hex(8)
    path.parent.mkdir(parents=True, exist_ok=True)
    if write_whole(path, json.dumps({"host": made}), replace=not missing):
        return made
    return host(root)                                 # another process wrote its mark first
