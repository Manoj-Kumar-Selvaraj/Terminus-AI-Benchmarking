#!/usr/bin/env bash
set -Eeuo pipefail
bash "/steps/milestone_3/solution/solve3.sh"
python3 - <<'PY'
from pathlib import Path

p = Path("/app/infra/modules/ec2/module.py")
s = p.read_text()
needle = """                + str(subnet.get("id"))
            )
    if errs:"""
insert = """                + str(subnet.get("id"))
            )
    for v in c.get("ebs_volumes", []):
        if not v.get("encrypted") or not v.get("kms_key_alias"):
            errs.append("unencrypted or unscoped ebs volume: " + str(v.get("name")))
    if errs:"""
if needle not in s:
    raise SystemExit("m4 validate anchor missing")
s = s.replace(needle, insert, 1)

broken = """def _ebs(c, inst):
    return []"""

fixed = """def _ebs(c, inst):
    return [
        {
            "id": _id("vol", i["id"], v["name"]),
            "instance_id": i["id"],
            "name": v["name"],
            "size_gb": v.get("size_gb", 20),
            "encrypted": True,
            "kms_key_alias": v["kms_key_alias"],
            "delete_on_termination": bool(v.get("delete_on_termination", False)),
            "orphaned": False,
            "tags": {
                "Application": c.get("app"),
                "VolumeRole": v["name"],
                "ManagedBy": "terraform-aws-ec2-module",
            },
        }
        for i in inst
        for v in c.get("ebs_volumes", [])
    ]"""

if broken not in s:
    raise SystemExit("_ebs anchor missing")
s = s.replace(broken, fixed, 1)
p.write_text(s)
PY
