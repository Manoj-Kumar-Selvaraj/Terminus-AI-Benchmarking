#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Milestone 3 is cumulative; solve3.sh installs all logic required up to this step.
bash "$SCRIPT_DIR/solve3.sh"
