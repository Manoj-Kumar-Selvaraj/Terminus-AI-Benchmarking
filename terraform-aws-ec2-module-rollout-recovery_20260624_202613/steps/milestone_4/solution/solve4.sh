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
    placement = config.get("placement") or {}
    subnets = placement.get("subnets") or []
    minimum_azs = int(placement.get("minimum_azs", 0) or 0)
    seen_ids = set()
    seen_azs = set()
    for subnet in subnets:
        subnet_id = subnet.get("id")
        az = subnet.get("az")
        if subnet.get("tier") != "private_app":
            errors.append(f"subnet {subnet_id} must have tier private_app")
        if subnet.get("account_id") != config.get("account_id"):
            errors.append(f"subnet {subnet_id} must belong to configured account")
        if not isinstance(subnet_id, str) or not subnet_id.startswith("subnet-"):
            errors.append("subnet id must start with subnet-")
        if not isinstance(az, str) or not az.startswith(config.get("region", "")):
            errors.append(f"subnet {subnet_id} has invalid availability zone")
        if subnet_id in seen_ids:
            errors.append(f"duplicate subnet id {subnet_id}")
        if az in seen_azs:
            errors.append(f"duplicate availability zone {az}")
        seen_ids.add(subnet_id)
        seen_azs.add(az)
    if len(seen_azs) < minimum_azs:
        errors.append(f"placement requires at least {minimum_azs} unique availability zones")
    network = config.get("network") or {}
    alb_sg = network.get("alb_security_group_id")
    resolver_sg = network.get("resolver_security_group_id")
    prefix_lists = network.get("endpoint_prefix_lists") or []
    if not isinstance(alb_sg, str) or not alb_sg.startswith("sg-"):
        errors.append("network.alb_security_group_id must start with sg-")
    if not isinstance(resolver_sg, str) or not resolver_sg.startswith("sg-"):
        errors.append("network.resolver_security_group_id must start with sg-")
    if not prefix_lists:
        errors.append("network.endpoint_prefix_lists is required")
    if len(prefix_lists) != len(set(prefix_lists)):
        errors.append("network.endpoint_prefix_lists contains duplicates")
    if any(not isinstance(item, str) or not item.startswith("pl-") for item in prefix_lists):
        errors.append("network.endpoint_prefix_lists entries must start with pl-")
    try:
        port = int(config.get("service_port", 0) or 0)
    except (TypeError, ValueError):
        port = 0
    if not 1 <= port <= 65535:
        errors.append("service_port must be between 1 and 65535")
    asg = config.get("asg") or {}
    desired = int(asg.get("desired_capacity", 0) or 0)
    minimum = int(asg.get("min_size", 0) or 0)
    maximum = int(asg.get("max_size", 0) or 0)
    if not (minimum <= desired <= maximum and desired > 0):
        errors.append("asg desired_capacity must be within min_size and max_size")
    if int(asg.get("max_unavailable", 0) or 0) != 1:
        errors.append("asg.max_unavailable must be exactly 1")
    if int(asg.get("pilot_size", 0) or 0) != 1:
        errors.append("asg.pilot_size must be exactly 1")
    if int(asg.get("wave_size", 0) or 0) < 1:
        errors.append("asg.wave_size must be positive")
    _required((config.get("rollout") or {}).get("owner_token"), "rollout.owner_token", errors)
    seen_names = set()
    for volume in config.get("ebs_volumes") or []:
        name = volume.get("logical_name")
        if not name:
            errors.append("ebs_volumes.logical_name is required")
        elif name in seen_names:
            errors.append(f"duplicate ebs logical_name {name}")
        seen_names.add(name)
        if volume.get("encrypted") is not True:
            errors.append(f"ebs volume {name} is unencrypted")
        if not volume.get("kms_key_alias"):
            errors.append(f"ebs volume {name} is missing kms_key_alias")
        kms_arn = volume.get("kms_key_arn", "")
        expected_prefix = f"arn:aws:kms:{config.get('region')}:{config.get('account_id')}:key/"
        if not kms_arn.startswith(expected_prefix):
            errors.append(f"ebs volume {name} kms key is outside configured account")
        if volume.get("delete_on_termination") is not False:
            errors.append(f"ebs volume {name} must set delete_on_termination false")
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
    network = config["network"]
    port = int(config["service_port"])
    return {
        "id": _id("sg", config.get("app"), config.get("environment")),
        "ingress": [
            {
                "protocol": "tcp",
                "from_port": port,
                "to_port": port,
                "source_security_group_id": network["alb_security_group_id"],
            }
        ],
        "egress": [
            {
                "protocol": "tcp",
                "from_port": 443,
                "to_port": 443,
                "prefix_list_ids": sorted(network["endpoint_prefix_lists"]),
            },
            {
                "protocol": "udp",
                "from_port": 53,
                "to_port": 53,
                "source_security_group_id": network["resolver_security_group_id"],
            },
            {
                "protocol": "tcp",
                "from_port": 53,
                "to_port": 53,
                "source_security_group_id": network["resolver_security_group_id"],
            },
        ],
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
    eligible = _eligible_subnets(config)
    eligible_ids = {subnet["id"] for subnet in eligible}
    prior_by_slot = {int(item["slot"]): item for item in prior_instances}
    placements = {}
    for slot in range(desired):
        prior = prior_by_slot.get(slot)
        if prior and prior.get("subnet_id") in eligible_ids:
            subnet = next(item for item in eligible if item["id"] == prior["subnet_id"])
        else:
            subnet = eligible[slot % len(eligible)]
        placements[slot] = subnet
    return placements


def _instance(config, launch_template, security_group, slot, subnet):
    release = _release_identity(config)
    return {
        "id": _id("i", config.get("app"), slot, launch_template["version"][:10]),
        "slot": slot,
        "subnet_id": subnet["id"],
        "az": subnet["az"],
        "public_ip_associated": False,
        "security_group_id": security_group["id"],
        "launch_template_version": launch_template["version"],
        "ami_id": launch_template["ami_id"],
        "state": "running",
        "health": "healthy",
        "tags": {
            "Application": config.get("app"),
            "Environment": config.get("environment"),
            "Slot": str(slot),
            "CommitSha": release["commit_sha"],
            "BuildId": release["build_id"],
            "ReleaseManifestSha256": release["manifest_sha256"],
        },
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
    prior_instances = sorted(deepcopy(prior.get("instances") or []), key=lambda item: int(item["slot"]))
    target_manifest = _release_identity(config)["manifest_sha256"]
    prior_refresh = (prior.get("autoscaling_group") or {}).get("instance_refresh") or {}
    in_progress = prior_refresh.get("status") == "in_progress"

    if in_progress:
        if prior_refresh.get("target_manifest_sha256") != target_manifest:
            raise ModuleError("target release changed during in-progress rollout")
        if prior_refresh.get("owner_token") != config["rollout"]["owner_token"]:
            raise ModuleError("stale rollout owner cannot resume in-progress operation")
        source_manifest = prior_refresh["source_manifest_sha256"]
        operation_id = prior_refresh["operation_id"]
        completed_slots = list(prior_refresh.get("completed_slots") or [])
        events = deepcopy(prior_refresh.get("events") or [])
    else:
        source_manifest = (prior.get("release_identity") or {}).get("manifest_sha256")
        operation_id = _operation_id(config, source_manifest, target_manifest, desired)
        completed_slots = []
        events = []

    placements = _placement_by_slot(config, desired, prior_instances)
    current_by_slot = {int(item["slot"]): item for item in prior_instances}
    target_by_slot = {
        slot: _instance(config, launch_template, security_group, slot, placements[slot])
        for slot in range(desired)
    }
    health = config["rollout"].get("candidate_health", "passing")
    fault = config["rollout"].get("fault_point", "none")

    if not in_progress and health == "fail_pilot":
        events = [
            _event(1, "pilot_launched", desired, slot=0),
            _event(2, "pilot_unhealthy", desired, slot=0),
            _event(3, "previous_capacity_preserved", desired),
        ]
        return prior_instances, {
            "strategy": "pilot-then-wave",
            "operation_id": operation_id,
            "owner_token": config["rollout"]["owner_token"],
            "source_manifest_sha256": source_manifest,
            "target_manifest_sha256": target_manifest,
            "status": "rolled_back",
            "cursor": 0,
            "completed_slots": [],
            "min_healthy_percentage": math.ceil((desired - 1) * 100 / desired),
            "max_unavailable": 1,
            "events": events,
        }, False

    if not in_progress and health == "fail_wave":
        events = [
            _event(1, "pilot_launched", desired, slot=0),
            _event(2, "pilot_healthy", desired, slot=0),
            _event(3, "pilot_committed", desired, slot=0),
            _event(4, "wave_launched", desired, wave=1),
            _event(5, "wave_unhealthy", desired, wave=1),
            _event(6, "previous_capacity_preserved", desired),
        ]
        return prior_instances, {
            "strategy": "pilot-then-wave",
            "operation_id": operation_id,
            "owner_token": config["rollout"]["owner_token"],
            "source_manifest_sha256": source_manifest,
            "target_manifest_sha256": target_manifest,
            "status": "rolled_back",
            "cursor": 0,
            "completed_slots": [],
            "min_healthy_percentage": math.ceil((desired - 1) * 100 / desired),
            "max_unavailable": 1,
            "events": events,
        }, False

    seq = max([item.get("seq", 0) for item in events] or [0])
    if 0 not in completed_slots:
        for name in ("pilot_launched", "pilot_healthy", "pilot_committed"):
            seq += 1
            events.append(_event(seq, name, desired, slot=0))
        current_by_slot[0] = target_by_slot[0]
        completed_slots.append(0)
        if fault == "after_pilot_commit_response_lost":
            mixed = [current_by_slot[slot] for slot in sorted(current_by_slot) if slot < desired]
            refresh = {
                "strategy": "pilot-then-wave",
                "operation_id": operation_id,
                "owner_token": config["rollout"]["owner_token"],
                "source_manifest_sha256": source_manifest,
                "target_manifest_sha256": target_manifest,
                "status": "in_progress",
                "cursor": 1,
                "completed_slots": completed_slots,
                "min_healthy_percentage": math.ceil((desired - 1) * 100 / desired),
                "max_unavailable": 1,
                "events": events,
            }
            return mixed, refresh, True

    remaining = [slot for slot in range(desired) if slot not in completed_slots]
    wave_size = int(config["asg"]["wave_size"])
    wave_number = 0
    for start in range(0, len(remaining), wave_size):
        wave_number += 1
        slots = remaining[start : start + wave_size]
        for name in ("wave_launched", "wave_healthy", "wave_committed"):
            seq += 1
            event = _event(seq, name, desired, wave=wave_number)
            event["slots"] = slots
            events.append(event)
        for slot in slots:
            current_by_slot[slot] = target_by_slot[slot]
            completed_slots.append(slot)
    seq += 1
    events.append(_event(seq, "rollout_completed", desired))
    instances = [current_by_slot[slot] for slot in range(desired)]
    return instances, {
        "strategy": "pilot-then-wave",
        "operation_id": operation_id,
        "owner_token": config["rollout"]["owner_token"],
        "source_manifest_sha256": source_manifest,
        "target_manifest_sha256": target_manifest,
        "status": "completed",
        "cursor": desired,
        "completed_slots": sorted(completed_slots),
        "min_healthy_percentage": math.ceil((desired - 1) * 100 / desired),
        "max_unavailable": 1,
        "events": events,
    }, False


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
    prior_instances = {item.get("id"): int(item["slot"]) for item in prior.get("instances") or []}
    prior_volumes = {}
    for volume in prior.get("ebs_volumes") or []:
        slot = int(volume.get("slot"))
        attached = volume.get("attached_instance_id")
        if attached and attached in prior_instances and prior_instances[attached] != slot:
            raise ModuleError(f"volume {volume.get('id')} violates slot ownership")
        prior_volumes[(slot, volume.get("logical_name"))] = volume

    result = []
    for instance in instances:
        slot = int(instance["slot"])
        for definition in config.get("ebs_volumes") or []:
            name = definition["logical_name"]
            stable_id = _id("vol", config.get("app"), slot, name)
            previous = prior_volumes.get((slot, name))
            generation = int((previous or {}).get("attachment_generation", 0) or 0)
            if not previous:
                generation = 1
            elif previous.get("attached_instance_id") != instance["id"]:
                generation += 1
            token = _hash(
                {"volume_id": stable_id, "instance_id": instance["id"], "generation": generation},
                24,
            )
            result.append(
                {
                    "id": stable_id,
                    "logical_name": name,
                    "slot": slot,
                    "size_gb": int(definition.get("size_gb", 0)),
                    "encrypted": True,
                    "kms_key_alias": definition["kms_key_alias"],
                    "kms_key_arn": definition["kms_key_arn"],
                    "delete_on_termination": False,
                    "orphaned": False,
                    "attached_instance_id": instance["id"],
                    "attachment_generation": generation,
                    "attachment_token": token,
                    "tags": {
                        "Application": config.get("app"),
                        "Environment": config.get("environment"),
                        "Slot": str(slot),
                        "VolumeRole": name,
                        "ManagedBy": "terraform-aws-ec2-module",
                    },
                }
            )
    return sorted(result, key=lambda item: (item["slot"], item["logical_name"]))


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
