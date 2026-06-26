# ruff: noqa: E501, E701, E702
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

APP = Path(os.environ.get("APP_DIR", "/app"))
SIM = APP / "tools/ec2sim.py"
CFG = APP / "infra/envs/prod/ec2_config.json"
SIM_SHA256 = "9851bac92692323fc8f9cf518baad7186d0729ab892ad3f5b0f8d8d34cca42b3"
MANIFEST_FIELDS = (
    "manifest_version",
    "ami_id",
    "ami_owner_account_id",
    "architecture",
    "commit_sha",
    "build_id",
    "user_data_sha256",
)


def config():
    return json.loads(CFG.read_text(encoding="utf-8"))


def manifest_digest(artifact):
    payload = {field: artifact[field] for field in MANIFEST_FIELDS}
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def run_sim(command, cfg, prior=None, state=None, journal=None):
    with tempfile.TemporaryDirectory() as temp_dir:
        temp = Path(temp_dir)
        config_path = temp / "config.json"
        output_path = temp / "output.json"
        config_path.write_text(json.dumps(cfg), encoding="utf-8")
        args = [
            sys.executable,
            str(SIM),
            command,
            "--config",
            str(config_path),
            "--out",
            str(output_path),
        ]
        if prior is not None:
            prior_path = temp / "prior.json"
            prior_path.write_text(json.dumps(prior), encoding="utf-8")
            args += ["--prior-state", str(prior_path)]
        if state is not None:
            args += ["--state", str(state)]
        if journal is not None:
            args += ["--journal", str(journal)]
        result = subprocess.run(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return result, json.loads(output_path.read_text(encoding="utf-8"))


class TestMilestone1:
    def test_simulator_cli_integrity(self):
        """The harness CLI remains unchanged while the EC2 module is repaired."""
        assert hashlib.sha256(SIM.read_bytes()).hexdigest() == SIM_SHA256

    def test_launch_template_uses_approved_release_identity(self):
        """AMI, bootstrap hash, architecture, and provenance come from the approved manifest."""
        cfg = config()
        result, state = run_sim("plan", cfg)
        assert result.returncode == 0
        artifact = cfg["release_artifact"]
        template = state["launch_template"]
        assert template["ami_id"] == artifact["ami_id"]
        assert template["ami_id"] != cfg["ami_catalog"]["latest"]
        assert template["architecture"] == artifact["architecture"]
        assert template["user_data_sha256"] == artifact["user_data_sha256"]
        assert template["provenance"] == {
            "commit_sha": artifact["commit_sha"],
            "build_id": artifact["build_id"],
            "manifest_sha256": artifact["manifest_sha256"],
        }

    def test_manifest_digest_matches_normative_canonical_schema(self):
        """The rendered identity carries the canonical manifest digest, not a sample constant."""
        cfg = config()
        result, state = run_sim("plan", cfg)
        assert result.returncode == 0
        expected = manifest_digest(cfg["release_artifact"])
        assert cfg["release_artifact"]["manifest_sha256"] == expected
        assert state["release_identity"]["manifest_sha256"] == expected
        assert state["launch_template"]["tags"]["ReleaseManifestSha256"] == expected

    @pytest.mark.parametrize(
        "field",
        [
            "manifest_version",
            "ami_id",
            "ami_owner_account_id",
            "architecture",
            "commit_sha",
            "build_id",
            "user_data_sha256",
            "manifest_sha256",
        ],
    )
    def test_missing_manifest_fields_fail_closed(self, field):
        """Every field in the release identity schema is mandatory and named in errors."""
        cfg = config()
        del cfg["release_artifact"][field]
        result, output = run_sim("validate", cfg)
        assert result.returncode != 0
        assert output["valid"] is False
        assert f"release_artifact.{field}" in output["error"]

    def test_tampered_manifest_digest_fails_closed(self):
        """Changing an attested field without recomputing the digest is rejected."""
        cfg = config()
        cfg["release_artifact"]["build_id"] = "build-tampered"
        result, output = run_sim("validate", cfg)
        assert result.returncode != 0
        assert "manifest_sha256" in output["error"]

    def test_unknown_ami_fails_closed(self):
        """An attested AMI must also exist in the offline catalog."""
        cfg = config()
        cfg["release_artifact"]["ami_id"] = "ami-not-catalogued"
        cfg["release_artifact"]["manifest_sha256"] = manifest_digest(cfg["release_artifact"])
        result, output = run_sim("validate", cfg)
        assert result.returncode != 0
        assert "ami_catalog.images" in output["error"]

    @pytest.mark.parametrize(
        ("catalog_field", "catalog_value", "error_fragment"),
        [
            ("owner_account_id", "999900001111", "owner"),
            ("architecture", "arm64", "architecture"),
            ("state", "pending", "available"),
            ("deprecated", True, "deprecated"),
        ],
    )
    def test_catalog_provenance_mismatch_fails_closed(
        self, catalog_field, catalog_value, error_fragment
    ):
        """Catalog owner, architecture, availability, and deprecation are enforced."""
        cfg = config()
        image = cfg["ami_catalog"]["images"][cfg["release_artifact"]["ami_id"]]
        image[catalog_field] = catalog_value
        result, output = run_sim("validate", cfg)
        assert result.returncode != 0
        assert error_fragment in output["error"].lower()

    def test_launch_template_version_is_deterministic_under_key_reordering(self):
        """Canonical hashing makes equivalent configuration ordering produce one version."""
        cfg = config()
        result_a, state_a = run_sim("plan", cfg)
        reordered = json.loads(json.dumps(cfg, sort_keys=True))
        reordered["release_artifact"] = dict(
            reversed(list(reordered["release_artifact"].items()))
        )
        result_b, state_b = run_sim("plan", reordered)
        assert result_a.returncode == result_b.returncode == 0
        assert state_a["launch_template"]["version"] == state_b["launch_template"]["version"]
        assert state_a["state_digest"] == state_b["state_digest"]

    def test_same_release_replan_preserves_template_and_instance_identity(self):
        """Replanning an unchanged approved release is stable instead of synthesizing identities."""
        cfg = config()
        first_result, first = run_sim("plan", cfg)
        second_result, second = run_sim("plan", cfg, prior=first)
        assert first_result.returncode == second_result.returncode == 0
        assert first["launch_template"]["version"] == second["launch_template"]["version"]
        assert first["outputs"]["instance_ids"] == second["outputs"]["instance_ids"]
        assert not any(action["action"] == "rolling_replace" for action in second["plan_actions"])

    def test_instance_tags_preserve_exact_release_provenance(self):
        """Every logical instance receives exact commit, build, slot, and manifest tags."""
        cfg = config()
        result, state = run_sim("plan", cfg)
        assert result.returncode == 0
        artifact = cfg["release_artifact"]
        for slot, instance in enumerate(state["instances"]):
            assert instance["tags"]["Slot"] == str(slot)
            assert instance["tags"]["CommitSha"] == artifact["commit_sha"]
            assert instance["tags"]["BuildId"] == artifact["build_id"]
            assert instance["tags"]["ReleaseManifestSha256"] == artifact["manifest_sha256"]

    def test_apply_accepts_state_and_journal_flags_and_writes_atomically(self, tmp_path):
        """Apply honors compatibility flags and writes a complete state plus durable journal record."""
        cfg = config()
        state_path = tmp_path / "nested" / "state.json"
        journal_path = tmp_path / "journal" / "rollout.jsonl"
        result, output = run_sim(
            "apply", cfg, prior={}, state=state_path, journal=journal_path
        )
        assert result.returncode == 0
        assert json.loads(state_path.read_text(encoding="utf-8")) == output
        records = [json.loads(line) for line in journal_path.read_text().splitlines()]
        assert len(records) == 1
        assert records[0]["release_manifest_sha256"] == cfg["release_artifact"]["manifest_sha256"]
        assert records[0]["state_digest"] == output["state_digest"]
