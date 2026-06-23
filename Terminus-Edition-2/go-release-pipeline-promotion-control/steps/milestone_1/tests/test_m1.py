
import hashlib
import json
import subprocess
from pathlib import Path

APP = Path("/app")

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
    scenario_path = write_json(tmp_path / "scenario.json", scenario)
    out_dir = tmp_path / "out"
    cmd = ["go", "run", "./cmd/pipelinesim", "run", "--scenario", str(scenario_path), "--out", str(out_dir)]
    result = subprocess.run(cmd, cwd=APP, text=True, capture_output=True, timeout=30)
    if expect_ok:
        assert result.returncode == 0, result.stderr + result.stdout
    else:
        assert result.returncode != 0, "pipeline unexpectedly succeeded\nSTDOUT=" + result.stdout + "\nSTDERR=" + result.stderr
    return result, out_dir


class TestMilestone1:
    def test_artifact_identity_survives_branch_tip_movement(self, tmp_path):
        """The manifest, unit report, and release manifest keep the checked-out build commit, not the newer branch tip."""
        scenario = {
            "branch": "release/identity",
            "branch_tip_sha": "tip-999999",
            "commit_sha": "built-111111",
            "build_number": "5101",
            "environment": "staging",
            "parallel_stages": False,
            "quality_gate": {
                "status": "pass",
                "commit_sha": "built-111111",
                "artifact_hash": artifact_digest("built-111111", "5101"),
                "coverage": 91.0,
                "report_id": "qg-5101",
            },
        }
        _, out_dir = run_pipeline(tmp_path, scenario)
        expected_hash = artifact_digest("built-111111", "5101")
        manifest = read_json(out_dir / "manifests" / "artifact_manifest.json")
        unit = read_json(out_dir / "reports" / "unit_report.json")
        release = read_json(out_dir / "release" / "release_manifest.json")
        assert manifest["commit_sha"] == "built-111111"
        assert manifest["commit_sha"] != "tip-999999"
        assert manifest["artifact_hash"] == expected_hash
        assert Path(manifest["artifact_path"]).exists()
        assert "commit=built-111111" in Path(manifest["artifact_path"]).read_text()
        assert unit["commit_sha"] == "built-111111"
        assert release["commit_sha"] == "built-111111"
        assert release["promoted_artifact_hash"] == expected_hash

    def test_manifest_schema_and_stage_names_remain_compatible(self, tmp_path):
        """The fix keeps the public artifact/release/history schemas and Jenkins-visible stage names stable."""
        scenario = {
            "branch": "release/schema",
            "branch_tip_sha": "tip-schema",
            "commit_sha": "commit-schema",
            "build_number": "5102",
            "environment": "prod",
            "parallel_stages": False,
            "quality_gate": {
                "status": "pass",
                "commit_sha": "commit-schema",
                "artifact_hash": artifact_digest("commit-schema", "5102"),
                "coverage": 90.0,
                "report_id": "qg-5102",
            },
        }
        _, out_dir = run_pipeline(tmp_path, scenario)
        manifest = read_json(out_dir / "manifests" / "artifact_manifest.json")
        release = read_json(out_dir / "release" / "release_manifest.json")
        history_path = out_dir / "release" / "release_history.json"
        history = read_json(history_path)
        assert manifest["schema_version"] == "artifact-manifest/v1"
        assert {"build_number", "commit_sha", "artifact_hash", "artifact_path", "created_by"}.issubset(manifest)
        assert release["schema_version"] == "release-manifest/v1"
        assert release["stage_order"] == ["Build", "Unit Test", "Integration Test", "Package", "Quality Gate", "Promote"]
        assert history_path.exists()
        assert history["schema_version"] == "release-history/v1"
        assert isinstance(history["releases"], list)
        assert len(history["releases"]) == 1
        assert {
            "environment",
            "build_number",
            "commit_sha",
            "artifact_hash",
            "promoted_artifact_hash",
            "package_hash",
            "promotion_status",
        }.issubset(history["releases"][0])
        assert history["releases"][0]["promotion_status"] == "promoted"
        assert history["releases"][0]["commit_sha"] == "commit-schema"

    def test_malformed_scenario_fails_without_outputs(self, tmp_path):
        """A missing immutable commit is rejected instead of producing a misleading manifest."""
        scenario = {"branch": "release/bad", "branch_tip_sha": "tip", "build_number": "5103", "environment": "staging"}
        scenario_path = write_json(tmp_path / "bad.json", scenario)
        out_dir = tmp_path / "bad-out"
        result = subprocess.run(["go", "run", "./cmd/pipelinesim", "run", "--scenario", str(scenario_path), "--out", str(out_dir)], cwd=APP, text=True, capture_output=True, timeout=30)
        assert result.returncode != 0
        assert not (out_dir / "manifests" / "artifact_manifest.json").exists()
