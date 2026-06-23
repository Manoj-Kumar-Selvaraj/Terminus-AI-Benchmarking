#!/usr/bin/env bash
OUT="/mnt/d/Manoj/Projects/Portfolio/TerminalBench/Terminus-Edition-2/Revision-ChatGpt/portal_feedback"
mkdir -p "$OUT"
for d in /tmp/feedback_*20260608*; do
  [ -d "$d" ] || continue
  base=$(basename "$d")
  rm -rf "$OUT/full_${base}"
  cp -r "$d" "$OUT/full_${base}"
done
ls -d "$OUT"/full_* 2>/dev/null || true
