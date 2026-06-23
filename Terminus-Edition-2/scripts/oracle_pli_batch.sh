#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
TASKS=(
  pli-retail-batch-trailer-reconciler
  pli-insurance-premium-surcharge-adjudicator
  pli-mainframe-tape-record-integrity-auditor
  pli-canonical-payload-semantic-matcher
  pli-multicurrency-ledger-clearing-processor
  pli-workload-manifest-consistency-auditor
  pli-infrastructure-state-drift-adjudicator
  pli-privilege-mandate-sandbox-classifier
  pli-numeric-directive-rollup-processor
)
for t in "${TASKS[@]}"; do
  echo "======== $t ========"
  if bash scripts/terminus2_cli.sh oracle "./$t"; then
    echo "OK $t"
  else
    echo "FAIL $t" >&2
    exit 1
  fi
done
