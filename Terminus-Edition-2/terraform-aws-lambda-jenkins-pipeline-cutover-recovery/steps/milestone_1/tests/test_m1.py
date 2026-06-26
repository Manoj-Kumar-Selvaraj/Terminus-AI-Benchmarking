# ruff: noqa: E501
import hashlib
import json
import re
import shutil
import subprocess
import uuid
from pathlib import Path

import pytest

APP = Path("/app")
CLI = APP / "bin" / "pipelinectl"
RUNTIME = Path("/opt/task-tools/lambda-pipeline-runtime")
EXPECTED_STAGES = [
    "intake", "verify_manifest", "acquire_lock", "fetch_inputs",
    "validate_inputs", "transform_records", "precheck_ledger", "write_ledger",
    "build_report", "notify_partner", "archive_batch", "release_lock",
]

EXPECTED_STAGE_CONTRACT = {
    "intake": {"timeout_seconds": 30, "memory_mb": 256, "reserved_concurrency": 4,
               "permissions": {"logs:PutLogEvents", "xray:PutTraceSegments"}},
    "verify_manifest": {"timeout_seconds": 45, "memory_mb": 256, "reserved_concurrency": 4,
                        "permissions": {"s3:GetObject", "kms:Verify", "logs:PutLogEvents"}},
    "acquire_lock": {"timeout_seconds": 20, "memory_mb": 128, "reserved_concurrency": 8,
                     "permissions": {"dynamodb:PutItem", "dynamodb:GetItem", "logs:PutLogEvents"}},
    "fetch_inputs": {"timeout_seconds": 120, "memory_mb": 512, "reserved_concurrency": 12,
                     "permissions": {"s3:GetObject", "logs:PutLogEvents"}},
    "validate_inputs": {"timeout_seconds": 90, "memory_mb": 512, "reserved_concurrency": 12,
                        "permissions": {"s3:GetObject", "logs:PutLogEvents"}},
    "transform_records": {"timeout_seconds": 180, "memory_mb": 1024, "reserved_concurrency": 8,
                          "permissions": {"s3:GetObject", "s3:PutObject", "logs:PutLogEvents"}},
    "precheck_ledger": {"timeout_seconds": 60, "memory_mb": 256, "reserved_concurrency": 6,
                        "permissions": {"dynamodb:GetItem", "logs:PutLogEvents"}},
    "write_ledger": {"timeout_seconds": 120, "memory_mb": 512, "reserved_concurrency": 6,
                     "permissions": {"dynamodb:PutItem", "dynamodb:UpdateItem", "logs:PutLogEvents"}},
    "build_report": {"timeout_seconds": 90, "memory_mb": 512, "reserved_concurrency": 4,
                     "permissions": {"s3:PutObject", "logs:PutLogEvents"}},
    "notify_partner": {"timeout_seconds": 30, "memory_mb": 256, "reserved_concurrency": 4,
                       "permissions": {"events:PutEvents", "logs:PutLogEvents"}},
    "archive_batch": {"timeout_seconds": 60, "memory_mb": 256, "reserved_concurrency": 4,
                      "permissions": {"s3:GetObject", "s3:PutObject", "s3:DeleteObject", "logs:PutLogEvents"}},
    "release_lock": {"timeout_seconds": 20, "memory_mb": 128, "reserved_concurrency": 8,
                     "permissions": {"dynamodb:DeleteItem", "logs:PutLogEvents"}},
}
ITEM_STAGES = {"fetch_inputs", "validate_inputs", "transform_records", "precheck_ledger", "write_ledger"}


def run(*args, check=True, input_text=None):
    result = subprocess.run([str(a) for a in args], cwd=APP, text=True,
                            input=input_text, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, timeout=120)
    if check and result.returncode != 0:
        raise AssertionError(result.stdout)
    return result


def build():
    run("/usr/local/go/bin/go", "build", "-o", CLI, "./cmd/pipelinectl")


def reset():
    shutil.rmtree(APP / "state", ignore_errors=True)
    (APP / "state").mkdir()
    run(RUNTIME, "reset")


def deploy(infra=APP / "infra", check=True):
    return run(CLI, "deploy", "--infra", infra, check=check)


def runtime_state(section="state"):
    return json.loads(run(RUNTIME, "inspect", section).stdout)


def request_file(tmp_path, items=2):
    token = uuid.uuid4().hex
    data = {
        "protocol_version": 2,
        "execution_id": f"exec-{token}",
        "batch_id": f"batch-{token}",
        "artifact_digest": f"sha256:{hashlib.sha256(token.encode()).hexdigest()}",
        "owner": f"lambda-{token[:8]}",
        "items": [
            {"id": f"item-{i}-{token[:6]}", "amount": 1000 + i, "tenant": "merchant-a"}
            for i in range(items)
        ],
        "metadata": {"partner": "bank-a", "trace": token},
    }
    path = tmp_path / "request.json"
    path.write_text(json.dumps(data))
    return path, data


