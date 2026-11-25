"""The version of Akasha that the team uses ([team] version in akasha.toml), against the version that runs here.

An administrator chooses the version of the team. The CI and the watch run that version itself: the server is the
judge of each change. A computer runs that version or another patch of the same minor version (2.0.x): a patch
changes no rule. An Akasha of another minor version, older or newer, starts, continues, and lands no task, because it
runs other rules than the server. The team fixes the version for the computers too, as it fixes the version of
Python: the marketplace file of the repository (claude.py) names the release tag of that version, and nothing moves a
computer without a change of that file. After the change, one command of Claude Code moves a computer: `/plugin update
akasha@akasha`, and a session start of Claude Code runs it by itself (start_update): the person restarts the session.
A computer that runs another patch is told, and nothing stops. Without the setting, nothing is
compared."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from akasha import REPOSITORY, VERSION, claude, repo, source
from akasha.config import STATE_DIR

CHECK = "version"                            # the name of the version check of the server
# The one command of Claude Code that moves a computer to the version that the team fixes, newer or older. It reads
# the marketplace file of the repository where it is, so it needs no refresh of a marketplace before it
UPDATE = "/plugin update akasha@akasha"
# Where the team fixes no version ([team] version is empty): the commands that take the newest Akasha of the
# marketplace that this computer follows. The second one does not refresh the marketplace itself
REFRESH = "/plugin marketplace update akasha, then /plugin update akasha@akasha, then restart the agent app"
# When this computer last started an update of the plugin by itself, for which version and folder: a second session
# start in the same minutes does not start it again
STARTED = STATE_DIR / "plugin-update.json"
AGAIN_AFTER = 600                            # seconds
SWITCH = "AKASHA_PLUGIN_UPDATE"               # "off": a session start updates no plugin (a person, a CI, the tests)
# The update of the plugin in the background: the install of the folder of the session (Claude Code keeps one for
# each folder, also for each work copy of a task), then the install of the person, one after the other
UPDATER = ("import subprocess, sys\n"
           "for scope in ('project', 'user'):\n"
           "    subprocess.run([sys.argv[1], 'plugin', 'update', 'akasha@akasha', '--scope', scope], cwd=sys.argv[2], "
           "stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=300)\n")


def number(text: str) -> tuple[int, ...]:
    return tuple(int(part) for part in text.split("."))


def older(wanted: str, running: str = VERSION) -> bool:
    """True when the Akasha that runs here is older than the version of the team."""
    return bool(wanted) and number(running) < number(wanted)


def _pin(text: str | None) -> str:
    """The version that a marketplace file of the team fixes for the plugin of Akasha, or ""."""
    try:
        plugins = json.loads(text or "")["plugins"]
        return next(str(item["version"]) for item in plugins if item["name"] == claude.MARKETPLACE)
    except (ValueError, KeyError, TypeError, StopIteration):
        return ""


def own_settings() -> Path:
    """The settings of Claude Code of this person. `claude plugin marketplace add` writes its declaration there."""
    return Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude") / "settings.json"


def market(root: Path) -> Path:
    """The folder of the marketplace of the team, in the main checkout: Claude Code reads the file where it is, and
    the work copy of a task goes away."""
    return (repo.main_root(root) or root) / claude.MARKET


def _register(root: Path, settings: Path | None = None) -> str:
    """The step before the update, once for a computer that takes Akasha from another place than the folder of a
    team, for example from a tag of the public repository that an older Akasha told the person to add: there
    `/plugin update` finds nothing new. The command replaces that declaration, and keeps the plugin. "" when the
    computer follows a folder, and when Claude Code holds no declaration of this person (Codex)."""
    path = settings or own_settings()
    try:
        kind = json.loads(path.read_text(encoding="utf-8-sig"))["extraKnownMarketplaces"][claude.MARKETPLACE]["source"]
        kind = str(kind["source"])
    except (OSError, ValueError, KeyError, TypeError):
        return ""
    if kind == "directory":
        return ""
    return (f'once run `claude plugin marketplace add "{market(root).as_posix()}"` (this computer takes Akasha from '
            f"a {kind} source, where no team fixes the version), then ")


def _pull(root: Path, wanted: str) -> str:
    """The step before the update when the main checkout is behind: the default branch on the server fixes the
    version of the team in the marketplace file, and the main checkout does not yet (also when it has no file)."""
    main, branch = repo.main_root(root) or root, repo.default_branch(root)
    path = main / claude.MARKET_FILE
    here = _pin(path.read_text(encoding="utf-8") if path.is_file() else None)
    there = _pin(repo.git(root, "show", f"origin/{branch}:{claude.MARKET_FILE}").stdout) if branch else ""
    return f"pull the default branch into {main.as_posix()}, then " if there == wanted != here else ""


def same_rules(wanted: str, running: str = VERSION) -> bool:
    """True when the two versions hold the same rules: the same major and minor number. A patch changes no rule."""
    return number(wanted)[:2] == number(running)[:2]


def update(wanted: str, root: Path | None = None, settings: Path | None = None) -> str:
    """How this computer moves to the version of the team: one command of Claude Code, after a pull when the main
    checkout is behind, and after the registration of the marketplace of the repository when the computer does not
    follow one yet."""
    first = _pull(root, wanted) + _register(root, settings) if root else ""
    return (f"in Claude Code {first}run `{UPDATE}`, then restart the agent app. For Codex run "
            f'`pip install "{source(wanted)}"`')


def other_patch(wanted: str, running: str = VERSION, root: Path | None = None) -> str:
    """What the person does on a computer that runs another patch than the team fixes, older or newer, or "". The
    rules are the same, so nothing stops: the session start notice and `akasha doctor` tell it."""
    if not wanted or wanted == running or not same_rules(wanted, running):
        return ""
    return (f"This computer runs Akasha {running}, and the team fixes {wanted} ([team] version in akasha.toml). To "
            f"move to {wanted}, {update(wanted, root)}.")


def mismatch(wanted: str, running: str = VERSION, root: Path | None = None) -> str:
    """Why this computer starts, continues, and lands no task: it runs an Akasha with other rules than the version
    of the team, or "" when the rules are the same. An older and a newer Akasha both run other rules than the
    server."""
    if not wanted or same_rules(wanted, running):
        return ""
    side = "older" if older(wanted, running) else "newer"
    return (f"This computer runs Akasha {running}, {side} than {wanted}, the version of the team in akasha.toml, so it "
            f"starts, continues, and lands no task. To move to {wanted}, {update(wanted, root)}. Only an "
            "administrator changes the version of the team: [team] version in akasha.toml, then `akasha setup`, in a "
            "task.")


def release_problem(root: Path, wanted: str) -> str:
    """Why the team cannot use this version: the public repository has no release tag of it, so the CI cannot install
    it. "" when the tag is there, or when git cannot ask (the server check still fails then)."""
    done = repo.git(root, "ls-remote", "--tags", f"https://github.com/{REPOSITORY}", f"refs/tags/v{wanted}",
                    timeout=20)
    if done.returncode != 0 or done.stdout.strip():
        return ""
    return (f"Akasha {wanted} has no release: the public repository has no tag v{wanted}, so the CI cannot install "
            "it. Set [team] version in akasha.toml to a released version")


def server_problem(wanted: tuple[str, ...], running: str = VERSION) -> str:
    """Why the server check fails: the Akasha on the server is not the version of the team. `wanted` holds the
    versions that count, for example of the base branch and of the pull request that raises it. Without a version,
    nothing fails."""
    wanted = tuple(item for item in wanted if item)
    if not wanted or running in wanted:
        return ""
    return (f"The server runs Akasha {running}, but akasha.toml asks for {wanted[-1]}. Correct the source: an "
            f"administrator removes the repository variable AKASHA_SOURCE or sets it to {source(wanted[-1])}, and "
            f"runs `akasha setup` with Akasha {wanted[-1]} in a task when the workflows still name a version.")


def start_update(root: Path, folder: Path, wanted: str, running: str = VERSION) -> str:
    """Move this computer to the version of the team by itself: start `claude plugin update` in the background, for
    the folder of the session and for the person, when this computer runs another version, follows the folder of
    the marketplace of the team, and its main checkout already fixes that version. Claude Code reads a plugin when a
    session starts, so the person restarts the session after it. The line for the session start notice, or "" when
    Akasha did not start it (then `other_patch` and `mismatch` tell the command)."""
    if not wanted or wanted == running or os.environ.get(SWITCH, "").lower() == "off" or _pull(root, wanted) \
            or _register(root):
        return ""
    found = shutil.which("claude")
    if not found:
        return ""
    path = root / STARTED
    try:
        last = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        last = {}
    place = str(folder)
    if not (isinstance(last, dict) and last.get("version") == wanted and last.get("folder") == place
            and time.time() - float(last.get("at") or 0) < AGAIN_AFTER):
        flags = {"creationflags": subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP} \
            if os.name == "nt" else {"start_new_session": True}
        try:
            subprocess.Popen([sys.executable, "-c", UPDATER, found, place], cwd=place, stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **flags)
        except OSError:
            return ""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"version": wanted, "folder": place, "at": time.time()}), encoding="utf-8")
    return (f"This computer runs Akasha {running}, and the team fixes {wanted}. Akasha updates the plugin of this "
            f"folder to {wanted} in the background (`claude plugin update akasha@akasha`): after a restart of the "
            "session in a minute, it runs the version of the team.")
