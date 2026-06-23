#!/usr/bin/env bash
set -euo pipefail

# Primary harness entrypoint. The full milestone 3 oracle implementation lives in solve3.sh
# so local preflight tools that invoke per-milestone solution names see the same patch.
bash "$(dirname "$0")/solve3.sh"
