"""Find secret keys in text before they go into the repository."""

from __future__ import annotations

import re

PATTERNS = {
    "OpenAI or Anthropic key": re.compile(r"\bsk-(?:ant-)?[A-Za-z0-9_\-]{20,}"),
    "GitHub token": re.compile(r"\b(?:ghp|gho|ghs|ghu)_[A-Za-z0-9]{30,}|\bgithub_pat_[A-Za-z0-9_]{30,}"),
    "AWS access key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "Slack token": re.compile(r"\bxox[abprs]-[A-Za-z0-9\-]{10,}"),
    "Google API key": re.compile(r"\bAIza[0-9A-Za-z_\-]{30,}"),
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
}


def find(text: str) -> list[tuple[int, str]]:
    """(line number, kind) for each secret key in the text."""
    return [(number, kind) for number, line in enumerate(text.splitlines(), 1)
            for kind, pattern in PATTERNS.items() if pattern.search(line)]
