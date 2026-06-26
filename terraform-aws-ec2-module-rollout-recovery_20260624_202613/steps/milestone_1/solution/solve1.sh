#!/usr/bin/env bash
set -Eeuo pipefail
APP_DIR="${APP_DIR:-/app}"
cat > "${APP_DIR}/infra/modules/ec2/module.py" <<'PYMODULE'
import hashlib
import json
import math
from copy import deepcopy
from pathlib import Path


class ModuleError(Exception):
    pass


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _hash(value, length=None):
    digest = hashlib.sha256(_canonical(value).encode()).hexdigest()
    return digest if length is None else digest[:length]


def _id(prefix, *parts):
    normalized = [str(part).replace("/", "_").replace(":", "_") for part in parts]
    return prefix + "-" + "-".join(normalized)


def _manifest_payload(artifact):
    keys = [
        "manifest_version",
        "ami_id",
        "ami_owner_account_id",
        "architecture",
        "commit_sha",
        "build_id",
        "user_data_sha256",
    ]
    return {key: artifact.get(key) for key in keys}


def _release_identity(config):
    artifact = config["release_artifact"]
    return {**_manifest_payload(artifact), "manifest_sha256": artifact["manifest_sha256"]}


def _required(value, name, errors):
    if value is None or value == "" or value == []:
        errors.append(f"{name} is required")


def validate_config(config):
    errors = []
    if config.get("schema_version") != "ec2-module-config.v2":
        errors.append("schema_version must be ec2-module-config.v2")
    artifact = config.get("release_artifact") or {}
    for field in (
        "manifest_version", "ami_id", "ami_owner_account_id", "architecture",
        "commit_sha", "build_id", "user_data_sha256", "manifest_sha256",
    ):
        _required(artifact.get(field), f"release_artifact.{field}", errors)
    if not errors:
        expected_manifest = _hash(_manifest_payload(artifact))
        if artifact.get("manifest_sha256") != expected_manifest:
            errors.append("release_artifact.manifest_sha256 does not match canonical manifest")
        image = (config.get("ami_catalog") or {}).get("images", {}).get(artifact.get("ami_id"))
        if not image:
            errors.append("release_artifact.ami_id is absent from ami_catalog.images")
        else:
            if image.get("owner_account_id") != artifact.get("ami_owner_account_id"):
                errors.append("release_artifact.ami_owner_account_id does not match catalog owner")
            if image.get("architecture") != artifact.get("architecture"):
                errors.append("release_artifact.architecture does not match catalog architecture")
            if image.get("state") != "available":
                errors.append("release_artifact.ami_id must be available")
            if image.get("deprecated") is True:
                errors.append("release_artifact.ami_id must not be deprecated")
    if errors:
        raise ModuleError("; ".join(errors))

def _metadata_options(_config):
    return {"http_tokens": "optional", "http_endpoint": "enabled", "http_put_response_hop_limit": 2}

def _launch_template(config):
    release = _release_identity(config)
    body = {
        "ami_id": release["ami_id"],
        "architecture": release["architecture"],
        "instance_type": config.get("instance_type"),
        "user_data_sha256": release["user_data_sha256"],
        "metadata_options": _metadata_options(config),
        "provenance": {
            "commit_sha": release["commit_sha"],
            "build_id": release["build_id"],
            "manifest_sha256": release["manifest_sha256"],
        },
    }
    version = _hash(body, 20)
    return {
        "id": _id("lt", config.get("app"), config.get("environment")),
        "version": version,
        **body,
        "tags": {
            "Application": config.get("app"),
            "Environment": config.get("environment"),
            "ManagedBy": "terraform-aws-ec2-module",
            "ReleaseManifestSha256": release["manifest_sha256"],
        },
    }


def _security_group(config):
    return {
        "id": _id("sg", config.get("app"), config.get("environment")),
        "ingress": [{"protocol": "tcp", "from_port": 22, "to_port": 22, "cidr_blocks": ["0.0.0.0/0"]}],
        "egress": [{"protocol": "-1", "from_port": 0, "to_port": 0, "cidr_blocks": ["0.0.0.0/0"]}],
    }

def _iam_role(config):
    return {"name": _id("role", config.get("app"), config.get("environment")), "policy": [{"Sid": "Administrator", "Action": ["*"], "Resource": "*"}]}

