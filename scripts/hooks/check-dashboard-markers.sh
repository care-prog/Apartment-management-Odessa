#!/bin/bash
# ProjectOS Hook: check-dashboard-markers.sh
# Type: PreToolUse (Edit)
# Blocks edits that remove DASHBOARD markers from project files.
#
# Protected markers: <!-- DASHBOARD:*:START --> and <!-- DASHBOARD:*:END -->

# Read tool input from stdin
INPUT=$(cat)

# Only check Edit tool calls
TOOL_NAME=$(echo "$INPUT" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    print(data.get('tool_name', ''))
except:
    print('')
" 2>/dev/null)

if [ "$TOOL_NAME" != "Edit" ]; then
  exit 0
fi

# Extract old_string and new_string
RESULT=$(echo "$INPUT" | python3 -c "
import sys, json, re
try:
    data = json.load(sys.stdin)
    tool_input = data.get('tool_input', {})
    old_string = tool_input.get('old_string', '')
    new_string = tool_input.get('new_string', '')

    # Find all DASHBOARD markers in old_string
    old_markers = set(re.findall(r'<!-- DASHBOARD:\w+:(START|END) -->', old_string))
    new_markers = set(re.findall(r'<!-- DASHBOARD:\w+:(START|END) -->', new_string))

    # Check if any markers in old_string are missing from new_string
    old_full = re.findall(r'<!-- DASHBOARD:\w+:(?:START|END) -->', old_string)
    new_full = re.findall(r'<!-- DASHBOARD:\w+:(?:START|END) -->', new_string)

    removed = []
    for marker in old_full:
        if marker not in new_full:
            removed.append(marker)

    if removed:
        print('REMOVED:' + '|'.join(removed))
    else:
        print('OK')
except Exception as e:
    print('OK')
" 2>/dev/null)

if echo "$RESULT" | grep -q '^REMOVED:'; then
  MARKERS=$(echo "$RESULT" | sed 's/^REMOVED://' | tr '|' '\n')
  echo "BLOCKED by ProjectOS: Dashboard markers cannot be removed."
  echo ""
  echo "  The following markers would be deleted by this edit:"
  echo "$MARKERS" | while read -r m; do
    echo "    $m"
  done
  echo ""
  echo "  These markers are required for the dashboard to render correctly."
  echo "  Edit the content BETWEEN the markers instead."
  exit 1
fi

exit 0
