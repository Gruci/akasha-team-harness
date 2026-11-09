"""The version of Akasha that the team uses ([team] version in akasha.toml), against the version that runs here.

An administrator chooses the version of the team, and each computer, the CI, and the watch run that version only: an
Akasha of another version, older or newer, starts, continues, and lands no task, because it runs other rules than the
server. The shared settings of Claude Code pin the plugin to that version (claude.py), so a restart moves a computer to
it. Without the setting, nothing is compared."""

from __future__ import annotations

import json
from pathlib import Path

from akasha import REPOSITORY, VERSION, claude, repo, source

CHECK = "version"                            # the name of the version check of the server


def number(text: str) -> tuple[int, ...]:
    return tuple(int(part) for part in text.split("."))


def older(wanted: str, running: str = VERSION) -> bool:
    """True when the Akasha that runs here is older than the version of the team."""
    return bool(wanted) and number(running) < number(wanted)


def _pin(text: str | None) -> str:
    """The version that shared settings of Claude Code pin for the plugin of Akasha, or ""."""
    try:
        ref = json.loads(text or "")["extraKnownMarketplaces"][claude.MARKETPLACE]["source"].get("ref") or ""
    except (ValueError, KeyError, TypeError, AttributeError):
        return ""
    return str(ref).removeprefix("v")


def _pull(root: Path, wanted: str) -> str:
    """The step before a restart when this checkout is behind: the default branch on the server pins the version of
    the team, and the shared settings of this checkout do not yet (also when they pin nothing)."""
    path, branch = root / claude.SETTINGS, repo.default_branch(root)
    here = _pin(path.read_text(encoding="utf-8") if path.is_file() else None)
    there = _pin(repo.git(root, "show", f"origin/{branch}:{claude.SETTINGS}").stdout) if branch else ""
    return f"pull the default branch into {root.as_posix()}, then " if there == wanted != here else ""


def update(wanted: str, root: Path | None = None) -> str:
    """The commands that move this computer to the version of the team. A restart loads the pinned plugin; the three
    commands pin it by hand where the shared settings did not take."""
    pull = _pull(root, wanted) if root else ""
    return (f"in Claude Code {pull}restart the agent app: it loads the Akasha that .claude/settings.json pins. When it "
            f"still runs another one, run `claude plugin marketplace remove akasha`, `claude plugin marketplace add "
            f"{REPOSITORY}#v{wanted}`, and `claude plugin install akasha@akasha`, then restart. For Codex run "
            f'`pip install "{source(wanted)}"`')


def mismatch(wanted: str, running: str = VERSION, root: Path | None = None) -> str:
    """Why this computer starts, continues, and lands no task: it runs another Akasha than the version of the team,
    or "" when they are the same. An older and a newer Akasha both run other rules than the server."""
    if not wanted or wanted == running:
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
    return (f"The server runs Akasha {running}, but akasha.toml asks for {wanted[-1]}. Correct the pin: an "
            f"administrator runs `akasha setup` with Akasha {wanted[-1]} in a task, and removes the repository "
            f"variable AKASHA_SOURCE or sets it to {source(wanted[-1])}.")
