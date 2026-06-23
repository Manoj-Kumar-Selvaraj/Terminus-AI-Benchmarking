#!/bin/bash
mkdir -p /logs/verifie
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
pytest -q -rA "$SCRIPT_DIR/test_m1.py"
exit_code=$?
if [ "$exit_code" -eq 0 ]; then
    echo 1 > /logs/verifier/reward.txt
else
    echo 0 > /logs/verifier/reward.txt
fi
