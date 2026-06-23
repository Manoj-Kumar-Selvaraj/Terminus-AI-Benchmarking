#!/usr/bin/env bash
set -euo pipefail
cat > /app/config/application.properties <<'EOF'
billing.server.port=8080
billing.datasource.url=jdbc:h2:tcp://127.0.0.1:9092/./billing
billing.datasource.user=sa
billing.datasource.password=
billing.pool.max=5
billing.migration.seconds=8
billing.container.memory.mb=256
EOF
