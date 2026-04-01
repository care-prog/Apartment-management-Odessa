#!/bin/bash
# ProjectOS Hook: check-session-log.sh
# Type: PreToolUse (Bash)
# BLOCKS task commits that don't include SESSION_LOG.md in staged files.
#
# Upgraded from PostToolUse warning to PreToolUse blocker in v3.3.0.
# Only blocks [phase*] commits — health/infra/docs/audit commits are exempt.

# Read tool input from stdin
INPUT=$(cat)

# Only check Bash tool calls
TOOL_NAME=$(echo "$INPUT" | grep -o '"tool_name"[[:space:]]*:[[:space:]]*"[^"]*"' | head -1 | sed 's/.*"tool_name"[[:space:]]*:[[:space:]]*"//;s/"$//')
if [ "$TOOL_NAME" != "Bash" ]; then
  exit 0
fi

# Use python3 to extract command
RESULT=$(HOOK_INPUT="$INPUT" python3 << 'PYEOF'
import os, json, re, subprocess

try:
    data = json.loads(os.environ.get("HOOK_INPUT", "{}"))
    command = data.get("tool_input", {}).get("command", "")
except:
    print("SKIP")
    exit(0)

# Only check git commit commands
if not re.search(r'^\s*git\s+commit\b', command):
    print("SKIP")
    exit(0)

# Only block [phase*] commits — exempt health/infra/docs/audit/setup
if not re.search(r'\[phase\d+\]', command):
    print("SKIP")
    exit(0)

# Check if SESSION_LOG.md is in the staged files
try:
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        capture_output=True, text=True, timeout=5
    )
    staged_files = result.stdout
    if "SESSION_LOG.md" in staged_files:
        print("OK")
    else:
        print("BLOCK")
except:
    # If we can't check, don't block
    print("SKIP")

PYEOF
)

case "$RESULT" in
  SKIP|OK)
    exit 0
    ;;
  BLOCK)
    echo "BLOCKED by ProjectOS: SESSION_LOG.md is not staged in this commit."
    echo ""
    echo "  Rule 3: Every task commit must include SESSION_LOG.md."
    echo "  Add a timestamped task entry to docs/SESSION_LOG.md, then stage it:"
    echo ""
    echo "    git add docs/SESSION_LOG.md"
    echo ""
    echo "  Format (see documentation/ai/REFERENCE.md):"
    echo "    ### [YYYY-MM-DD HH:MM] Task: [name]"
    echo "    **Stage:** [from] → [to]"
    echo "    **What was done:** [bullets]"
    exit 1
    ;;
  *)
    exit 0
    ;;
esac
