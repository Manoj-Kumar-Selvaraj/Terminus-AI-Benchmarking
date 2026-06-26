#!/bin/bash
set -euo pipefail
for kind in leases database-users pools journal audit; do
  echo "== $kind =="
  /opt/task-tools/vault-db-runtime inspect "$kind" || true
done
