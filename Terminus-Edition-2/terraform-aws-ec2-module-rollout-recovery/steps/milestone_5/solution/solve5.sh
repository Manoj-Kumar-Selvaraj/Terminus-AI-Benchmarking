#!/usr/bin/env bash
set -Eeuo pipefail
bash "/steps/milestone_4/solution/solve4.sh"
python3 - <<'PY'
from pathlib import Path

p = Path("/app/infra/modules/ec2/module.py")
s = p.read_text()

broken_meta = """def _meta(c):
    return {
        "http_tokens": "optional",
        "http_endpoint": "enabled",
        "http_put_response_hop_limit": 2,
    }"""

fixed_meta = """def _meta(c):
    return {
        "http_tokens": "required",
        "http_endpoint": "enabled",
        "http_put_response_hop_limit": 1,
    }"""

if broken_meta not in s:
    raise SystemExit("_meta anchor missing")
s = s.replace(broken_meta, fixed_meta, 1)

broken_iam = """def _iam(c):
    return {
        "name": _id("role", c.get("app")),
        "policy": [{"Action": ["*"], "Resource": "*"}],
    }"""

fixed_iam = """def _iam(c):
    kms = [
        v.get("kms_key_arn") for v in c.get("ebs_volumes", []) if v.get("kms_key_arn")
    ]
    return {
        "name": _id("role", c.get("app")),
        "policy": [
            {
                "Action": [
                    "ssm:UpdateInstanceInformation",
                    "ssmmessages:CreateControlChannel",
                    "ssmmessages:OpenControlChannel",
                    "ec2messages:GetMessages",
                ],
                "Resource": "*",
                "Condition": {
                    "StringEquals": {"aws:ResourceAccount": c.get("account_id")}
                },
            },
            {
                "Action": ["s3:GetObject"],
                "Resource": c.get("artifact_bucket_arn") + "/*",
            },
            {"Action": ["kms:Decrypt"], "Resource": kms},
            {
                "Action": ["cloudwatch:PutMetricData"],
                "Resource": "*",
                "Condition": {
                    "StringEquals": {"cloudwatch:namespace": c.get("metric_namespace")}
                },
            },
        ],
    }"""

if broken_iam not in s:
    raise SystemExit("_iam anchor missing")
s = s.replace(broken_iam, fixed_iam, 1)

needle = """    drift = []
    return {"""
insert = """    drift = []
    if prior:
        drift = [
            {
                "instance_id": i["id"],
                "field": "launch_template_version",
                "expected": lt["version"],
                "actual": i.get("launch_template_version"),
                "action": "report_only",
            }
            for i in prior.get("instances", [])
            if i.get("launch_template_version") != lt["version"]
        ]
    return {"""
if needle not in s:
    raise SystemExit("drift anchor missing")
s = s.replace(needle, insert, 1)
p.write_text(s)
PY
