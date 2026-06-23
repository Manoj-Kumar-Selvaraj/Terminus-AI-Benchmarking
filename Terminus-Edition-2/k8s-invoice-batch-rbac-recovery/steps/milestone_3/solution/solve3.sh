#!/usr/bin/env bash
set -euo pipefail
cat > /app/manifests/role.yaml <<'YAML'
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: invoice-batch-role
  namespace: billing-batch
  labels:
    app: invoice-nightly-batch
rules:
  - apiGroups: [""]
    resources: ["configmaps"]
    resourceNames: ["invoice-batch-config"]
    verbs: ["get"]
  - apiGroups: [""]
    resources: ["secrets"]
    verbs: ["create", "get"]
YAML