def _legacy_moves():
    return [
        {"from": "aws_launch_template.payments", "to": "aws_launch_template.this"},
        {"from": "aws_autoscaling_group.payments", "to": "aws_autoscaling_group.this"},
        {"from": "aws_security_group.payments_instance", "to": "aws_security_group.instance"},
        {"from": "aws_iam_role.payments_instance", "to": "aws_iam_role.instance"},
        {"from": "aws_ebs_volume.payments_data", "to": "aws_ebs_volume.data"},
        {"from": "aws_volume_attachment.payments_data", "to": "aws_volume_attachment.data"},
    ]


def _normalize_prior(prior, config):
    if not prior:
        return {}, {"legacy_state": False, "moved": [], "preserved_instance_ids": []}
    return deepcopy(prior), {"legacy_state": False, "moved": [], "preserved_instance_ids": [item.get("id") for item in prior.get("instances") or []]}

def _eligible_subnets(config):
    return sorted(config["placement"]["subnets"], key=lambda item: (item["az"], item["id"]))


def _placement_by_slot(config, desired, prior_instances):
    subnets = list(config["placement"]["subnets"])
    return {slot: subnets[slot % len(subnets)] for slot in range(desired)}

def _instance(config, launch_template, security_group, slot, subnet):
    release = _release_identity(config)
    return {
        "id": _id("i", config.get("app"), slot, launch_template["version"][:10]),
        "slot": slot, "subnet_id": subnet["id"], "az": subnet["az"],
        "public_ip_associated": True, "security_group_id": security_group["id"],
        "launch_template_version": launch_template["version"], "ami_id": launch_template["ami_id"],
        "state": "running", "health": "healthy",
        "tags": {"Application": config.get("app"), "Environment": config.get("environment"), "Slot": str(slot), "CommitSha": release["commit_sha"], "BuildId": release["build_id"], "ReleaseManifestSha256": release["manifest_sha256"]},
    }

def _initial_instances(config, launch_template, security_group, desired):
    placements = _placement_by_slot(config, desired, [])
    return [_instance(config, launch_template, security_group, slot, placements[slot]) for slot in range(desired)]


def _operation_id(config, source_manifest, target_manifest, desired):
    return "rollout-" + _hash(
        {
            "app": config.get("app"),
            "environment": config.get("environment"),
            "source_manifest": source_manifest,
            "target_manifest": target_manifest,
            "desired_capacity": desired,
        },
        18,
    )


def _event(seq, name, desired, slot=None, wave=None):
    value = {
        "seq": seq,
        "event": name,
        "healthy_capacity": desired,
        "unavailable": 0,
    }
    if slot is not None:
        value["slot"] = slot
    if wave is not None:
        value["wave"] = wave
    return value


def _refresh(config, prior, launch_template, security_group, desired):
    placements = _placement_by_slot(config, desired, prior.get("instances") or [])
    instances = [_instance(config, launch_template, security_group, slot, placements[slot]) for slot in range(desired)]
    refresh = {
        "strategy": "terminate-first", "operation_id": "refresh-latest", "owner_token": config.get("rollout", {}).get("owner_token"),
        "source_manifest_sha256": (prior.get("release_identity") or {}).get("manifest_sha256"),
        "target_manifest_sha256": _release_identity(config)["manifest_sha256"], "status": "completed", "cursor": desired,
        "completed_slots": list(range(desired)), "min_healthy_percentage": 50, "max_unavailable": desired,
        "events": [{"seq": 1, "event": "old_capacity_terminated", "healthy_capacity": max(0, desired - 2), "unavailable": 2}],
    }
    return instances, refresh, False

def _same_release_instances(config, prior, launch_template, security_group, desired):
    prior_instances = sorted(deepcopy(prior.get("instances") or []), key=lambda item: int(item["slot"]))
    placements = _placement_by_slot(config, desired, prior_instances)
    by_slot = {int(item["slot"]): item for item in prior_instances}
    instances = []
    actions = []
    for slot in range(desired):
        if slot in by_slot:
            instances.append(by_slot[slot])
            actions.append({"action": "no_op", "slot": slot, "instance_id": by_slot[slot]["id"]})
        else:
            created = _instance(config, launch_template, security_group, slot, placements[slot])
            instances.append(created)
            actions.append({"action": "create", "slot": slot, "instance_id": created["id"]})
    for slot, item in by_slot.items():
        if slot >= desired:
            actions.append({"action": "scale_in", "slot": slot, "instance_id": item["id"]})
    return instances, actions


def _drift_report(config, prior_instances, expected_instances, security_group):
    return []

def _volumes(config, instances, prior):
    return []

