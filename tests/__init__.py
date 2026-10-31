import os

# The tests run the same inside and outside Claude Code: the session of the agent engine changes what counts
for name in ("CLAUDE_CODE_SESSION_ID", "CLAUDECODE"):
    os.environ.pop(name, None)
