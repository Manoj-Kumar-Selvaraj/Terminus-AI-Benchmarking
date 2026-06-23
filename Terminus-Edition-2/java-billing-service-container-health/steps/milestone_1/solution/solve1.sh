#!/usr/bin/env bash
set -euo pipefail
# Milestone 1 only repairs datasource configuration. The verifier starts H2 and
# the billing service via run_service.sh, so no restart or recompile is needed here.
cat > /app/config/application.properties <<'EOF'
billing.server.port=8080
billing.datasource.url=jdbc:h2:tcp://127.0.0.1:9092/./billing
billing.datasource.user=sa
billing.datasource.password=
billing.pool.max=5
billing.migration.seconds=8
billing.container.memory.mb=256
EOF
