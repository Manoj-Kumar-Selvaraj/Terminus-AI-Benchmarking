#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
bash "/steps/milestone_4/solution/solve4.sh"
python3 - <<'PY'
from pathlib import Path
p = Path("/app/infra/modules/vpc/module.py")
s = p.read_text()
needle = '    except Exception as exc:\n        errs.append("invalid cidr configuration: " + str(exc))\n    for ep in c.get("gateway_endpoints", []):'
insert = '''    except Exception as exc:
        errs.append("invalid cidr configuration: " + str(exc))
    nats = {n.get("az") for n in c.get("nat_gateways", [])}
    app = {subnet.get("az") for subnet in c.get("subnets", []) if subnet.get("tier") == "app"}
    missing = sorted(app - nats)
    if missing:
        errs.append("missing nat gateway for app azs: " + ",".join(missing))
    for ep in c.get("gateway_endpoints", []):'''
if needle not in s:
    raise SystemExit("nat validation anchor missing")
s = s.replace(needle, insert, 1)
old_prior = '''    if prior_state:
        if prior_state.get("vpc", {}).get("cidr") == vpc["cidr"]:
            pass
    else:'''
new_prior = '''    if prior_state:
        prior = {subnet.get("cidr"): subnet for subnet in prior_state.get("subnets", [])}
        for subnet in subs:
            old = prior.get(subnet["cidr"])
            if old and old.get("id") != subnet["id"]:
                actions.append(
                    {
                        "action": "moved",
                        "from": old.get("address", old.get("id")),
                        "to": subnet["address"],
                    }
                )
        if prior_state.get("vpc", {}).get("cidr") == vpc["cidr"]:
            pass
    else:'''
if old_prior not in s:
    raise SystemExit("prior_state anchor missing")
s = s.replace(old_prior, new_prior, 1)
s = s.replace(
    '"moved": [],',
    '"moved": [\n'
    '            {"from": "module.vpc.aws_subnet.private", "to": "module.vpc.aws_subnet.app"}\n'
    "        ],",
)
p.write_text(s)
PY
