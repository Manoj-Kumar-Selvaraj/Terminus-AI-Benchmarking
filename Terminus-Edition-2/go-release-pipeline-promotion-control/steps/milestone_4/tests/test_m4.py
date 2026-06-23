
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import pytest

APP = Path("/app")
COMMAND_INTERFACE = "pipelinesim rollback --history PATH --env ENV --out DIR [--target-build BUILD]"

def digest(*parts: str) -> str:
    """Hash length-delimited strings using the simulator's digest contract."""
    h = hashlib.sha256()
    for part in parts:
        h.update(part.encode())
        h.update(b"\x00")
    return h.hexdigest()

def artifact_digest(commit: str, build: str) -> str:
    """Return the expected immutable artifact digest."""
    return digest("artifact", commit, build)

def package_digest(artifact_hash: str) -> str:
    """Return the expected package digest for an artifact."""
    return digest("package", artifact_hash)

def write_json(path: Path, value: dict) -> Path:
    """Write a JSON fixture and return its path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n")
    return path

def read_json(path: Path) -> dict:
    """Read a generated JSON artifact."""
    return json.loads(path.read_text())

def run_pipeline(tmp_path: Path, scenario: dict, expect_ok: bool = True):
    """Run the real pipeline simulator against a temporary scenario."""
    out_dir = tmp_path / "out"
    scenario_path = tmp_path / "scenario.json"
    if out_dir.exists():
        shutil.rmtree(out_dir)
    if scenario_path.exists():
        scenario_path.unlink()
    scenario_path = write_json(scenario_path, scenario)
    cmd = ["go", "run", "./cmd/pipelinesim", "run", "--scenario", str(scenario_path), "--out", str(out_dir)]
    result = subprocess.run(cmd, cwd=APP, text=True, capture_output=True, timeout=30)
    if expect_ok:
        assert result.returncode == 0, result.stderr + result.stdout
    else:
        assert result.returncode != 0, "pipeline unexpectedly succeeded\nSTDOUT=" + result.stdout + "\nSTDERR=" + result.stderr
    return result, out_dir


def run_rollback(tmp_path: Path, history: dict, env: str = "prod", target_build: str = "", expect_ok: bool = True):
    """Run the real rollback command against temporary release history."""
    out_dir = tmp_path / "rollback"
    history_path = tmp_path / "release_history.json"
    if out_dir.exists():
        shutil.rmtree(out_dir)
    if history_path.exists():
        history_path.unlink()
    history_path = write_json(history_path, history)
    cmd = ["go", "run", "./cmd/pipelinesim", "rollback", "--history", str(history_path), "--env", env, "--out", str(out_dir)]
    if target_build:
        cmd.extend(["--target-build", target_build])
    result = subprocess.run(cmd, cwd=APP, text=True, capture_output=True, timeout=30)
    if expect_ok:
        assert result.returncode == 0, result.stderr + result.stdout
    else:
        assert result.returncode != 0, "rollback unexpectedly succeeded\nSTDOUT=" + result.stdout + "\nSTDERR=" + result.stderr
    return result, out_dir

class TestMilestone4:
    def test_default_rollback_redeploys_previous_promoted_artifact(self, tmp_path):
        """Default rollback chooses the previous successful release for the requested environment, not HEAD."""
        history = {"schema_version": "release-history/v1", "releases": [
            {"environment": "prod", "build_number": "8401", "commit_sha": "old-prod", "artifact_hash": "artifact-old", "promoted_artifact_hash": "promoted-old", "package_hash": "pkg-old", "promotion_status": "promoted", "release_contract_version": "2024.11"},
            {"environment": "staging", "build_number": "8401", "commit_sha": "old-stg", "artifact_hash": "artifact-stg", "promoted_artifact_hash": "promoted-stg", "package_hash": "pkg-stg", "promotion_status": "promoted", "release_contract_version": "2024.11"},
            {"environment": "prod", "build_number": "8402", "commit_sha": "new-prod", "artifact_hash": "artifact-new", "promoted_artifact_hash": "promoted-new", "package_hash": "pkg-new", "promotion_status": "promoted", "release_contract_version": "2024.11"},
        ]}
        _, out_dir = run_rollback(tmp_path, history, env="prod")
        manifest = read_json(out_dir / "rollback_manifest.json")
        assert manifest["schema_version"] == "rollback-manifest/v1"
        assert manifest["environment"] == "prod"
        assert manifest["target_build_number"] == "8401"
        assert manifest["commit_sha"] == "old-prod"
        assert manifest["artifact_hash"] == "artifact-old"
        assert manifest["promoted_artifact_hash"] == "promoted-old"
        assert manifest["rollback_source"] == "release_history"
        assert manifest["command_interface"] == COMMAND_INTERFACE
        assert manifest["commit_sha"] != "HEAD"

    def test_explicit_target_build_redeploys_that_history_record(self, tmp_path):
        """The compatible --target-build flag selects an explicit promoted artifact from the same environment."""
        history = {"schema_version": "release-history/v1", "releases": [
            {"environment": "prod", "build_number": "8500", "commit_sha": "prod-8500", "artifact_hash": "artifact-8500", "promoted_artifact_hash": "promoted-8500", "package_hash": "pkg-8500", "promotion_status": "promoted", "release_contract_version": "2024.11"},
            {"environment": "prod", "build_number": "8501", "commit_sha": "prod-8501", "artifact_hash": "artifact-8501", "promoted_artifact_hash": "promoted-8501", "package_hash": "pkg-8501", "promotion_status": "promoted", "release_contract_version": "2024.11"},
        ]}
        _, out_dir = run_rollback(tmp_path, history, env="prod", target_build="8500")
        manifest = read_json(out_dir / "rollback_manifest.json")
        assert manifest["target_build_number"] == "8500"
        assert manifest["artifact_hash"] == "artifact-8500"
        assert manifest["promoted_artifact_hash"] == "promoted-8500"
        assert manifest["command_interface"] == COMMAND_INTERFACE

    def test_default_rollback_ignores_newer_non_promoted_records(self, tmp_path):
        """Failed or pending records do not participate in previous-promoted release selection."""
        history = {"schema_version": "release-history/v1", "releases": [
            {"environment": "prod", "build_number": "8600", "commit_sha": "prod-8600", "artifact_hash": "artifact-8600", "promoted_artifact_hash": "promoted-8600", "package_hash": "pkg-8600", "promotion_status": "promoted", "release_contract_version": "2024.11"},
            {"environment": "prod", "build_number": "8601", "commit_sha": "prod-8601", "artifact_hash": "artifact-8601", "promoted_artifact_hash": "promoted-8601", "package_hash": "pkg-8601", "promotion_status": "promoted", "release_contract_version": "2024.11"},
            {"environment": "prod", "build_number": "8602", "commit_sha": "prod-8602", "artifact_hash": "artifact-8602", "promoted_artifact_hash": "promoted-8602", "package_hash": "pkg-8602", "promotion_status": "failed", "release_contract_version": "INVALID"},
            {"environment": "prod", "build_number": "8603", "commit_sha": "prod-8603", "artifact_hash": "artifact-8603", "promoted_artifact_hash": "promoted-8603", "package_hash": "pkg-8603", "promotion_status": "pending"},
        ]}

        _, out_dir = run_rollback(tmp_path, history, env="prod")
        manifest = read_json(out_dir / "rollback_manifest.json")

        assert manifest["target_build_number"] == "8600"
        assert manifest["artifact_hash"] == "artifact-8600"
        assert manifest["promoted_artifact_hash"] == "promoted-8600"

    def test_default_rollback_requires_a_previous_promoted_record(self, tmp_path):
        """The most recent promoted record is excluded, so a single promoted record leaves no rollback target."""
        history = {"schema_version": "release-history/v1", "releases": [
            {"environment": "prod", "build_number": "8650", "commit_sha": "prod-8650", "artifact_hash": "artifact-8650", "promoted_artifact_hash": "promoted-8650", "package_hash": "pkg-8650", "promotion_status": "promoted", "release_contract_version": "2024.11"},
            {"environment": "prod", "build_number": "8651", "commit_sha": "prod-8651", "artifact_hash": "artifact-8651", "promoted_artifact_hash": "promoted-8651", "package_hash": "pkg-8651", "promotion_status": "failed"},
        ]}

        _, out_dir = run_rollback(tmp_path, history, env="prod", expect_ok=False)

        assert not (out_dir / "rollback_manifest.json").exists()

    @pytest.mark.parametrize(
        ("target_build", "records"),
        [
            (
                "8700",
                [
                    {"environment": "staging", "build_number": "8700", "commit_sha": "stg-8700", "artifact_hash": "artifact-stg", "promoted_artifact_hash": "promoted-stg", "package_hash": "pkg-stg", "promotion_status": "promoted", "release_contract_version": "2024.11"},
                ],
            ),
            (
                "8701",
                [
                    {"environment": "prod", "build_number": "8701", "commit_sha": "prod-8701", "artifact_hash": "artifact-failed", "promoted_artifact_hash": "promoted-failed", "package_hash": "pkg-failed", "promotion_status": "failed"},
                ],
            ),
            (
                "8799",
                [
                    {"environment": "prod", "build_number": "8798", "commit_sha": "prod-8798", "artifact_hash": "artifact-existing", "promoted_artifact_hash": "promoted-existing", "package_hash": "pkg-existing", "promotion_status": "promoted", "release_contract_version": "2024.11"},
                ],
            ),
        ],
    )
    def test_explicit_target_rejects_wrong_environment_non_promoted_or_absent_record(self, tmp_path, target_build, records):
        """Explicit rollback targets must be existing promoted records from the requested environment."""
        history = {"schema_version": "release-history/v1", "releases": records}

        _, out_dir = run_rollback(
            tmp_path,
            history,
            env="prod",
            target_build=target_build,
            expect_ok=False,
        )

        assert not (out_dir / "rollback_manifest.json").exists()

    def test_malformed_or_missing_history_fails_closed(self, tmp_path):
        """Malformed history does not produce a successful rollback manifest."""
        bad_history = {"schema_version": "release-history/v1", "records": []}
        _, out_dir = run_rollback(tmp_path, bad_history, env="prod", expect_ok=False)
        assert not (out_dir / "rollback_manifest.json").exists()

    def test_missing_history_file_fails_closed(self, tmp_path):
        """A nonexistent history path returns an error and writes no rollback manifest."""
        out_dir = tmp_path / "rollback-missing"
        if out_dir.exists():
            shutil.rmtree(out_dir)
        cmd = [
            "go",
            "run",
            "./cmd/pipelinesim",
            "rollback",
            "--history",
            str(tmp_path / "does-not-exist.json"),
            "--env",
            "prod",
            "--out",
            str(out_dir),
        ]
        result = subprocess.run(cmd, cwd=APP, text=True, capture_output=True, timeout=30)
        assert result.returncode != 0
        assert not (out_dir / "rollback_manifest.json").exists()

    def test_default_rollback_skips_promoted_records_below_environment_contract_floor(self, tmp_path):
        """Compatibility filtering happens before excluding the most recent eligible promoted record."""
        history = {"schema_version": "release-history/v1", "releases": [
            {"environment": "prod", "build_number": "8900", "commit_sha": "prod-8900", "artifact_hash": "artifact-8900", "promoted_artifact_hash": "promoted-8900", "package_hash": "pkg-8900", "promotion_status": "promoted", "release_contract_version": "2024.10"},
            {"environment": "prod", "build_number": "8901", "commit_sha": "prod-8901", "artifact_hash": "artifact-8901", "promoted_artifact_hash": "promoted-8901", "package_hash": "pkg-8901", "promotion_status": "promoted", "release_contract_version": "2024.04"},
            {"environment": "prod", "build_number": "8902", "commit_sha": "prod-8902", "artifact_hash": "artifact-8902", "promoted_artifact_hash": "promoted-8902", "package_hash": "pkg-8902", "promotion_status": "promoted", "release_contract_version": "2024.11"},
        ]}

        _, out_dir = run_rollback(tmp_path, history, env="prod")
        manifest = read_json(out_dir / "rollback_manifest.json")

        assert manifest["target_build_number"] == "8900"
        assert manifest["artifact_hash"] == "artifact-8900"
        assert manifest["promoted_artifact_hash"] == "promoted-8900"

    @pytest.mark.parametrize("bad_version", ["2024.09", "", "2024-Q4"])
    def test_explicit_target_rejects_contract_version_below_or_outside_floor(self, tmp_path, bad_version):
        """Explicit rollback cannot bypass the environment release-contract compatibility floor."""
        history = {"schema_version": "release-history/v1", "releases": [
            {"environment": "prod", "build_number": "8910", "commit_sha": "prod-8910", "artifact_hash": "artifact-8910", "promoted_artifact_hash": "promoted-8910", "package_hash": "pkg-8910", "promotion_status": "promoted", "release_contract_version": bad_version},
            {"environment": "prod", "build_number": "8911", "commit_sha": "prod-8911", "artifact_hash": "artifact-8911", "promoted_artifact_hash": "promoted-8911", "package_hash": "pkg-8911", "promotion_status": "promoted", "release_contract_version": "2024.11"},
        ]}

        _, out_dir = run_rollback(
            tmp_path,
            history,
            env="prod",
            target_build="8910",
            expect_ok=False,
        )

        assert not (out_dir / "rollback_manifest.json").exists()
