#!/bin/bash
# ProjectOS Hook: check-commit-format.sh
# Type: PreToolUse (Bash)
# Blocks git commits that don't follow the required format.
#
# Valid formats:
#   [phase1] task: description
#   [phase2] built: description
#   [health] check: description
#   [audit] daily: description
#   [infra] upgrade: description
#   [fix] bug: description
#   [docs] updated: description

# Read tool input from stdin
INPUT=$(cat)

# Only check Bash tool calls
TOOL_NAME=$(echo "$INPUT" | grep -o '"tool_name"[[:space:]]*:[[:space:]]*"[^"]*"' | head -1 | sed 's/.*"tool_name"[[:space:]]*:[[:space:]]*"//;s/"$//')
if [ "$TOOL_NAME" != "Bash" ]; then
  exit 0
fi

# Use python3 to extract command and validate commit format
# Pass INPUT via env var since heredoc takes over stdin
RESULT=$(HOOK_INPUT="$INPUT" python3 << 'PYEOF'
import os, json, re

try:
    data = json.loads(os.environ.get("HOOK_INPUT", "{}"))
    command = data.get("tool_input", {}).get("command", "")
except:
    print("SKIP")
    sys.exit(0)

# Only check git commit commands
if not re.search(r'^\s*git\s+commit\b', command):
    print("SKIP")
    sys.exit(0)

# Extract commit message from -m flag
msg = None

# Try double-quoted: -m "message"
m = re.search(r'-m\s+"((?:[^"\\]|\\.)*)"', command)
if m:
    msg = m.group(1).split("\n")[0]

# Try single-quoted: -m 'message'
if not msg:
    m = re.search(r"-m\s+'((?:[^'\\]|\\.)*)'", command)
    if m:
        msg = m.group(1).split("\n")[0]

# Try heredoc: -m "$(cat <<'EOF' ... EOF )"
if not msg:
    m = re.search(r'-m\s+"\$\(cat\s+<<', command)
    if m:
        lines = command.split("\n")
        for i, line in enumerate(lines):
            if i > 0 and "EOF" not in line and "Co-Authored" not in line and line.strip():
                msg = line.strip()
                break

if not msg:
    print("SKIP")
    sys.exit(0)

# Validate format: [tag] verb: description
pattern = r'^\[(phase[0-9]+|health|audit|infra|fix|docs|setup)\]\s+[a-z]+:\s+.+'
if re.match(pattern, msg):
    print("OK")
else:
    print("BLOCK:" + msg)
PYEOF
)

case "$RESULT" in
  SKIP|OK)
    exit 0
    ;;
  BLOCK:*)
    MSG="${RESULT#BLOCK:}"
    echo "BLOCKED by ProjectOS: Invalid commit message format."
    echo ""
    echo "  Got: $MSG"
    echo ""
    echo "  Required format: [tag] verb: description"
    echo "  Valid tags: [phase1], [phase2], ..., [health], [audit], [infra], [fix], [docs], [setup]"
    echo "  Examples:"
    echo "    [phase1] built: user auth flow"
    echo "    [fix] resolved: login redirect loop"
    echo "    [health] check: daily health results"
    echo "    [audit] daily: code quality audit completed"
    echo "    [docs] updated: session log"
    exit 1
    ;;
  *)
    # Unknown result — allow
    exit 0
    ;;
esac
