"""Run Akasha from its plugin folder: python akasha_run.py <command>. The hooks and the skills use this file."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from akasha.__main__ import run  # noqa: E402  (the path must contain the plugin folder first)

if __name__ == "__main__":
    sys.exit(run())
