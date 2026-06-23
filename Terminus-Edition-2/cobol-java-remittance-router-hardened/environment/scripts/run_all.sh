#!/usr/bin/env bash
set -euo pipefail

if ! (exec 3<>/dev/tcp/127.0.0.1/8080) 2>/dev/null; then
    java -cp /app/build RuleServer >/tmp/rule-server.log 2>&1 &
    for _ in $(seq 1 20); do
        if (exec 3<>/dev/tcp/127.0.0.1/8080) 2>/dev/null; then
            break
        fi
        sleep 0.1
    done
fi

/app/scripts/run_batch.sh
/app/scripts/run_adapter.sh
