#!/usr/bin/env bash

mkdir -p /logs/verifier
echo 0 > /logs/verifier/reward.txt

python3 -m pytest /tests/test_m3.py -rA
PYTEST_RC=$?
if [ "$PYTEST_RC" -eq 0 ]; then
    echo 1 > /logs/verifier/reward.txt
else
    echo 0 > /logs/verifier/reward.txt
fi
