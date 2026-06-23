
import hashlib
import json
import shutil
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


class TestMilestone3:
    def test_failed_quality_gate_blocks_promotion(self, tmp_path):
        """A failed gate leaves blocked-promotion evidence and no successful release manifest."""
        artifact_hash = artifact_digest("qg-fail-commit", "7301")
        scenario = {
            "branch": "release/qg-fail",
            "branch_tip_sha": "qg-tip",
            "commit_sha": "qg-fail-commit",
            "build_number": "7301",
            "environment": "prod",
            "parallel_stages": True,
            "quality_gate": {"status": "fail", "commit_sha": "qg-fail-commit", "artifact_hash": artifact_hash, "coverage": 52.0, "report_id": "qg-7301"},
        }
        _, out_dir = run_pipeline(tmp_path, scenario, expect_ok=False)
        assert not (out_dir / "release" / "release_manifest.json").exists()
        blocked = read_json(out_dir / "release" / "blocked_promotion.json")
        assert blocked["schema_version"] == "blocked-promotion/v1"
        assert blocked["status"] == "blocked"
        assert "quality" in blocked["reason"].lower() or "gate" in blocked["reason"].lower()

    def test_quality_gate_provenance_must_match_commit_and_artifact(self, tmp_path):
        """A passing-looking gate for another commit or artifact is not accepted for promotion."""
        scenario = {
            "branch": "release/qg-mismatch",
            "branch_tip_sha": "qg-tip-2",
            "commit_sha": "qg-real-commit",
            "build_number": "7302",
            "environment": "staging",
            "parallel_stages": True,
            "quality_gate": {"status": "pass", "commit_sha": "different-commit", "artifact_hash": "not-the-built-artifact", "coverage": 99.0, "report_id": "qg-7302"},
        }
        _, out_dir = run_pipeline(tmp_path, scenario, expect_ok=False)
        assert not (out_dir / "release" / "release_manifest.json").exists()
        blocked = read_json(out_dir / "release" / "blocked_promotion.json")
        assert blocked["status"] == "blocked"
        assert "match" in blocked["reason"].lower() or "provenance" in blocked["reason"].lower()
        assert blocked["artifact_manifest"]["commit_sha"] == "qg-real-commit"
        assert blocked["quality_gate"]["commit_sha"] == "different-commit"

    def test_artifact_hash_mismatch_alone_blocks_promotion(self, tmp_path):
        """A matching commit cannot promote when the gate names a different artifact hash."""
        scenario = {
            "branch": "release/qg-hash-mismatch",
            "branch_tip_sha": "qg-tip-hash",
            "commit_sha": "qg-hash-commit",
            "build_number": "7304",
            "environment": "prod",
            "parallel_stages": True,
            "quality_gate": {
                "status": "pass",
                "commit_sha": "qg-hash-commit",
                "artifact_hash": "wrong-artifact-hash",
                "coverage": 96.0,
                "report_id": "qg-7304",
            },
        }
        _, out_dir = run_pipeline(tmp_path, scenario, expect_ok=False)
        assert not (out_dir / "release" / "release_manifest.json").exists()
        blocked = read_json(out_dir / "release" / "blocked_promotion.json")
        assert blocked["status"] == "blocked"
        assert "artifact" in blocked["reason"].lower()
        assert blocked["quality_gate"]["commit_sha"] == blocked["artifact_manifest"]["commit_sha"]
        assert blocked["quality_gate"]["artifact_hash"] != blocked["artifact_manifest"]["artifact_hash"]

    def test_missing_quality_gate_fails_closed(self, tmp_path):
        """An absent gate must remain absent and block promotion rather than being synthesized as passing."""
        scenario = {
            "branch": "release/qg-missing",
            "branch_tip_sha": "qg-tip-missing",
            "commit_sha": "qg-missing-commit",
            "build_number": "7305",
            "environment": "prod",
            "parallel_stages": True,
        }
        _, out_dir = run_pipeline(tmp_path, scenario, expect_ok=False)
        assert not (out_dir / "release" / "release_manifest.json").exists()
        blocked = read_json(out_dir / "release" / "blocked_promotion.json")
        assert blocked["schema_version"] == "blocked-promotion/v1"
        assert blocked["status"] == "blocked"
        assert "quality" in blocked["reason"].lower() or "gate" in blocked["reason"].lower()
        assert blocked["quality_gate"]["status"] == ""
        assert blocked["quality_gate"]["commit_sha"] == ""
        assert blocked["quality_gate"]["artifact_hash"] == ""
        assert blocked["artifact_manifest"]["commit_sha"] == "qg-missing-commit"
        assert blocked["artifact_manifest"]["artifact_hash"] == artifact_digest("qg-missing-commit", "7305")

    def test_incomplete_quality_gate_fails_closed(self, tmp_path):
        """A present pass gate without explicit commit and artifact provenance is still incomplete."""
        scenario = {
            "branch": "release/qg-incomplete",
            "branch_tip_sha": "qg-tip-incomplete",
            "commit_sha": "qg-incomplete-commit",
            "build_number": "7306",
            "environment": "prod",
            "parallel_stages": True,
            "quality_gate": {
                "status": "pass",
                "commit_sha": "",
                "artifact_hash": "",
                "coverage": 95.0,
                "report_id": "qg-7306",
            },
        }
        _, out_dir = run_pipeline(tmp_path, scenario, expect_ok=False)
        assert not (out_dir / "release" / "release_manifest.json").exists()
        blocked = read_json(out_dir / "release" / "blocked_promotion.json")
        assert blocked["schema_version"] == "blocked-promotion/v1"
        assert blocked["status"] == "blocked"
        assert "match" in blocked["reason"].lower() or "provenance" in blocked["reason"].lower()
        assert blocked["quality_gate"] == scenario["quality_gate"]
        assert blocked["artifact_manifest"]["commit_sha"] == "qg-incomplete-commit"
        assert blocked["artifact_manifest"]["artifact_hash"] == artifact_digest("qg-incomplete-commit", "7306")

    def test_empty_quality_gate_commit_alone_is_provenance_mismatch(self, tmp_path):
        """A passing gate with only commit provenance missing still blocks promotion."""
        artifact_hash = artifact_digest("qg-empty-commit", "7307")
        scenario = {
            "branch": "release/qg-empty-commit",
            "branch_tip_sha": "qg-tip-empty-commit",
            "commit_sha": "qg-empty-commit",
            "build_number": "7307",
            "environment": "prod",
            "parallel_stages": True,
            "quality_gate": {
                "status": "pass",
                "commit_sha": "",
                "artifact_hash": artifact_hash,
                "coverage": 95.0,
                "report_id": "qg-7307",
            },
        }
        _, out_dir = run_pipeline(tmp_path, scenario, expect_ok=False)
        assert not (out_dir / "release" / "release_manifest.json").exists()
        blocked = read_json(out_dir / "release" / "blocked_promotion.json")
        assert blocked["quality_gate"] == scenario["quality_gate"]
        assert "match" in blocked["reason"].lower() or "provenance" in blocked["reason"].lower()

    def test_empty_quality_gate_artifact_alone_is_provenance_mismatch(self, tmp_path):
        """A passing gate with only artifact provenance missing still blocks promotion."""
        scenario = {
            "branch": "release/qg-empty-artifact",
            "branch_tip_sha": "qg-tip-empty-artifact",
            "commit_sha": "qg-empty-artifact",
            "build_number": "7308",
            "environment": "prod",
            "parallel_stages": True,
            "quality_gate": {
                "status": "pass",
                "commit_sha": "qg-empty-artifact",
                "artifact_hash": "",
                "coverage": 95.0,
                "report_id": "qg-7308",
            },
        }
        _, out_dir = run_pipeline(tmp_path, scenario, expect_ok=False)
        assert not (out_dir / "release" / "release_manifest.json").exists()
        blocked = read_json(out_dir / "release" / "blocked_promotion.json")
        assert blocked["quality_gate"] == scenario["quality_gate"]
        assert "match" in blocked["reason"].lower() or "provenance" in blocked["reason"].lower()

    def test_valid_quality_gate_promotes_with_recorded_provenance(self, tmp_path):
        """A valid gate for the exact artifact promotes and records gate provenance in the release manifest."""
        artifact_hash = artifact_digest("qg-good-commit", "7303")
        scenario = {
            "branch": "release/qg-good",
            "branch_tip_sha": "qg-good-tip",
            "commit_sha": "qg-good-commit",
            "build_number": "7303",
            "environment": "prod",
            "parallel_stages": True,
            "quality_gate": {"status": "pass", "commit_sha": "qg-good-commit", "artifact_hash": artifact_hash, "coverage": 92.5, "report_id": "qg-7303"},
        }
        _, out_dir = run_pipeline(tmp_path, scenario)
        release = read_json(out_dir / "release" / "release_manifest.json")
        assert release["promotion_status"] == "promoted"
        assert release["quality_gate"]["status"] == "pass"
        assert release["quality_gate"]["commit_sha"] == release["commit_sha"]
        assert release["quality_gate"]["artifact_hash"] == release["artifact_hash"]
        assert release["promoted_artifact_hash"] == artifact_hash