def copy_infra(tmp_path):
    dst = tmp_path / "infra"
    shutil.copytree(APP / "infra", dst)
    return dst


@pytest.fixture(scope="session", autouse=True)
def compiled_application():
    """Compile the editable Go controller once for the milestone verifier."""
    build()


@pytest.fixture(autouse=True)
def clean_runtime():
    """Start each assertion with empty application and trusted runtime state."""
    reset()


class TestMilestone1:
    def test_trusted_runtime_integrity(self):
        """The protected simulator binary must match the image-build checksum."""
        expected = Path("/opt/task-tools/lambda-pipeline-runtime.sha256").read_text().split()[0]
        assert hashlib.sha256(RUNTIME.read_bytes()).hexdigest() == expected

    def test_deploys_all_twelve_stages_in_contract_order(self):
        """A successful deployment exposes the complete Jenkins-equivalent stage graph."""
        deployment = json.loads(deploy().stdout)
        assert [s["name"] for s in deployment["stages"]] == EXPECTED_STAGES
        assert len(runtime_state("deployments")) == 1

    def test_uses_pinned_terraform_lambda_module(self):
        """Deployment metadata comes from the required pinned Lambda module contract."""
        deployment = json.loads(deploy().stdout)
        assert deployment["module"] == "terraform-aws-modules/lambda/aws"
        assert deployment["version"] == "7.20.1"


    def test_exact_stage_resources_and_permissions(self):
        """Each stage preserves its documented resource allocation and least-privilege actions."""
        deployment = json.loads(deploy().stdout)
        for stage in deployment["stages"]:
            expected = EXPECTED_STAGE_CONTRACT[stage["name"]]
            assert stage["timeout_seconds"] == expected["timeout_seconds"]
            assert stage["memory_mb"] == expected["memory_mb"]
            assert stage["reserved_concurrency"] == expected["reserved_concurrency"]
            assert set(stage["permissions"]) == expected["permissions"]

    def test_each_stage_has_distinct_versioned_identity(self):
        """Every stage receives its own function identity, package digest, and live alias."""
        deployment = json.loads(deploy().stdout)
        names = [s["function_name"] for s in deployment["stages"]]
        hashes = [s["package_hash"] for s in deployment["stages"]]
        assert len(set(names)) == 12
        assert len(set(hashes)) == 12
        assert all(s["alias"] == "live" for s in deployment["stages"])

    def test_wildcard_permission_is_rejected(self, tmp_path):
        """A stage cannot gain wildcard IAM actions during migration."""
        infra = copy_infra(tmp_path)
        stages = json.loads((infra / "stages.json").read_text())
        stages["stages"][4]["permissions"].append("*")
        (infra / "stages.json").write_text(json.dumps(stages))
        result = deploy(infra, check=False)
        assert result.returncode != 0
        assert runtime_state("deployments") == {}

    def test_missing_stage_is_rejected(self, tmp_path):
        """A shortened function fleet cannot be accepted as a successful migration."""
        infra = copy_infra(tmp_path)
        stages = json.loads((infra / "stages.json").read_text())
        stages["stages"].pop()
        (infra / "stages.json").write_text(json.dumps(stages))
        assert deploy(infra, check=False).returncode != 0

    def test_duplicated_stage_is_rejected(self, tmp_path):
        """A duplicate stage name cannot replace another required stage."""
        infra = copy_infra(tmp_path)
        stages = json.loads((infra / "stages.json").read_text())
        stages["stages"][11] = dict(stages["stages"][10])
        (infra / "stages.json").write_text(json.dumps(stages))
        assert deploy(infra, check=False).returncode != 0
        assert runtime_state("deployments") == {}

    def test_reordered_stage_graph_is_rejected(self, tmp_path):
        """The loader preserves the documented Jenkins stage dependency order."""
        infra = copy_infra(tmp_path)
        stages = json.loads((infra / "stages.json").read_text())
        stages["stages"][3], stages["stages"][4] = stages["stages"][4], stages["stages"][3]
        (infra / "stages.json").write_text(json.dumps(stages))
        assert deploy(infra, check=False).returncode != 0

    def test_unversioned_or_wrong_runtime_module_is_rejected(self, tmp_path):
        """The loader rejects local-module and legacy-runtime substitutions."""
        infra = copy_infra(tmp_path)
        text = (infra / "main.tf").read_text().replace(
            'source  = "terraform-aws-modules/lambda/aws"', 'source = "./lambda"'
        ).replace('runtime       = "provided.al2023"', 'runtime = "go1.x"')
        (infra / "main.tf").write_text(text)
        assert deploy(infra, check=False).returncode != 0

    def test_invalid_resource_bounds_are_rejected(self, tmp_path):
        """Timeout and concurrency values remain within the documented Lambda bounds."""
        infra = copy_infra(tmp_path)
        stages = json.loads((infra / "stages.json").read_text())
        stages["stages"][0]["timeout_seconds"] = 901
        stages["stages"][1]["reserved_concurrency"] = 0
        (infra / "stages.json").write_text(json.dumps(stages))
        assert deploy(infra, check=False).returncode != 0

    @pytest.mark.parametrize(
        ("field", "delta"),
        [("timeout_seconds", 1), ("memory_mb", 128), ("reserved_concurrency", 1)],
    )
    def test_in_range_resource_drift_is_rejected(self, tmp_path, field, delta):
        """Even values inside Lambda service limits must match the documented stage contract."""
        infra = copy_infra(tmp_path)
        stages = json.loads((infra / "stages.json").read_text())
        stages["stages"][0][field] += delta
        (infra / "stages.json").write_text(json.dumps(stages))
        assert deploy(infra, check=False).returncode != 0
        assert runtime_state("deployments") == {}

    def test_non_wildcard_permission_expansion_is_rejected(self, tmp_path):
        """A stage cannot receive another stage's otherwise valid action."""
        infra = copy_infra(tmp_path)
        stages = json.loads((infra / "stages.json").read_text())
        stages["stages"][0]["permissions"].append("s3:GetObject")
        (infra / "stages.json").write_text(json.dumps(stages))
        assert deploy(infra, check=False).returncode != 0
        assert runtime_state("deployments") == {}

    def test_wildcard_invoke_principal_is_rejected(self, tmp_path):
        """Step Functions invocation cannot be broadened to a wildcard principal."""
        infra = copy_infra(tmp_path)
        main_tf = (infra / "main.tf").read_text().replace(
            'principal  = "states.amazonaws.com"', 'principal  = "*"'
        )
        (infra / "main.tf").write_text(main_tf)
        assert deploy(infra, check=False).returncode != 0
        assert runtime_state("deployments") == {}

    def test_normal_batch_runs_every_stage_and_preserves_identity(self, tmp_path):
        """The real workflow completes all stages without losing immutable request identity."""
        deploy()
        path, request = request_file(tmp_path)
        checkpoint = json.loads(run(CLI, "run", "--request", path).stdout)
        assert checkpoint["status"] == "SUCCEEDED"
        assert checkpoint["next_stage"] == 12
        invocations = runtime_state("invocations")
        assert {i["stage"] for i in invocations} == set(EXPECTED_STAGES)
        assert all(i["execution_id"] == request["execution_id"] for i in invocations)
        assert all(i["batch_id"] == request["batch_id"] for i in invocations)
        assert all(i["metadata"]["artifact_digest"] == request["artifact_digest"] for i in invocations)
        assert all(i["generation"] == 1 for i in invocations)
        expected_item_ids = {item["id"] for item in request["items"]}
        for stage in ITEM_STAGES:
            stage_item_ids = {i["item_id"] for i in invocations if i["stage"] == stage}
            assert stage_item_ids == expected_item_ids
        assert all("item_id" not in i for i in invocations if i["stage"] not in ITEM_STAGES)

    def test_external_effects_are_stage_specific(self, tmp_path):
        """The happy path produces per-item ledger effects and one batch-level downstream effect."""
        deploy()
        path, _ = request_file(tmp_path, items=3)
        run(CLI, "run", "--request", path)
        effects = runtime_state("effects")
        assert len([e for e in effects if e["stage"] == "write_ledger"]) == 3
        assert len([e for e in effects if e["stage"] == "build_report"]) == 1
        assert len([e for e in effects if e["stage"] == "notify_partner"]) == 1
        assert len([e for e in effects if e["stage"] == "archive_batch"]) == 1

    def test_no_static_credentials_or_wildcard_principal(self):
        """Migration source contains neither embedded credentials nor wildcard invoke principals."""
        terraform_text = "\n".join(p.read_text(errors="ignore") for p in (APP / "infra").glob("*.tf"))
        stage_document = json.loads((APP / "infra/stages.json").read_text())
        assert "AKIA" not in terraform_text
        assert not re.search(r'principal\s*=\s*"\*"', terraform_text)
        assert all("*" not in stage["permissions"] for stage in stage_document["stages"])
