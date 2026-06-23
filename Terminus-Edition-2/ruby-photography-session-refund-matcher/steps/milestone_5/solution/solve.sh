#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Milestone 5 is cumulative; solve5.sh installs all logic required up to this step.
bash "$SCRIPT_DIR/solve5.sh"
