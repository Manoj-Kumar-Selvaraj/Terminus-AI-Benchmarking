#!/usr/bin/env bash
set -uo pipefail
if [ "$PWD" = "/" ]; then
  echo "Error: No working directory set. Please set a WORKDIR in your Dockerfile."
  exit 1
fi
mkdir -p /logs/verifie
echo 0 > /logs/verifier/reward.txt

# Requires pytest-json-ctrf (installed in environment/Dockerfile)
# Omit -e so pytest failures reach the reward if/else block below.
python3 -m pytest --ctrf /logs/verifier/ctrf.json /tests/test_m1.py -rA
exit_code=$?

if [ $exit_code -eq 0 ]; then
  echo 1 > /logs/verifier/reward.txt
else
  echo 0 > /logs/verifier/reward.txt
fi