def render(config, prior_state=None):
    validate_config(config)
    prior, import_report = _normalize_prior(prior_state, config)
    release = _release_identity(config)
    launch_template = _launch_template(config)
    security_group = _security_group(config)
    iam_role = _iam_role(config)
    desired = int(config["asg"]["desired_capacity"])
    prior_instances = prior.get("instances") or []
    prior_refresh = (prior.get("autoscaling_group") or {}).get("instance_refresh") or {}
    in_progress = prior_refresh.get("status") == "in_progress"
    prior_manifest = (prior.get("release_identity") or {}).get("manifest_sha256")
    release_changed = bool(prior and prior_manifest != release["manifest_sha256"])

    control_plane_response_lost = False
    if not prior:
        instances = _initial_instances(config, launch_template, security_group, desired)
        refresh = {
            "strategy": "pilot-then-wave",
            "operation_id": None,
            "owner_token": config["rollout"]["owner_token"],
            "source_manifest_sha256": None,
            "target_manifest_sha256": release["manifest_sha256"],
            "status": "stable",
            "cursor": desired,
            "completed_slots": list(range(desired)),
            "min_healthy_percentage": math.ceil((desired - 1) * 100 / desired),
            "max_unavailable": 1,
            "events": [],
        }
        plan_actions = [{"action": "create", "slot": item["slot"], "instance_id": item["id"]} for item in instances]
        drift_report = []
    elif release_changed or in_progress:
        instances, refresh, control_plane_response_lost = _refresh(
            config, prior, launch_template, security_group, desired
        )
        plan_actions = [
            {
                "action": "rolling_replace",
                "slot": item["slot"],
                "instance_id": item["id"],
                "operation_id": refresh["operation_id"],
            }
            for item in instances
        ]
        drift_report = []
    else:
        expected_instances = _initial_instances(config, launch_template, security_group, desired)
        drift_report = _drift_report(config, prior_instances, expected_instances, security_group)
        instances, plan_actions = _same_release_instances(
            config, prior, launch_template, security_group, desired
        )
        for drift in drift_report:
            plan_actions.append(
                {
                    "action": "report_only",
                    "instance_id": drift["instance_id"],
                    "field": drift["field"],
                }
            )
        refresh = deepcopy(prior_refresh) if prior_refresh else {
            "strategy": "pilot-then-wave",
            "operation_id": None,
            "owner_token": config["rollout"]["owner_token"],
            "source_manifest_sha256": release["manifest_sha256"],
            "target_manifest_sha256": release["manifest_sha256"],
            "status": "stable",
            "cursor": desired,
            "completed_slots": list(range(desired)),
            "min_healthy_percentage": math.ceil((desired - 1) * 100 / desired),
            "max_unavailable": 1,
            "events": [],
        }

    volumes = _volumes(config, instances, prior)
    asg = {
        "name": _id("asg", config.get("app"), config.get("environment")),
        "desired_capacity": desired,
        "min_size": int(config["asg"]["min_size"]),
        "max_size": int(config["asg"]["max_size"]),
        "subnet_ids": [item["id"] for item in _eligible_subnets(config)],
        "instance_refresh": refresh,
    }
    result = {
        "schema_version": "ec2sim.aws.2",
        "environment": config.get("environment"),
        "application": config.get("app"),
        "release_identity": release,
        "launch_template": launch_template,
        "security_group": security_group,
        "autoscaling_group": asg,
        "instances": sorted(instances, key=lambda item: int(item["slot"])),
        "ebs_volumes": volumes,
        "iam_role": iam_role,
        "drift_report": sorted(drift_report, key=lambda item: (item["instance_id"], item["field"])),
        "import_report": import_report,
        "plan_actions": plan_actions,
        "journal_repair": {"truncated_tail": False, "preserved_records": 0},
        "control_plane_response_lost": control_plane_response_lost,
        "outputs": {
            "launch_template_id": launch_template["id"],
            "launch_template_version": launch_template["version"],
            "autoscaling_group_name": asg["name"],
            "instance_ids": [item["id"] for item in sorted(instances, key=lambda item: int(item["slot"]))],
            "volume_ids": [item["id"] for item in volumes],
            "rollout_operation_id": refresh.get("operation_id"),
            "drift_report": sorted(drift_report, key=lambda item: (item["instance_id"], item["field"])),
        },
    }
    result["state_digest"] = _hash(result)
    return result
PYMODULE
python3 -m py_compile "${APP_DIR}/infra/modules/ec2/module.py"
