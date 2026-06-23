#!/usr/bin/env bash
set -euo pipefail

# Primary harness entrypoint. The full milestone 2 oracle implementation lives in solve2.sh
# so local preflight tools that invoke per-milestone solution names see the same patch.
bash "$(dirname "$0")/solve2.sh"
