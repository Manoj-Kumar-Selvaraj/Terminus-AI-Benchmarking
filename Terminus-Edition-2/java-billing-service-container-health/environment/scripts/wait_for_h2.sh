#!/usr/bin/env bash
set -euo pipefail

deadline=$((SECONDS + 30))
while [ "$SECONDS" -lt "$deadline" ]; do
  if (echo >/dev/tcp/127.0.0.1/9092) 2>/dev/null; then
    exit 0
  fi
  sleep 0.2
done
echo "H2 TCP listener on 9092 did not become ready in time" >&2
exit 1
