#!/bin/bash
# Omit -e so pytest failures reach the reward if/else block below.
set -uo pipefail
mkdir -p /logs/verifier
echo 0 > /logs/verifier/reward.txt
export APP_DIR="${APP_DIR:-/app}"
export TF_CLI_CONFIG_FILE="${TF_CLI_CONFIG_FILE:-/opt/terraformrc}"
export AWS_ACCESS_KEY_ID="${AWS_ACCESS_KEY_ID:-test}"
export AWS_SECRET_ACCESS_KEY="${AWS_SECRET_ACCESS_KEY:-test}"
export AWS_EC2_METADATA_DISABLED="true"
if [ "$PWD" = "/" ]; then
    echo "Error: No working directory set. Please set a WORKDIR in your Dockerfile."
    exit 1
fi
pytest -q -rA --disable-warnings --ctrf /logs/verifier/ctrf.json /tests/test_outputs.py
if [ $? -eq 0 ]; then
    echo 1 > /logs/verifier/reward.txt
else
    echo 0 > /logs/verifier/reward.txt
fi