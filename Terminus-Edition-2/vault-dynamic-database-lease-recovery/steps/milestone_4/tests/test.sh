#!/bin/bash
set -uo pipefail

mkdir -p /logs/verifier
echo 0 > /logs/verifier/reward.txt
if [ "$PWD" = "/" ]; then
  echo "Error: No working directory set. Please set a WORKDIR in your Dockerfile before running this script."
  exit 1
fi
/usr/local/go/bin/go build -o /tmp/lease-agent-verifier ./cmd/lease-agent
/usr/local/go/bin/go build -o /tmp/payment-api-verifier ./cmd/payment-api
export LEASE_AGENT_TEST_BIN=/tmp/lease-agent-verifier
export PAYMENT_API_TEST_BIN=/tmp/payment-api-verifier
if pytest --help 2>/dev/null | grep -q -- '--ctrf'; then
  pytest --ctrf /logs/verifier/ctrf.json /tests/test_m4.py -rA
else
  pytest /tests/test_m4.py -rA
fi
status=$?
if [ "$status" -eq 0 ]; then
  echo 1 > /logs/verifier/reward.txt
else
  echo 0 > /logs/verifier/reward.txt
fi
