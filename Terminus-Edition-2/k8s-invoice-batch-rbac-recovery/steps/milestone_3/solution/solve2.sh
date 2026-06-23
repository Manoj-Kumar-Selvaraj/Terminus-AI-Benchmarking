#!/usr/bin/env bash
set -euo pipefail
python3 - <<'PY'
from pathlib import Path
import yaml

path = Path("/app/manifests/cronjob.yaml")
docs = list(yaml.safe_load_all(path.read_text(encoding="utf-8")))
cronjob = docs[0]
cronjob.setdefault("spec", {})["concurrencyPolicy"] = "Forbid"
path.write_text(yaml.safe_dump(cronjob, sort_keys=False), encoding="utf-8")
PY
