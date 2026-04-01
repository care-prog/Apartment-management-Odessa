#!/bin/bash
# ProjectOS Hook: check-task-stage-skip.sh
# Type: PreToolUse (Edit)
# Blocks edits to TASK_PIPELINE.md that skip the 🔍 Audit stage.
# A task cannot go from ⚪ To Do directly to 🟡 UI First or later.

# Read tool input from stdin
INPUT=$(cat)

# Only check Edit tool calls
TOOL_NAME=$(echo "$INPUT" | grep -o '"tool_name"[[:space:]]*:[[:space:]]*"[^"]*"' | head -1 | sed 's/.*"tool_name"[[:space:]]*:[[:space:]]*"//;s/"$//')
if [ "$TOOL_NAME" != "Edit" ]; then
  exit 0
fi

# Use python3 to check for stage skipping
RESULT=$(HOOK_INPUT="$INPUT" python3 << 'PYEOF'
import os, json, re

try:
    data = json.loads(os.environ.get("HOOK_INPUT", "{}"))
    tool_input = data.get("tool_input", {})
    file_path = tool_input.get("file_path", "")
    old_string = tool_input.get("old_string", "")
    new_string = tool_input.get("new_string", "")
except:
    print("SKIP")
    exit(0)

# Only check edits to TASK_PIPELINE.md
if "TASK_PIPELINE" not in file_path:
    print("SKIP")
    exit(0)

# Check if old_string has "To Do" and new_string has a stage beyond Audit
old_has_todo = bool(re.search(r'⚪\s*To\s*Do', old_string))
if not old_has_todo:
    print("OK")
    exit(0)

# If we're changing from To Do, the new stage must be Audit
new_has_audit = bool(re.search(r'🔍\s*Audit', new_string))
new_has_todo = bool(re.search(r'⚪\s*To\s*Do', new_string))
new_has_blocked = bool(re.search(r'🔴\s*Blocked', new_string))

# Allow: To Do -> Audit, To Do -> To Do (no change), To Do -> Blocked
if new_has_audit or new_has_todo or new_has_blocked:
    print("OK")
    exit(0)

# Check if any later stage is present
later_stages = [
    r'🟡\s*UI\s*First',
    r'🔵\s*Built',
    r'🟢\s*Tested',
    r'📝\s*Documented',
    r'🟣\s*Deployed',
]
for pattern in later_stages:
    if re.search(pattern, new_string):
        print("BLOCK")
        exit(0)

print("OK")
PYEOF
)

case "$RESULT" in
  SKIP|OK)
    exit 0
    ;;
  BLOCK)
    echo "BLOCKED by ProjectOS: Cannot skip the 🔍 Audit stage."
    echo ""
    echo "  Tasks must go through pre-development audit before UI First."
    echo "  Required flow: ⚪ To Do → 🔍 Audit → 🟡 UI First → ..."
    echo ""
    echo "  To fix: First move the task to 🔍 Audit, run the pre-dev audit,"
    echo "  then move to 🟡 UI First."
    echo ""
    echo "  See documentation/ai/PRE_DEV_AUDIT_PROMPT.md for the audit workflow."
    exit 1
    ;;
  *)
    exit 0
    ;;
esac
