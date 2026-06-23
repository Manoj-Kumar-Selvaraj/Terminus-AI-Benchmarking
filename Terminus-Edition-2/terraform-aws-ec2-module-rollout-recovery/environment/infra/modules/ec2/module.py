import hashlib
import json
from copy import deepcopy


class ModuleError(Exception):
    pass


def _id(p, *parts):
    return p + "-" + "-".join(str(x).replace("/", "_").replace(":", "_") for x in parts)


def _h(o):
    return hashlib.sha256(
        json.dumps(o, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()[:16]


def validate_config(c):
    errs = []
    if errs:
        raise ModuleError("; ".join(errs))


def _meta(c):
    return {
        "http_tokens": "optional",
        "http_endpoint": "enabled",
        "http_put_response_hop_limit": 2,
    }


def _lt(c):
    ami = c.get("ami_catalog", {}).get("latest", "ami-latest")
    uds = "latest-bootstrap"
    prov = {"commit_sha": "HEAD", "build_id": "latest"}
    body = {
        "ami_id": ami,
        "instance_type": c.get("instance_type", "t3.micro"),
        "user_data_sha256": uds,
        "metadata_options": _meta(c),
        "provenance": prov,
    }
    return {
        "id": _id("lt", c.get("app", "app")),
        "version": _h(body),
        **body,
        "tags": {"Application": c.get("app"), "ManagedBy": "terraform-aws-ec2-module"},
    }


def _sg(c):
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
    }


def _instances(c, lt):
    desired = int(c.get("asg", {}).get("desired_capacity", 2))
    subs = c.get("subnets", [])
    out = []
    for i in range(desired):
        s = subs[i % len(subs)]
        out.append(
            {
                "id": _id("i", c.get("app"), i),
                "subnet_id": s["id"],
                "az": s.get("az"),
                "public_ip_associated": True,
                "launch_template_version": lt["version"],
                "ami_id": lt["ami_id"],
                "state": "running",
                "tags": {
                    "Application": c.get("app"),
                    "Environment": c.get("environment"),
                    "CommitSha": lt["provenance"].get("commit_sha"),
                    "BuildId": lt["provenance"].get("build_id"),
                },
            }
        )
    return out


def _refresh(c, inst, prior):
    return {
        "strategy": "terminate-first",
        "min_healthy_percentage": 50,
        "events": ["terminated_old_before_replacement"],
    }


def _ebs(c, inst):
    return []


def _iam(c):
    return {
        "name": _id("role", c.get("app")),
        "policy": [{"Action": ["*"], "Resource": "*"}],
    }


def render(c, prior_state=None):
    validate_config(c)
    prior = prior_state or {}
    lt = _lt(c)
    inst = _instances(c, lt)
    refresh = _refresh(c, inst, prior)
    if refresh.get("status") == "rolled_back" and prior.get("instances"):
        inst = deepcopy(prior["instances"])
    drift = []
    return {
        "schema_version": "ec2sim.aws.1",
        "environment": c.get("environment"),
        "application": c.get("app"),
        "launch_template": lt,
        "security_group": _sg(c),
        "autoscaling_group": {
            "name": _id("asg", c.get("app"), c.get("environment")),
            "desired_capacity": c.get("asg", {}).get("desired_capacity", 2),
            "subnet_ids": [s["id"] for s in c.get("subnets", [])],
            "instance_refresh": refresh,
        },
        "instances": inst,
        "ebs_volumes": _ebs(c, inst),
        "iam_role": _iam(c),
        "drift_report": drift,
        "outputs": {
            "launch_template_id": lt["id"],
            "launch_template_version": lt["version"],
            "autoscaling_group_name": _id("asg", c.get("app"), c.get("environment")),
            "instance_ids": [i["id"] for i in inst],
        },
    }
