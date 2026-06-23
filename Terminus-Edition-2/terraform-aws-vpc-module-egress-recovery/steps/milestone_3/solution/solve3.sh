#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
bash "/steps/milestone_2/solution/solve2.sh"
python3 - <<'PY'
from pathlib import Path
p = Path("/app/infra/modules/vpc/module.py")
s = p.read_text()
if "import ipaddress" not in s:
    s = "import ipaddress\n\n" + s
needle = '            errs.append(f"missing {t} tier")\n    for ep in c.get("gateway_endpoints", []):'
insert = '''            errs.append(f"missing {t} tier")
    try:
        v = ipaddress.ip_network(c["vpc_cidr"])
        seen = []
        for subnet in c.get("subnets", []):
            n = ipaddress.ip_network(subnet["cidr"])
            if not n.subnet_of(v):
                errs.append(f"subnet {subnet.get('name')} outside vpc_cidr")
            for name, prev in seen:
                if n.overlaps(prev):
                    errs.append(f"subnet {subnet.get('name')} overlaps {name}")
            seen.append((subnet.get("name"), n))
    except Exception as exc:
        errs.append("invalid cidr configuration: " + str(exc))
    for ep in c.get("gateway_endpoints", []):'''
if needle not in s:
    raise SystemExit("validate_config anchor missing")
s = s.replace(needle, insert, 1)
old_prior = '''    if prior_state:
        actions.append(
            {
                "action": "replace",
                "resource": "aws_route_table.private",
                "reason": "legacy index drift",
            }
        )
    else:'''
new_prior = '''    if prior_state:
        if prior_state.get("vpc", {}).get("cidr") == vpc["cidr"]:
            pass
    else:'''
if old_prior not in s:
    raise SystemExit("prior_state anchor missing")
s = s.replace(old_prior, new_prior, 1)
p.write_text(s)
PY
