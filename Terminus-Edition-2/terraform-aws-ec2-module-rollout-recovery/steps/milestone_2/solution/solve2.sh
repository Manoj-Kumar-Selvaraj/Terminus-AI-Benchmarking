#!/usr/bin/env bash
set -Eeuo pipefail
bash "/steps/milestone_1/solution/solve1.sh"
python3 - <<'PY'
from pathlib import Path

p = Path("/app/infra/modules/ec2/module.py")
s = p.read_text()
needle = """            errs.append(f"release_artifact.{k} is required")
    if errs:"""
insert = """            errs.append(f"release_artifact.{k} is required")
    for subnet in c.get("subnets", []):
        if subnet.get("tier") != "private_app":
            errs.append(
                "ec2 module may only target private_app subnets: "
                + str(subnet.get("id"))
            )
    if errs:"""
if needle not in s:
    raise SystemExit("m2 validate anchor missing")
s = s.replace(needle, insert, 1)

broken_sg = """def _sg(c):
    return {
        "id": _id("sg", c.get("app"), c.get("environment")),
        "ingress": [
            {
                "protocol": "tcp",
                "from_port": 22,
                "to_port": 22,
                "cidr_blocks": ["0.0.0.0/0"],
            }
        ],
        "egress": [],
    }"""

fixed_sg = """def _sg(c):
    return {
        "id": _id("sg", c.get("app"), c.get("environment")),
        "ingress": [
            {
                "protocol": "tcp",
                "from_port": c.get("service_port", 8080),
                "to_port": c.get("service_port", 8080),
                "source_security_group_id": c.get("alb_security_group_id"),
            }
        ],
        "egress": [
            {
                "protocol": "tcp",
                "from_port": 443,
                "to_port": 443,
                "prefix_list_ids": c.get("endpoint_prefix_lists", []),
            }
        ],
    }"""

if broken_sg not in s:
    raise SystemExit("_sg anchor missing")
s = s.replace(broken_sg, fixed_sg, 1)
s = s.replace('"public_ip_associated": True,', '"public_ip_associated": False,', 1)
p.write_text(s)
PY
