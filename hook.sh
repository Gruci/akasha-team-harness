#!/bin/sh
# Run a hook of Akasha with Python 3.11 or higher: the first python on PATH can be older, or the stub of the
# Microsoft Store. `hook.sh --python` prints the Python that the hooks use, for akasha doctor.
# The script keeps the path of the Python that it found in the file .python beside itself, so that each later hook
# starts Python once. The file is a cache: where the script cannot write it, or after an update of the plugin, the
# script finds Python again. When that Python is gone, or too old (akasha_run.py ends with 126 then), also.
# Without such a Python, the session start and the prompt tell it to the agent, and an edit in a repository that uses
# Akasha stops, so that no step goes around Akasha without notice. Shell commands still run, to repair it.
here=$(dirname "$(printf '%s' "$0" | tr '\\' '/')")       # on Windows the path of the plugin can have \
kept="$here/.python"                                      # no folder in the home of the person
if [ "$1" != "--python" ] && [ -r "$kept" ]; then
  python=$(tr -d '\r' < "$kept" 2>/dev/null)             # a file from Windows can end with \r
  if [ -n "$python" ] && [ -f "$python" ]; then
    AKASHA_KEPT_PYTHON=1 "$python" -X utf8 "$here/akasha_run.py" hook --event "$1"
    code=$?
    [ "$code" -ne 126 ] && [ "$code" -ne 127 ] && exit "$code"
  fi
fi
for candidate in "py -3" python3 python; do
  found=$($candidate -c "import sys; sys.version_info >= (3, 11) and print(sys.executable.replace(chr(92), '/'))" </dev/null 2>/dev/null)
  if [ -n "$found" ]; then
    if [ "$1" = "--python" ]; then
      exec $candidate -c "import sys; print(sys.executable, sys.version.split()[0])"
    fi
    # Write beside, then rename: a hook that runs at the same time never reads half a path
    tmp="$kept.$$"
    { printf '%s\n' "$found" > "$tmp" && mv -f "$tmp" "$kept"; } 2>/dev/null || rm -f "$tmp" 2>/dev/null
    exec $candidate -X utf8 "$here/akasha_run.py" hook --event "$1"
  fi
done
[ "$1" = "--python" ] && exit 1
reason="Akasha needs Python 3.11 or higher for its hooks and found none (py -3, python3, python). Ask the person to install it, then to restart the agent app."
case "$1" in
  SessionStart|UserPromptSubmit) echo "[AKASHA] $reason" ;;
  PreToolUse)
    top=$(git rev-parse --show-toplevel 2>/dev/null)
    if [ "$2" = "edit" ] && [ -n "$top" ] && { [ -f "$top/akasha.toml" ] || [ -f "$top/.github/akasha.toml" ]; }; then
      echo "$reason Akasha stops each edit until then." >&2
      exit 2
    fi ;;
esac
exit 0
