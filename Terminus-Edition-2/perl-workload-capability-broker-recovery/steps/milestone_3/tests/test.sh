#!/usr/bin/env bash
set -uo pipefail
if [ "$PWD" = "/" ]; then echo "Error: No working directory set."; exit 1; fi
mkdir -p /logs/verifier
echo 0 > /logs/verifier/reward.txt
export APP_ROOT=/app
export PERL5LIB="/tests:/app/lib"
perl /tests/test_m3.t
rc=$?
if [ "$rc" -eq 0 ]; then
    echo 1 > /logs/verifier/reward.txt
else
    echo 0 > /logs/verifier/reward.txt
fi
