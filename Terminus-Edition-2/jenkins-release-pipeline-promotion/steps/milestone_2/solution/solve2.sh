#!/usr/bin/env bash
set -Eeuo pipefail
cat > /app/ci/pipeline_config.json <<'JSON'
{
  "credentialBindings": {
    "staging": "cred-staging",
    "production": "cred-production"
  },
  "workspace": {
    "parallelIsolation": true,
    "cacheKeyIncludesAxis": true
  },
  "promotionGate": {
    "scanSource": "branch_tip",
    "requiredStatus": "PASS"
  },
  "rollback": {
    "strategy": "rebuild_head",
    "preservePriorDigest": false
  },
  "compat": {
    "manifestSchema": "v1",
    "stageNames": [
      "Build",
      "Integration",
      "Quality Gate",
      "Promote",
      "Rollback"
    ]
  }
}
JSON
