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

python3 - <<'PY'
from pathlib import Path
import yaml

path = Path("/app/manifests/configmap.yaml")
docs = list(yaml.safe_load_all(path.read_text(encoding="utf-8")))
configmap = docs[0]
data = configmap.setdefault("data", {})
data["current_window"] = "WIN-20260612"
path.write_text(yaml.safe_dump(configmap, sort_keys=False), encoding="utf-8")
PY
