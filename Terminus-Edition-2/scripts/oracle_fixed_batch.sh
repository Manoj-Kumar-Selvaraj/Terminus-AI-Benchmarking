#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CLI="$ROOT/scripts/terminus2_cli.sh"
for t in go-catering-order-adjustment-matcher pl1-cobol-atm-risk-release-router ruby-go-bash-vineyard-club-shipment-credit-router; do
  echo "=== ORACLE $t ==="
  (cd "$ROOT" && bash "$CLI" oracle "./$t") || exit 1
done
echo "ALL FIXED TASKS PASS"
