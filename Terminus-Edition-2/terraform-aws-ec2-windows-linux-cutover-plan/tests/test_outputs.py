import json
import os
import subprocess
from pathlib import Path

APP = Path(os.environ.get("APP_ROOT", "/app"))
TF_ROOT = APP / "environment" / "terraform"
PLAN_JSON = APP / "output" / "ec2_linux_migration_plan.json"

WORKLOADS = {
    "payments-api": {"subnet_id": "subnet-private-app-a", "private_ip": "10.42.16.21", "ami": "ami-linux-payments-20260601", "instance_type": "m7i.large", "az": "us-east-1a", "root_gib": 80},
    "claims-worker": {"subnet_id": "subnet-private-batch-b", "private_ip": "10.42.24.45", "ami": "ami-linux-claims-20260601", "instance_type": "m7i.xlarge", "az": "us-east-1b", "root_gib": 100},
    "report-export": {"subnet_id": "subnet-private-services-a", "private_ip": "10.42.31.78", "ami": "ami-linux-reporting-20260601", "instance_type": "m7i.large", "az": "us-east-1a", "root_gib": 80},
    "admin-jump": {"subnet_id": "subnet-private-admin-b", "private_ip": "10.42.8.9", "ami": "ami-linux-admin-20260601", "instance_type": "t3.large", "az": "us-east-1b", "root_gib": 60},
}
KMS_KEY = "arn:aws:kms:us-east-1:111122223333:key/96b54ac0-1579-42db-8ed0-ec2linuxmigration"
FORBIDDEN_GROUPS = {"sg-rdp-admin", "sg-winrm-admin", "sg-domain-join"}
EXPECTED_VOLUME_KEYS = {"admin-jump:/dev/sdf", "claims-worker:/dev/sdf", "payments-api:/dev/sdf", "payments-api:/dev/sdg", "report-export:/dev/sdf"}
SNAPSHOTS = {"snap-payments-appdata-20260601", "snap-payments-logs-20260601", "snap-claims-queue-20260601", "snap-report-share-20260601", "snap-admin-tools-20260601"}


