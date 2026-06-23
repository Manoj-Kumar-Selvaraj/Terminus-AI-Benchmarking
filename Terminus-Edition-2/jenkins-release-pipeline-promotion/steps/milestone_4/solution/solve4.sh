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
    "scanSource": "built_artifact",
    "requiredStatus": "PASS"
  },
  "rollback": {
    "strategy": "redeploy_prior_digest",
    "preservePriorDigest": true
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
