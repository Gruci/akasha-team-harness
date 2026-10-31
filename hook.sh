#!/bin/sh
# Run a hook of Akasha with Python 3.11 or higher: the first python on PATH can be older, or the stub of the
# Microsoft Store. `hook.sh --python` prints the Python that the hooks use, for akasha doctor.
# Without such a Python, the session start and the prompt tell it to the agent, and an edit in a repository that uses
# Akasha stops, so that no step goes around Akasha without notice. Shell commands still run, to repair it.
here=$(dirname "$(printf '%s' "$0" | tr '\\' '/')")       # on Windows the path of the plugin can have \
for candidate in "py -3" python3 python; do
  if $candidate -c "import sys; sys.exit(sys.version_info < (3, 11))" </dev/null >/dev/null 2>&1; then
    if [ "$1" = "--python" ]; then
      exec $candidate -c "import sys; print(sys.executable, sys.version.split()[0])"
    fi
    exec $candidate -X utf8 "$here/akasha_run.py" hook --event "$1"
  fi
done
[ "$1" = "--python" ] && exit 1
reason="Akasha needs Python 3.11 or higher for its hooks and found none (py -3, python3, python). Ask the person to install it, then to restart the agent app."
case "$1" in
  SessionStart|UserPromptSubmit) echo "[AKASHA] $reason" ;;
  PreToolUse)
    top=$(git rev-parse --show-toplevel 2>/dev/null)
    if [ "$2" = "edit" ] && [ -n "$top" ] && [ -f "$top/akasha.toml" ]; then
      echo "$reason Akasha stops each edit until then." >&2
      exit 2
    fi ;;
esac
exit 0
