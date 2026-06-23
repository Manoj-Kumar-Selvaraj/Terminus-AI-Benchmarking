#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
bash "/steps/milestone_3/solution/solve3.sh"
python3 - <<'PY'
from pathlib import Path
p = Path("/app/infra/modules/vpc/module.py")
s = p.read_text()
needle = "    outputs = {"
flow_block = '''    flow = {
        "id": _id("fl", env, "vpc"),
        "traffic_type": "ALL",
        "destination": c.get("flow_log", {}).get("destination"),
        "iam_policy": {
            "Action": [
                "logs:CreateLogStream",
                "logs:PutLogEvents",
                "logs:DescribeLogGroups",
            ],
            "Resource": c.get("flow_log", {}).get("log_group_arn"),
        },
        "log_format": "${version} ${account-id} ${interface-id} ${srcaddr} ${dstaddr} ${action}",
        "subnet_ids": sorted(s["id"] for s in subs),
    }
    cidrs = c.get("resolver", {}).get("allowed_cidrs", [])
    rsg = {
        "id": _id("sg", env, "resolver-inbound"),
        "ingress": [
            {"protocol": p, "from_port": 53, "to_port": 53, "cidr_blocks": cidrs}
            for p in ["tcp", "udp"]
        ],
        "egress": [
            {
                "protocol": "-1",
                "from_port": 0,
                "to_port": 0,
                "cidr_blocks": [c["vpc_cidr"]],
            }
        ],
    }
    outputs = {'''
if needle not in s:
    raise SystemExit("outputs anchor missing")
s = s.replace(needle, flow_block, 1)
s = s.replace('"flow_log": None,', '"flow_log": flow,')
s = s.replace('"resolver_security_group": None,', '"resolver_security_group": rsg,')
p.write_text(s)
PY
