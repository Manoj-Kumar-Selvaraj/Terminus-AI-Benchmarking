#!/usr/bin/env bash
FB=$(ls -dt /tmp/feedback_cd26e7aa* 2>/dev/null | head -1)
echo "Using: $FB"
ls -la "$FB"
echo ""
echo "=== notes.txt ==="
cat "$FB/notes.txt"
echo ""
echo "=== all top-level files ==="
find "$FB" -maxdepth 2 -type f
echo ""
echo "=== grep agent/difficulty/review ==="
grep -riE "agent review|Agent Review|agent_review|verifier_did_not_run|difficulty|Summary \(difficulty|Quality check|test quality|Test Quality" "$FB" 2>/dev/null | head -60
echo ""
echo "=== json files in feedback root ==="
find "$FB" -maxdepth 1 -name "*.json" -exec echo "--- {} ---" \; -exec cat {} \;
