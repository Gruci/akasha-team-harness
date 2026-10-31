"""Run Akasha from its plugin folder: python akasha_run.py <command>. The hooks and the skills use this file."""

import sys
from pathlib import Path

if sys.version_info < (3, 11):
    # hook.sh picks a newer Python. Where it did not run, the agent sees the problem at the start of the session
    reason = (f"Akasha needs Python 3.11 or higher, and this is Python {sys.version.split()[0]}. Ask the person to "
              "install a newer Python, then to restart the agent app.")
    hook = sys.argv[1:2] == ["hook"]
    print(f"[AKASHA] {reason}" if hook else reason, file=sys.stdout if hook else sys.stderr)
    sys.exit(0 if hook else 2)

sys.path.insert(0, str(Path(__file__).resolve().parent))

from akasha.__main__ import run  # noqa: E402  (the path must contain the plugin folder first)

if __name__ == "__main__":
    sys.exit(run())
