#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
for t in go-airport-gate-baggage-hold-release go-coldchain-pallet-hold-release go-datacenter-rack-hold-release go-rail-yard-freight-hold-release; do
  echo "=== $t ==="
  ./scripts/terminus2_cli.sh oracle "./$t" 2>&1 | tail -10
done
