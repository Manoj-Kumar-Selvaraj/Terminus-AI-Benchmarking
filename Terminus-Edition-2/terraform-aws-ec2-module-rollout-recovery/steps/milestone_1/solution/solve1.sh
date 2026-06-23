#!/usr/bin/env bash
set -Eeuo pipefail
APP_DIR="${APP_DIR:-/app}"
python3 - <<'PY'
from pathlib import Path

p = Path("/app/infra/modules/ec2/module.py")
s = p.read_text()
needle = "    errs = []\n    if errs:"
insert = """    errs = []
    art = c.get("release_artifact") or {}
    for k in ["ami_id", "commit_sha", "build_id", "user_data_sha256"]:
        if not art.get(k):
            errs.append(f"release_artifact.{k} is required")
    if errs:"""
if needle not in s:
    raise SystemExit("validate_config anchor missing")
s = s.replace(needle, insert, 1)
s = s.replace(
    'def _lt(c):\n'
    '    ami = c.get("ami_catalog", {}).get("latest", "ami-latest")\n'
    '    uds = "latest-bootstrap"\n'
    '    prov = {"commit_sha": "HEAD", "build_id": "latest"}',
    'def _lt(c):\n'
    '    art = c.get("release_artifact") or {}\n'
    '    ami = art.get("ami_id")\n'
    '    uds = art.get("user_data_sha256")\n'
    '    prov = {"commit_sha": art.get("commit_sha"), "build_id": art.get("build_id")}',
)
p.write_text(s)
PY
