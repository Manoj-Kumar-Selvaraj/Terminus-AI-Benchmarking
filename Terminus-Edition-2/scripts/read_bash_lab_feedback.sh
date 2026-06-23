#!/usr/bin/env bash
set -euo pipefail
FB=$(ls -dt /tmp/feedback_c03df315* 2>/dev/null | head -1)
echo "FB=$FB"
echo "=== agent_review ==="
cat "$FB/agent_review.txt" 2>/dev/null || echo "(missing)"
echo "=== notes ==="
cat "$FB/notes.txt" 2>/dev/null || echo "(missing)"
