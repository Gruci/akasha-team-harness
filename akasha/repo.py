"""git and the GitHub command line: find the main checkout, run git and gh, and tell who this person is."""

from __future__ import annotations

import json
import os
import re
import secrets
import signal
import subprocess
import time
from pathlib import Path

from akasha.config import STATE_DIR

_GITHUB = re.compile(r"^(?:[a-z][a-z0-9+.-]*://)?(?:[^@/]+@)?(?:www\.|ssh\.)?github\.com(?::\d+)?[:/]+"
                     r"([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?/*$", re.I)
_QUIET = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}    # git must fail, not wait for a password that nobody types
# A new process group, so that a timeout stops a program and all the programs that it started
GROUP = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
ME_FILE = STATE_DIR / "me.json"                        # the GitHub name of this person, for the hooks
ME_AGE = 3600


def stop(process: subprocess.Popen) -> None:
    """Stop a program that started in a new process group, and the programs that it started."""
    if os.name == "nt":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(process.pid)], capture_output=True)
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def git(cwd: Path, *args: str, timeout: float | None = None) -> subprocess.CompletedProcess:
    """Run git. With a timeout, git and the programs that it started stop after that many seconds."""
    process = subprocess.Popen(["git", *args], cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                               encoding="utf-8", errors="replace", env=_QUIET, **GROUP)
    try:
        output, errors = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        stop(process)
        process.communicate()
        return subprocess.CompletedProcess(["git", *args], 124, "", f"git did not answer in {timeout:g} seconds")
    return subprocess.CompletedProcess(["git", *args], process.returncode, output, errors)


def names(cwd: Path, *args: str) -> list[str]:
    """File names from a git listing. Names with Korean or other non-ASCII letters stay as they are."""
    listed = git(cwd, "-c", "core.quotePath=false", *args, "-z")
    if listed.returncode:
        raise RuntimeError(f"git {args[0]} failed: {listed.stderr.strip()[:300]}")
    return [name for name in listed.stdout.split("\0") if name.strip()]


def main_root(cwd: Path) -> Path | None:
    """The main checkout. A work copy is a git worktree, so its common git folder points to the main checkout."""
    try:
        found = git(cwd, "rev-parse", "--path-format=absolute", "--git-common-dir")
    except (OSError, NotADirectoryError):
        return None
    return Path(found.stdout.strip()).parent if found.returncode == 0 else None


def github_slug(address: str) -> str:
    found = _GITHUB.match(address.strip())
    return f"{found.group(1)}/{found.group(2)}" if found else ""


def origin(root: Path) -> str:
    """owner/name of the GitHub repository of origin, or "" when origin is not on GitHub."""
    found = git(root, "remote", "get-url", "origin")
    return github_slug(found.stdout) if found.returncode == 0 else ""


def gh(root: Path, *args: str, payload: dict | None = None, timeout: float = 60) -> subprocess.CompletedProcess:
    """Run the GitHub command line on the repository of origin. When gh is missing or does not answer, the return
    code is not zero."""
    env = dict(os.environ)
    if not env.get("GH_REPO") and (slug := origin(root)):
        env["GH_REPO"] = slug
    try:
        return subprocess.run(["gh", *args], cwd=root, input=json.dumps(payload) if payload is not None else None,
                              capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout,
                              env=env)
    except (OSError, subprocess.TimeoutExpired) as error:
        return subprocess.CompletedProcess(["gh", *args], 127, "", str(error))


def gh_json(root: Path, *args: str, timeout: float = 60):
    """The JSON answer of gh, or None when gh fails."""
    done = gh(root, *args, timeout=timeout)
    if done.returncode:
        return None
    try:
        return json.loads(done.stdout or "null")
    except ValueError:
        return None


def me(root: Path, kept: bool = False, timeout: float = 30) -> str:
    """The GitHub name of the person on this computer in lower case, or "". The hooks take the name that Akasha kept
    for one hour (`kept`); a command asks gh."""
    path = root / ME_FILE
    if kept:
        try:
            known = json.loads(path.read_text(encoding="utf-8"))
            if time.time() - float(known["checked"]) < ME_AGE:
                return str(known["login"]).lower()
        except (OSError, ValueError, KeyError, TypeError):
            pass
    asked = gh(root, "api", "user", "--jq", ".login", timeout=timeout)
    login = asked.stdout.strip().lower() if asked.returncode == 0 else ""
    if login:
        path.parent.mkdir(parents=True, exist_ok=True)
        write_whole(path, json.dumps({"login": login, "checked": time.time()}))
    return login


def person(root: Path, kept: bool = True) -> str:
    """The GitHub name of this person, else the name of git, for a record of a decision."""
    login = me(root, kept=kept, timeout=10) if origin(root) else ""
    if login:
        return login
    named = git(root, "config", "user.name").stdout.strip()
    return named or "unknown"


def default_branch(root: Path) -> str:
    """The default branch of origin as git knows it, without the network. "main" when git does not know it."""
    head = git(root, "symbolic-ref", "-q", "--short", "refs/remotes/origin/HEAD").stdout.strip()
    if head.startswith("origin/"):
        return head.removeprefix("origin/")
    for name in ("main", "master"):
        if git(root, "rev-parse", "-q", "--verify", f"refs/remotes/origin/{name}").returncode == 0:
            return name
    return "main"


def fetch(cwd: Path, branch: str, timeout: float = 120) -> subprocess.CompletedProcess:
    """Fetch one branch of origin into origin/<branch>."""
    return git(cwd, "fetch", "-q", "origin", f"+refs/heads/{branch}:refs/remotes/origin/{branch}", timeout=timeout)


def write_whole(path: Path, text: str) -> None:
    """Write the file in one step, so that no other process reads it half written."""
    temporary = path.with_name(f"{path.name}.{secrets.token_hex(4)}.tmp")
    temporary.write_text(text, encoding="utf-8")
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def inside(path: Path, folder: Path) -> bool:
    try:
        path.resolve().relative_to(folder.resolve())
        return True
    except (ValueError, OSError):
        return False
