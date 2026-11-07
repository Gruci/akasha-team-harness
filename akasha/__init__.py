"""Akasha: a light team harness for coding agents. A person approves a preview at the start; the AI does the rest."""

VERSION = "1.1.3"


def source(version: str) -> str:
    """The pip source of one version of Akasha. From v1.0.0 on, each release has its own tag, and a fix gets a new
    version."""
    return f"git+https://github.com/Gruci/akasha-team-harness@v{version}"


SOURCE = source(VERSION)                     # the pip source of this Akasha
