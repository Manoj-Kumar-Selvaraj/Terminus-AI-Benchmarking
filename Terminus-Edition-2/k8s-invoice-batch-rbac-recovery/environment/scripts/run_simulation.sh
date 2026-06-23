#!/usr/bin/env bash
set -euo pipefail
SCENARIO="${1:-all}"
python3 -m sim.simulate --scenario "$SCENARIO"
