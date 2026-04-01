#!/bin/bash
# ProjectOS Hook: check-git-push-reminder.sh
# Type: PostToolUse (Bash)
# Warns to push after wrap-up/session commits.

# Read tool input from stdin
INPUT=$(cat)

# Only check Bash tool calls
TOOL_NAME=$(echo "$INPUT" | grep -o '"tool_name"[[:space:]]*:[[:space:]]*"[^"]*"' | head -1 | sed 's/.*"tool_name"[[:space:]]*:[[:space:]]*"//;s/"$//')
if [ "$TOOL_NAME" != "Bash" ]; then
  exit 0
fi

# Use python3 to check
RESULT=$(HOOK_INPUT="$INPUT" python3 << 'PYEOF'
import os, json, re

try:
    data = json.loads(os.environ.get("HOOK_INPUT", "{}"))
    command = data.get("tool_input", {}).get("command", "")
    stdout = data.get("stdout", "")
except:
    print("SKIP")
    exit(0)

# Only check git commit commands
if not re.search(r'^\s*git\s+commit\b', command):
    print("SKIP")
    exit(0)

# Skip if commit failed
if "nothing to commit" in stdout or "error" in stdout.lower():
    print("SKIP")
    exit(0)

# Check if the commit message suggests a session wrap-up
wrap_keywords = ["session", "wrap", "summary", "end of", "done for", "final"]
msg_lower = command.lower()
for kw in wrap_keywords:
    if kw in msg_lower:
        print("WARN")
        exit(0)

# Also check for [docs] updated: session log pattern
if re.search(r'\[docs\].*session', msg_lower):
    print("WARN")
    exit(0)

print("SKIP")
PYEOF
)

case "$RESULT" in
  SKIP|OK)
    exit 0
    ;;
  WARN)
    echo ""
    echo "⚠️  ProjectOS: This looks like a session wrap-up commit."
    echo "   Rule 4: Push to Git at end of EVERY session."
    echo "   Don't forget to run: git push"
    echo ""
    exit 0
    ;;
  *)
    exit 0
    ;;
esac
