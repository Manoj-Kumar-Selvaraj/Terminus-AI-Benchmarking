#!/bin/bash
set -uo pipefail
mkdir -p /logs/verifier
echo 0 > /logs/verifier/reward.txt
pytest_status=1
trap 'exit $pytest_status' EXIT
if [ "$PWD" = "/" ]; then
    echo "Error: No working directory set. Please set a WORKDIR in your Dockerfile before running this script."
    exit 1
fi
python3 -m pytest --ctrf /logs/verifier/ctrf.json /tests/test_m2.py -rA
pytest_status=$?
test $pytest_status -eq 0
if [ $? -eq 0 ]; then
    echo 1 > /logs/verifier/reward.txt
else
    echo 0 > /logs/verifier/reward.txt
fi