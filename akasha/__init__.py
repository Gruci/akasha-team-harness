"""Akasha: a light team harness for coding agents. A person approves a preview at the start; the AI does the rest."""

VERSION = "2.0.0"
REPOSITORY = "Gruci/akasha-team-harness"     # the public repository: the marketplace, the release tags, and pip


def source(version: str) -> str:
    """The pip source of one version of Akasha. From v1.0.0 on, each release has its own tag, and a fix gets a new
    version."""
    return f"git+https://github.com/{REPOSITORY}@v{version}"


SOURCE = source(VERSION)                     # the pip source of this Akasha
