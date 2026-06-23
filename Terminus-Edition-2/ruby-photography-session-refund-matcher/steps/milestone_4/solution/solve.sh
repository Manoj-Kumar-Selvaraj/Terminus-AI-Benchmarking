#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Milestone 4 is cumulative; solve4.sh installs all logic required up to this step.
bash "$SCRIPT_DIR/solve4.sh"
