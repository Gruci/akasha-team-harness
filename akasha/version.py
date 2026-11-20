"""The version of Akasha that the team uses ([team] version in akasha.toml), against the version that runs here.

An administrator chooses the version of the team. The CI and the watch run that version itself: the server is the
judge of each change. A computer runs that version or another patch of the same minor version (2.0.x): a patch
changes no rule. An Akasha of another minor version, older or newer, starts, continues, and lands no task, because it
runs other rules than the server. The shared settings of Claude Code make the plugin follow the branch of that minor
version (claude.py), so a computer takes each patch by itself, also before the team raises its version. Only a new
minor version changes the settings. Without the setting, nothing is compared."""

from __future__ import annotations

import json
import os
from pathlib import Path

from akasha import REPOSITORY, VERSION, claude, line, repo, source

CHECK = "version"                            # the name of the version check of the server
# The commands of Claude Code that take the newest patch: the second one does not refresh the marketplace itself
REFRESH = "/plugin marketplace update akasha, then /plugin update akasha@akasha, then restart the agent app"


def number(text: str) -> tuple[int, ...]:
    return tuple(int(part) for part in text.split("."))


def older(wanted: str, running: str = VERSION) -> bool:
    """True when the Akasha that runs here is older than the version of the team."""
    return bool(wanted) and number(running) < number(wanted)


def _ref(text: str | None) -> str:
    """The ref that settings of Claude Code name for the marketplace of Akasha, or ""."""
    try:
        return str(json.loads(text or "")["extraKnownMarketplaces"][claude.MARKETPLACE]["source"].get("ref") or "")
    except (ValueError, KeyError, TypeError, AttributeError):
        return ""


def _pin(text: str | None) -> str:
    """The branch of the minor version that shared settings of Claude Code name for the plugin of Akasha, or "".
    Settings that an Akasha before 2.0.2 wrote name the tag of a patch (v2.0.1): that is the branch v2.0."""
    ref = _ref(text)
    return line(ref.removeprefix("v")) if ref else ""


def own_settings() -> Path:
    """The settings of Claude Code of this person. `claude plugin marketplace add` writes its declaration there."""
    return Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude") / "settings.json"


def _renew(wanted: str) -> str:
    """The commands that replace the own declaration of this person. The first one names its scope: without
    `--scope user`, Claude Code also removes the marketplace and the plugin from the shared settings of the
    repository. The last one is `update`: `install` changes no plugin that is there."""
    return (f"`claude plugin marketplace remove akasha --scope user`, `claude plugin marketplace add "
            f"{REPOSITORY}#{line(wanted)}`, and `claude plugin update akasha@akasha`, then restart")


def stale(wanted: str, settings: Path | None = None) -> str:
    """Why this computer takes no new patch, or "": the own declaration of this person names another ref of the
    marketplace of Akasha than the branch of the minor version of the team. It wins over the shared settings of the
    repository. An Akasha before 2.0.2 told the person to add the tag of a patch (v2.0.1), and a tag never moves."""
    path = settings or own_settings()
    try:
        ref = _ref(path.read_text(encoding="utf-8-sig"))
    except OSError:
        return ""
    if not wanted or not ref or ref == line(wanted):
        return ""
    return (f"Claude Code on this computer follows {ref} of the marketplace of Akasha ({path.as_posix()} names it), "
            f"not {line(wanted)}, the branch that the team follows, so it takes no new patch. Once, run "
            f"{_renew(wanted)}")


def _pull(root: Path, wanted: str) -> str:
    """The step before a restart when this checkout is behind: the default branch on the server names the minor
    version of the team, and the shared settings of this checkout do not yet (also when they name nothing)."""
    path, branch = root / claude.SETTINGS, repo.default_branch(root)
    here = _pin(path.read_text(encoding="utf-8") if path.is_file() else None)
    there = _pin(repo.git(root, "show", f"origin/{branch}:{claude.SETTINGS}").stdout) if branch else ""
    return f"pull the default branch into {root.as_posix()}, then " if there == line(wanted) != here else ""


def same_rules(wanted: str, running: str = VERSION) -> bool:
    """True when the two versions hold the same rules: the same major and minor number. A patch changes no rule."""
    return number(wanted)[:2] == number(running)[:2]


def update(wanted: str, root: Path | None = None, running: str = VERSION) -> str:
    """The commands that move this computer to the version of the team. Another patch of the same minor version: the
    plugin follows the branch of the minor version, so a refresh takes it. Another minor version: a restart loads the
    plugin from the branch that the shared settings name, and the three commands move a computer whose own
    declaration of the marketplace (`claude plugin marketplace add` wrote it) still names the old one."""
    if same_rules(wanted, running):
        return f'in Claude Code run {REFRESH}. For Codex run `pip install "{source(wanted)}"`'
    pull = _pull(root, wanted) if root else ""
    return (f"in Claude Code {pull}restart the agent app: it loads the Akasha that .claude/settings.json names. When "
            f'it still runs another one, run {_renew(wanted)}. For Codex run `pip install "{source(wanted)}"`')


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
