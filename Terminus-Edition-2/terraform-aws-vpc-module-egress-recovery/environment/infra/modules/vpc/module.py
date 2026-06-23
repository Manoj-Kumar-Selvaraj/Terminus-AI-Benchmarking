
class ModuleError(Exception):
    pass


def _id(p, *parts):
    return p + "-" + "-".join(str(x).replace("/", "_").replace(".", "_") for x in parts)


def _az(az):
    return az[-1]


def validate_config(c):
    errs = []
    if not c.get("environment"):
        errs.append("environment is required")
    if len(c.get("availability_zones", [])) < 2:
        errs.append("at least two azs required")
    tiers = {s.get("tier") for s in c.get("subnets", [])}
    for t in ["public", "app", "data"]:
        if t not in tiers:
            errs.append(f"missing {t} tier")
    if errs:
        raise ModuleError("; ".join(errs))


def _nat(c, az):
    nats = c.get("nat_gateways", [])
    if not nats:
        return None
    return nats[0]["id"]


def render(c, prior_state=None):
    validate_config(c)
    env = c["environment"]
    vpc = {
        "id": _id("vpc", env),
        "cidr": c["vpc_cidr"],
        "tags": {"Environment": env, "ManagedBy": "terraform-aws-vpc-module"},
    }
    subs = []
    rts = []
    for s in c.get("subnets", []):
        rt = _id("rtb", env, s["tier"], _az(s["az"]))
        sid = _id("subnet", env, s["tier"], _az(s["az"]))
        subs.append(
            {
                "id": sid,
                "name": s["name"],
                "tier": s["tier"],
                "az": s["az"],
                "cidr": s["cidr"],
                "route_table_id": rt,
                "address": f'module.vpc.aws_subnet.{s["tier"]}["{s["az"]}"]',
                "tags": {
                    "Name": s["name"],
                    "Tier": s["tier"],
                    "AvailabilityZone": s["az"],
                    "Environment": env,
                },
            }
        )
        routes = []
        if s["tier"] == "public":
            routes.append(
                {
                    "destination": "0.0.0.0/0",
                    "target": c.get("internet_gateway_id", "igw"),
                }
            )
        elif s["tier"] == "app" and _nat(c, s["az"]):
            routes.append({"destination": "0.0.0.0/0", "target": _nat(c, s["az"])})
        elif s["tier"] == "data" and _nat(c, s["az"]):
            routes.append({"destination": "0.0.0.0/0", "target": _nat(c, s["az"])})
        rts.append(
            {
                "id": rt,
                "tier": s["tier"],
                "az": s["az"],
                "routes": routes,
                "tags": {
                    "Tier": s["tier"],
                    "AvailabilityZone": s["az"],
                    "ManagedBy": "terraform-aws-vpc-module",
                },
            }
        )
    eligible = [rt["id"] for rt in rts]
    endpoints = [
        {
            "id": _id("vpce", env, ep["service"]),
            "service": ep["service"],
            "route_table_ids": sorted(eligible),
            "policy": {
                "Statement": [
                    {
                        "Action": [ep["service"] + ":*"],
                        "Resource": "*",
                        "Condition": {
                            "StringEquals": {
                                "aws:PrincipalAccount": c.get(
                                    "account_id", "000000000000"
                                )
                            }
                        },
                    }
                ]
            },
            "tags": {"ManagedBy": "terraform-aws-vpc-module", "Environment": env},
        }
        for ep in c.get("gateway_endpoints", [])
    ]
    outputs = {
        "vpc_id": vpc["id"],
        "public_subnet_ids": sorted(s["id"] for s in subs if s["tier"] == "public"),
        "private_app_subnet_ids": sorted(s["id"] for s in subs if s["tier"] == "app"),
        "isolated_data_subnet_ids": sorted(
            s["id"] for s in subs if s["tier"] == "data"
        ),
        "private_app_route_table_ids": sorted(
            rt["id"] for rt in rts if rt["tier"] == "app"
        ),
        "isolated_data_route_table_ids": sorted(
            rt["id"] for rt in rts if rt["tier"] == "data"
        ),
    }
    state = {
        "schema_version": "vpcsim.aws.1",
        "environment": env,
        "vpc": vpc,
        "subnets": subs,
        "route_tables": rts,
        "gateway_endpoints": endpoints,
        "flow_log": None,
        "resolver_security_group": None,
        "outputs": outputs,
        "moved": [],
    }
    actions = []
    if prior_state:
        actions.append(
            {
                "action": "replace",
                "resource": "aws_route_table.private",
                "reason": "legacy index drift",
            }
        )
    else:
        actions.append({"action": "create", "resource": "vpc", "id": vpc["id"]})
    state["plan_actions"] = actions
    return state
