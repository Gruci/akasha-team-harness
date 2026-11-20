"""Akasha: a light team harness for coding agents. A person approves a preview at the start; the AI does the rest."""

VERSION = "2.0.2"
REPOSITORY = "Gruci/akasha-team-harness"     # the public repository: the marketplace, the release tags, and pip


def source(version: str) -> str:
    """The pip source of one version of Akasha. From v1.0.0 on, each release has its own tag, and a fix gets a new
    version."""
    return f"git+https://github.com/{REPOSITORY}@v{version}"


SOURCE = source(VERSION)                     # the pip source of this Akasha


def line(version: str) -> str:
    """The branch of the public repository that the plugin of Claude Code follows: one for each minor version, for
    example v2.0. Each release of a patch moves it, so a computer takes a patch without a change in the repository of
    the team. The tag of a release (v2.0.2) never moves: pip and the server install from it."""
    return "v" + ".".join(version.split(".")[:2])
