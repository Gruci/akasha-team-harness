"""A real git repository with a local origin, for the tests. A local origin is not GitHub, so Akasha works without
the board, as on a computer without GitHub."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

TEAM = """[team]
admins = ["admin-a", "admin-b"]

[risk]
paths = ["db/**"]

[checks]
required = ["secrets", "tests"]

[checks.tests]
command = "python -c \\"import sys; sys.exit(0)\\""
"""


def run(cwd: Path, *args: str) -> str:
    done = subprocess.run(list(args), cwd=cwd, capture_output=True, text=True, encoding="utf-8")
    if done.returncode:
        raise AssertionError(f"{args}: {done.stderr}")
    return done.stdout


class Repository:
    """A temporary repository: `root` is the main checkout, and `origin` a bare repository."""

    def __init__(self, team: str = TEAM) -> None:
        self.folder = tempfile.TemporaryDirectory()
        base = Path(self.folder.name)
        self.origin = base / "origin.git"
        self.root = base / "work"
        run(base, "git", "init", "-q", "--bare", "-b", "main", str(self.origin))
        self.root.mkdir()
        run(self.root, "git", "init", "-q", "-b", "main")
        run(self.root, "git", "config", "user.name", "Tester")
        run(self.root, "git", "config", "user.email", "tester@example.com")
        (self.root / "app.py").write_text("print('hello')\n", encoding="utf-8")
        (self.root / "db").mkdir()
        (self.root / "db" / "schema.sql").write_text("create table a (x int);\n", encoding="utf-8")
        if team:
            (self.root / "akasha.toml").write_text(team, encoding="utf-8")
        (self.root / ".gitignore").write_text(".akasha/state/\n.akasha/work/\n", encoding="utf-8")
        run(self.root, "git", "add", "-A")
        run(self.root, "git", "commit", "-q", "-m", "first")
        run(self.root, "git", "remote", "add", "origin", str(self.origin))
        run(self.root, "git", "push", "-q", "-u", "origin", "main")
        run(self.root, "git", "remote", "set-head", "origin", "main")

    def close(self) -> None:
        self.folder.cleanup()
