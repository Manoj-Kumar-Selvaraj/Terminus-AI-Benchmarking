#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TASK_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
bash "$TASK_ROOT/milestone_1/solution/solve1.sh"
bash "$TASK_ROOT/milestone_2/solution/solve2.sh"
bash "$SCRIPT_DIR/solve3.sh"
