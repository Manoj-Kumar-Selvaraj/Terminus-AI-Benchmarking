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

mkdir -p "${APP_DIR}/bin"
(cd "${APP_DIR}" && /usr/local/go/bin/go build -o "${APP_DIR}/bin/vpc-recover" ./cmd/vpcrecover)

pytest -q -rA --disable-warnings /tests/test_m5.py

if [ $? -eq 0 ]; then
    echo 1 > /logs/verifier/reward.txt
else
    echo 0 > /logs/verifier/reward.txt
fi
