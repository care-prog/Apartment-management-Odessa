#!/bin/bash
# ProjectOS Hook: check-claude-integrity.sh
# Type: PreToolUse (Edit, Write)
# Blocks edits that remove key structural sections from CLAUDE.md.
#
# Protected sections: ## STOP, ## Rules, ## Workflows
# Updated in v3.3.0: File Formats moved to REFERENCE.md, STOP section added.

# Read tool input from stdin
INPUT=$(cat)

# Extract tool name and file path
RESULT=$(echo "$INPUT" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    tool_name = data.get('tool_name', '')
    tool_input = data.get('tool_input', {})
    file_path = tool_input.get('file_path', '')
    print(f'{tool_name}|{file_path}')
except:
    print('|')
" 2>/dev/null)

TOOL_NAME=$(echo "$RESULT" | cut -d'|' -f1)
FILE_PATH=$(echo "$RESULT" | cut -d'|' -f2)

# Only check Edit and Write on CLAUDE.md
if [ "$TOOL_NAME" != "Edit" ] && [ "$TOOL_NAME" != "Write" ]; then
  exit 0
fi

if ! echo "$FILE_PATH" | grep -qE '/CLAUDE\.md$'; then
  exit 0
fi

PROTECTED_SECTIONS_STR="## STOP|## Rules|## Workflows"

if [ "$TOOL_NAME" = "Edit" ]; then
  # For Edit: check if old_string contains a protected section header
  # and new_string does NOT contain it (i.e., removing the section)
  REMOVED=$(echo "$INPUT" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    tool_input = data.get('tool_input', {})
    old_string = tool_input.get('old_string', '')
    new_string = tool_input.get('new_string', '')

    protected = ['## STOP', '## Rules', '## Workflows']
    removed = []
    for section in protected:
        if section in old_string and section not in new_string:
            removed.append(section)
    if removed:
        print('|'.join(removed))
    else:
        print('')
except:
    print('')
" 2>/dev/null)

  if [ -n "$REMOVED" ]; then
    echo "BLOCKED by ProjectOS: Cannot remove protected CLAUDE.md sections."
    echo ""
    echo "  Sections being removed:"
    echo "$REMOVED" | tr '|' '\n' | while read -r s; do
      echo "    $s"
    done
    echo ""
    echo "  These sections are required for ProjectOS to function."
    echo "  You may edit content within these sections, but the section headers must remain."
    exit 1
  fi
fi

if [ "$TOOL_NAME" = "Write" ]; then
  # For Write: check if the new content contains all protected sections
  MISSING=$(echo "$INPUT" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    tool_input = data.get('tool_input', {})
    content = tool_input.get('content', '')

    protected = ['## STOP', '## Rules', '## Workflows']
    missing = []
    for section in protected:
        if section not in content:
            missing.append(section)
    if missing:
        print('|'.join(missing))
    else:
        print('')
except:
    print('')
" 2>/dev/null)

  if [ -n "$MISSING" ]; then
    echo "BLOCKED by ProjectOS: CLAUDE.md rewrite is missing required sections."
    echo ""
    echo "  Missing sections:"
    echo "$MISSING" | tr '|' '\n' | while read -r s; do
      echo "    $s"
    done
    echo ""
    echo "  CLAUDE.md must always contain: ## STOP, ## Rules, ## Workflows"
    echo "  Use Edit instead of Write to modify specific parts without losing structure."
    exit 1
  fi
fi

exit 0
