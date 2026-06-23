#!/usr/bin/env bash
set -euo pipefail

/app/scripts/compile.sh
mkdir -p /app/out
/app/build/lockbox_apply
