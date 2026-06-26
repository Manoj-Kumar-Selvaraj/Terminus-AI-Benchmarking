#!/usr/bin/env bash
set -uo pipefail
mkdir -p /logs/verifier
echo 0 > /logs/verifier/reward.txt
export APP_DIR="${APP_DIR:-/app}"
pytest -q -rA --disable-warnings --ctrf /logs/verifier/ctrf.json /tests/test_m3.py
rc=$?
if [ "$rc" -eq 0 ]; then
  echo 1 > /logs/verifier/reward.txt
else
  echo 0 > /logs/verifier/reward.txt
fi
