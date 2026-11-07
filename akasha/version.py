"""The version of Akasha that the team uses ([team] version in akasha.toml), against the version that runs here.

The CI and the watch install one version of Akasha, and each computer installs the plugin by itself. Without one
version for all, a computer and the server can run different rules. Without the setting, nothing is compared."""

from __future__ import annotations

from akasha import VERSION, source

CHECK = "version"                            # the name of the version check of the server


def number(text: str) -> tuple[int, ...]:
    return tuple(int(part) for part in text.split("."))


def older(wanted: str, running: str = VERSION) -> bool:
    """True when the Akasha that runs here is older than the version of the team."""
    return bool(wanted) and number(running) < number(wanted)


def update(wanted: str) -> str:
    """The commands that install the version of the team."""
    return (f"in Claude Code run `claude plugin marketplace update akasha`, then `claude plugin update akasha@akasha`, "
            f"and restart the agent app; for Codex run `pip install \"{source(wanted)}\"`")


def mismatch(wanted: str, running: str = VERSION) -> str:
    """One line about a difference from the version of the team, with its fix, or "" when they are the same."""
    if not wanted or wanted == running:
        return ""
    if older(wanted, running):
        return (f"This computer runs Akasha {running}, older than {wanted}, the version of the team in akasha.toml. "
                f"To update it, {update(wanted)}.")
    return (f"This computer runs Akasha {running}, newer than {wanted}, the version of the team in akasha.toml. An "
            f"administrator raises the version of the team: `akasha setup` in a task writes {running} into "
            "akasha.toml and the workflows.")


def start_problem(wanted: str, running: str = VERSION) -> str:
    """Why a new task cannot start: an older Akasha than the team uses runs older rules. A newer one only warns."""
    return mismatch(wanted, running) if older(wanted, running) else ""


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
