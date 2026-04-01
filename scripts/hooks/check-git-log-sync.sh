#!/bin/bash
# ProjectOS Hook: check-git-log-sync.sh
# Type: PostToolUse (Bash)
# Warns if GIT_LOG.md was not included in a git commit.

# Read tool input from stdin
INPUT=$(cat)

# Only check Bash tool calls
TOOL_NAME=$(echo "$INPUT" | grep -o '"tool_name"[[:space:]]*:[[:space:]]*"[^"]*"' | head -1 | sed 's/.*"tool_name"[[:space:]]*:[[:space:]]*"//;s/"$//')
if [ "$TOOL_NAME" != "Bash" ]; then
  exit 0
fi

# Use python3 to check
RESULT=$(HOOK_INPUT="$INPUT" python3 << 'PYEOF'
import os, json, re, subprocess

try:
    data = json.loads(os.environ.get("HOOK_INPUT", "{}"))
    command = data.get("tool_input", {}).get("command", "")
    stdout = data.get("stdout", "")
except:
    print("SKIP")
    exit(0)

# Only check successful git commit commands
if not re.search(r'^\s*git\s+commit\b', command):
    print("SKIP")
    exit(0)

# Skip if commit failed
if "nothing to commit" in stdout or "error" in stdout.lower():
    print("SKIP")
    exit(0)

# Check if GIT_LOG.md was in the committed files
try:
    result = subprocess.run(
        ["git", "diff", "--name-only", "HEAD~1", "HEAD"],
        capture_output=True, text=True, timeout=5
    )
    committed_files = result.stdout
    if "GIT_LOG.md" in committed_files:
        print("OK")
    else:
        print("WARN")
except:
    print("SKIP")

PYEOF
)

case "$RESULT" in
  SKIP|OK)
    exit 0
    ;;
  WARN)
    echo ""
    echo "⚠️  ProjectOS: docs/GIT_LOG.md was not updated in this commit."
    echo "   Rule 17 requires GIT_LOG.md to be updated after every commit."
    echo "   Please add the commit entry to docs/GIT_LOG.md now."
    echo ""
    exit 0
    ;;
  *)
    exit 0
    ;;
esac
