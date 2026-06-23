#!/bin/bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# This milestone oracle installs the full implementation expected after milestone 2.
bash "$SCRIPT_DIR/solve2.sh"
