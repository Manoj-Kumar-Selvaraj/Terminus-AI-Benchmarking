#!/usr/bin/env bash
set -euo pipefail
/app/scripts/compile.sh
exec /app/build/batch
