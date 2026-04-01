#!/bin/bash
# ProjectOS Hook Installer
# Merges ProjectOS enforcement hooks into .claude/settings.json
#
# Usage: ./scripts/hooks/install-hooks.sh
# Run from the project root directory.

set -e

# Colors
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
NC='\033[0m'

PROJECT_DIR="$(pwd)"
SETTINGS_DIR="$PROJECT_DIR/.claude"
SETTINGS_FILE="$SETTINGS_DIR/settings.json"

# Ensure .claude directory exists
mkdir -p "$SETTINGS_DIR"

# Define the hooks configuration (v3.3.0 — 8 hooks)
HOOKS_JSON='{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "cat /dev/stdin | bash scripts/hooks/check-commit-format.sh"
          },
          {
            "type": "command",
            "command": "cat /dev/stdin | bash scripts/hooks/check-session-log.sh"
          }
        ]
      },
      {
        "matcher": "Edit",
        "hooks": [
          {
            "type": "command",
            "command": "cat /dev/stdin | bash scripts/hooks/check-dashboard-markers.sh"
          },
          {
            "type": "command",
            "command": "cat /dev/stdin | bash scripts/hooks/check-claude-integrity.sh"
          },
          {
            "type": "command",
            "command": "cat /dev/stdin | bash scripts/hooks/check-task-stage-skip.sh"
          }
        ]
      },
      {
        "matcher": "Write",
        "hooks": [
          {
            "type": "command",
            "command": "cat /dev/stdin | bash scripts/hooks/check-claude-integrity.sh"
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "cat /dev/stdin | bash scripts/hooks/check-git-log-sync.sh"
          },
          {
            "type": "command",
            "command": "cat /dev/stdin | bash scripts/hooks/check-pipeline-update.sh"
          },
          {
            "type": "command",
            "command": "cat /dev/stdin | bash scripts/hooks/check-git-push-reminder.sh"
          }
        ]
      }
    ]
  }
}'

if [ -f "$SETTINGS_FILE" ]; then
  # Merge hooks into existing settings
  MERGED=$(python3 -c "
import json, sys

with open('$SETTINGS_FILE', 'r') as f:
    settings = json.load(f)

hooks = json.loads('''$HOOKS_JSON''')

# Merge hooks — replace the hooks section entirely
settings['hooks'] = hooks['hooks']

print(json.dumps(settings, indent=2))
" 2>/dev/null)

  if [ -n "$MERGED" ]; then
    echo "$MERGED" > "$SETTINGS_FILE"
  else
    echo -e "${YELLOW}Warning: Could not merge into existing settings. Creating new file.${NC}"
    echo "$HOOKS_JSON" | python3 -c "import sys,json; print(json.dumps(json.load(sys.stdin), indent=2))" > "$SETTINGS_FILE"
  fi
else
  # Create new settings file with hooks
  echo "$HOOKS_JSON" | python3 -c "import sys,json; print(json.dumps(json.load(sys.stdin), indent=2))" > "$SETTINGS_FILE"
fi

echo -e "${GREEN}ProjectOS hooks installed successfully (v3.3.0).${NC}"
echo ""
echo -e "  ${CYAN}Hooks added to:${NC} $SETTINGS_FILE"
echo ""
echo -e "  ${CYAN}PreToolUse (BLOCKING):${NC}"
echo "    - check-commit-format.sh (Bash) — commit message format"
echo "    - check-session-log.sh (Bash) — SESSION_LOG in task commits"
echo "    - check-dashboard-markers.sh (Edit) — dashboard marker preservation"
echo "    - check-claude-integrity.sh (Edit, Write) — CLAUDE.md structure"
echo "    - check-task-stage-skip.sh (Edit) — audit stage enforcement"
echo ""
echo -e "  ${CYAN}PostToolUse (WARNING):${NC}"
echo "    - check-git-log-sync.sh (Bash) — GIT_LOG.md after commits"
echo "    - check-pipeline-update.sh (Bash) — TASK_PIPELINE after task commits"
echo "    - check-git-push-reminder.sh (Bash) — push reminder on wrap-up"
