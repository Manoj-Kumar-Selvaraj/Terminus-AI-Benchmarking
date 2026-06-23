#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
for task in pli-orbit-downlink-frame-auditor pli-treasury-wire-batch-adjudicator pli-distributed-fragment-ledger-reconciler pli-general-ledger-posting-normalizer \
  pli-retail-batch-trailer-reconciler pli-insurance-premium-surcharge-adjudicator pli-mainframe-tape-record-integrity-auditor \
  pli-canonical-payload-semantic-matcher pli-multicurrency-ledger-clearing-processor pli-workload-manifest-consistency-auditor \
  pli-infrastructure-state-drift-adjudicator pli-privilege-mandate-sandbox-classifier pli-numeric-directive-rollup-processor; do
  for n in 04 05 06 07 08 09 10; do
    echo "Operational evidence note $n for batch reconciliation contract." > "$ROOT/$task/environment/docs/audit_support_${n}.md"
  done
  mkdir -p "$ROOT/$task/environment/evidence"
  echo "2026-06-12T12:00:00Z batch mismatch spike on production slice" > "$ROOT/$task/environment/evidence/incident_trace.log"
  cat > "$ROOT/$task/environment/docs/batch_contract.md" <<'EOF'
# Batch Reconciliation Contract
Inputs are pipe-separated value files under `/app/data/`. Policy constants are DCL lines in `/app/src/*_rules.pli`.
Runtime switches are `%SET` directives in `/app/src/*_batch.pli`. The harness reads both decks; do not edit `/app/scripts/*.awk`.
Outputs must land in `/app/out/` with stable column order documented in `/app/docs/operations.md`.
EOF
  cat > "$ROOT/$task/environment/config/defaults.psv" <<'EOF'
setting|value
batch_mode|production
EOF
done
