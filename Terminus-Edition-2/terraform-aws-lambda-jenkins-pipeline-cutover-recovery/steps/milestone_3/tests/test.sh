#!/bin/bash
set -uo pipefail
if [ "$PWD" = "/" ]; then
    echo "Error: No working directory set. Please set a WORKDIR in your Dockerfile."
    exit 1
fi
mkdir -p /logs/verifier
echo 0 > /logs/verifier/reward.txt
/opt/verifier/bin/python3 -m pytest --ctrf /logs/verifier/ctrf.json /tests/test_m3.py -rA
rc=$?
if [ "$rc" -eq 0 ]; then
    echo 1 > /logs/verifier/reward.txt
else
    echo 0 > /logs/verifier/reward.txt
fi
