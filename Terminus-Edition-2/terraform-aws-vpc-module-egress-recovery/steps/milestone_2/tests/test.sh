#!/bin/bash
# Omit -e so pytest failures reach the reward if/else block below.
set -uo pipefail
mkdir -p /logs/verifier
echo 0 > /logs/verifier/reward.txt
export APP_DIR="${APP_DIR:-/app}"

if [ "$PWD" = "/" ]; then
    echo "Error: No working directory set. Please set a WORKDIR in your Dockerfile."
    exit 1
fi

mkdir -p /app/bin
/usr/local/go/bin/go build -o /app/bin/vpcsim /app/cmd/vpcsim

pytest -q -rA --disable-warnings /tests/test_m2.py

if [ $? -eq 0 ]; then
    echo 1 > /logs/verifier/reward.txt
else
    echo 0 > /logs/verifier/reward.txt
fi
