#!/bin/bash
set -euo pipefail
mkdir -p /app/build /app/out
cobc -x -free -O2 -o /app/build/atm_release_router /app/src/atm_release_router.cbl
/app/build/atm_release_router