def run_render_command():
    result = subprocess.run(
        [str(APP / "environment" / "scripts" / "render-migration-plan")],
        cwd=TF_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    assert result.returncode == 0, result.stdout


def load_plan():
    assert TF_ROOT.exists(), "Terraform root is missing"
    assert (TF_ROOT / "modules" / "ec2_linux_migration").is_dir(), "EC2 migration module is missing"
    fmt = subprocess.run(["terraform", "fmt", "-check", "-recursive"], cwd=TF_ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    assert fmt.returncode == 0, fmt.stdout
    run_render_command()
    assert PLAN_JSON.exists() and PLAN_JSON.stat().st_size > 0, "plan JSON was not produced"
    return json.loads(PLAN_JSON.read_text())


def resource_changes(plan, resource_type):
    return [
        change
        for change in plan.get("resource_changes", [])
        if change.get("type") == resource_type and change.get("change", {}).get("actions") == ["create"]
    ]


def after(change):
    return change["change"]["after"]


def instance_by_workload(plan):
    instances = {}
    for change in resource_changes(plan, "aws_instance"):
        body = after(change)
        instances[body["tags"]["Workload"]] = body
    return instances


class TestEc2WindowsLinuxCutoverPlan:
    def test_final_plan_is_module_based_complete_and_offline(self):
        plan = load_plan()
        module_calls = plan["configuration"]["root_module"].get("module_calls", {})
        assert module_calls.get("ec2_linux_migration", {}).get("source", "").split("/")[-1] == "ec2_linux_migration"
        assert not [c for c in plan.get("resource_changes", []) if c.get("mode") == "data"]
        ec2_changes = [c for c in plan.get("resource_changes", []) if c.get("type") in {"aws_instance", "aws_ebs_volume", "aws_volume_attachment"}]
        assert len(resource_changes(plan, "aws_instance")) == 4
        assert len(resource_changes(plan, "aws_ebs_volume")) == 5
        assert len(resource_changes(plan, "aws_volume_attachment")) == 5
        assert all(c["address"].startswith("module.ec2_linux_migration.") for c in ec2_changes)

    def test_instances_are_inventory_matched_ssm_private_and_imdsv2_hardened(self):
        plan = load_plan()
        instances = instance_by_workload(plan)
        assert set(instances) == set(WORKLOADS)
        for workload, inst in instances.items():
            expected = WORKLOADS[workload]
            assert inst["ami"] == expected["ami"]
            assert inst["instance_type"] == expected["instance_type"]
            assert inst["subnet_id"] == expected["subnet_id"]
            assert inst["availability_zone"] == expected["az"]
            assert inst["private_ip"] == expected["private_ip"]
            groups = set(inst["vpc_security_group_ids"])
            assert "sg-ssm-egress" in groups
            assert not groups.intersection(FORBIDDEN_GROUPS)
            assert inst.get("associate_public_ip_address") is False
            assert inst.get("key_name") is None
            assert inst["iam_instance_profile"] == "ssm-linux-core-prod"
            assert inst["disable_api_termination"] is True
            assert inst["monitoring"] is True
            assert inst["ebs_optimized"] is True
            metadata = inst["metadata_options"][0]
            assert metadata["http_endpoint"] == "enabled"
            assert metadata["http_tokens"] == "required"
            assert metadata["http_put_response_hop_limit"] == 1
            assert metadata["instance_metadata_tags"] == "enabled"

    def test_final_tags_and_root_volume_hardening(self):
        plan = load_plan()
        for workload, inst in instance_by_workload(plan).items():
            tags = inst["tags"]
            assert tags["ManagedBy"] == "terraform"
            assert tags["MigrationProgram"] == "windows-to-linux-2026"
            assert tags["ComplianceDomain"] == "payments-platform"
            assert tags["CutoverId"] == "CUT-2026-06-WINLINUX"
            assert tags["MigrationWave"] == "wave-3-prod-parallel"
            assert tags["MigratedFromOS"] == "windows"
            assert tags["OSFamily"] == "linux"
            assert tags["LegacyInstanceId"].startswith("i-0win")
            assert tags["Owner"].startswith("platform-")
            assert tags["OwnerCostCenter"].startswith("cc-")
            assert tags["PatchGroup"].startswith("linux-")
            assert tags["BackupTier"] in {"gold", "silver", "bronze"}
            root = inst["root_block_device"][0]
            assert root["volume_size"] == WORKLOADS[workload]["root_gib"]
            assert root["volume_type"] == "gp3"
            assert root["encrypted"] is True
            assert root["kms_key_id"] == KMS_KEY
            assert root["tags"]["VolumeRole"] == "root"

    def test_data_storage_and_outputs_remain_complete_after_hardening(self):
        plan = load_plan()
        volumes = [after(change) for change in resource_changes(plan, "aws_ebs_volume")]
        attachments = [after(change) for change in resource_changes(plan, "aws_volume_attachment")]
        assert {v["snapshot_id"] for v in volumes} == SNAPSHOTS
        assert all(v["encrypted"] is True and v["kms_key_id"] == KMS_KEY and v["type"] == "gp3" for v in volumes)
        for volume in volumes:
            tags = volume["tags"]
            assert volume["iops"] >= 3000
            assert volume["throughput"] >= 125
            assert volume["size"] >= 80
            assert volume["availability_zone"] == WORKLOADS[tags["Workload"]]["az"]
            assert tags["SourceSnapshot"] == volume["snapshot_id"]
            assert tags["DeviceName"] in {"/dev/sdf", "/dev/sdg"}
            assert tags["VolumeRole"]
            assert tags["LegacyInstanceId"].startswith("i-0win")
            assert tags["MigratedFromOS"] == "windows"
            assert tags["OSFamily"] == "linux"
        assert len(attachments) == 5
        assert sorted(a["device_name"] for a in attachments) == ["/dev/sdf", "/dev/sdf", "/dev/sdf", "/dev/sdf", "/dev/sdg"]
        assert all(a.get("force_detach") is False for a in attachments)
        outputs = plan["planned_values"]["outputs"]
        assert set(outputs["planned_linux_instances"]["value"].keys()) == set(WORKLOADS)
        assert set(outputs["planned_data_volumes"]["value"].keys()) == EXPECTED_VOLUME_KEYS
