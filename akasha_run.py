"""Run Akasha from its plugin folder: python akasha_run.py <command>. The hooks and the skills use this file."""

import sys
from pathlib import Path

if sys.version_info < (3, 11):
    # A hook must not break the session of a person with an old Python: tell it once, and let the work go on
    print(f"Akasha needs Python 3.11 or higher, and this is Python {sys.version.split()[0]}. Install a newer Python "
          "and make it the first python on PATH.", file=sys.stderr)
    sys.exit(0 if "hook" in sys.argv[1:2] else 2)

sys.path.insert(0, str(Path(__file__).resolve().parent))

from akasha.__main__ import run  # noqa: E402  (the path must contain the plugin folder first)

if __name__ == "__main__":
    sys.exit(run())
