#!/usr/bin/env bash
set -euo pipefail
test -s /app/data/tickets.csv
test -s /app/data/credits.csv
echo "input validation ok"
