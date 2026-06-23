#!/bin/bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# This milestone oracle installs the full implementation expected after milestone 4.
bash "$SCRIPT_DIR/solve4.sh"
