#!/usr/bin/env bash
set -euo pipefail
cat > /app/manifests/rolebinding.yaml <<'YAML'
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: invoice-batch-binding
  namespace: billing-batch
  labels:
    app: invoice-nightly-batch
subjects:
  - kind: ServiceAccount
    name: invoice-batch-runner
    namespace: billing-batch
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: invoice-batch-role
YAML
