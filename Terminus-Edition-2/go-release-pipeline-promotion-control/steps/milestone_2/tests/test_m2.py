
import hashlib
import json
import textwrap
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


class TestMilestone2:
    def test_parallel_stages_use_isolated_workspace_state(self, tmp_path):
        """Integration Test and Package do not write/read the same mutable state file during a parallel run."""
        scenario = {
            "branch": "release/parallel",
            "branch_tip_sha": "tip-parallel",
            "commit_sha": "commit-parallel",
            "build_number": "6201",
            "environment": "staging",
            "parallel_stages": True,
            "quality_gate": {
                "status": "pass",
                "commit_sha": "commit-parallel",
                "artifact_hash": artifact_digest("commit-parallel", "6201"),
                "coverage": 88.4,
                "report_id": "qg-6201",
            },
        }
        _, out_dir = run_pipeline(tmp_path, scenario)
        artifact_hash = artifact_digest("commit-parallel", "6201")
        package = read_json(out_dir / "packages" / "package_manifest.json")
        integration = read_json(out_dir / "reports" / "integration_report.json")
        assert package["workspace_contaminated"] is False
        assert package["package_hash"] == package_digest(artifact_hash)
        assert integration["stage_name"] == "Integration Test"
        assert package["stage_name"] == "Package"
        assert Path(integration["workspace"]) == out_dir / "workspace" / "integration"
        assert Path(package["workspace"]) == out_dir / "workspace" / "package"
        assert (out_dir / "workspace" / "integration" / "state.json").exists()
        assert (out_dir / "workspace" / "package" / "state.json").exists()
        assert not (out_dir / "workspace" / "shared" / "state.json").exists()

    def test_package_marks_foreign_workspace_state_as_contaminated(self, tmp_path):
        """Package reports contamination when its state file already belongs to another stage."""
        test_file = APP / "internal" / "pipeline" / "workspace_contamination_test.go"
        test_file.write_text(
            textwrap.dedent(
                r'''
                package pipeline

                import (
                	"os"
                	"path/filepath"
                	"testing"
                )

                func TestPackageReportsForeignWorkspaceState(t *testing.T) {
                	outDir := t.TempDir()
                	workspace := filepath.Join(outDir, "workspace", "package")
                	if err := os.MkdirAll(workspace, 0o755); err != nil {
                		t.Fatal(err)
                	}
                	if err := os.WriteFile(filepath.Join(workspace, "state.json"), []byte(`{"stage":"integration","stage_name":"Integration Test"}`), 0o644); err != nil {
                		t.Fatal(err)
                	}
                	manifest := ArtifactManifest{
                		SchemaVersion: "artifact-manifest/v1",
                		BuildNumber: "6205",
                		CommitSHA: "commit-contamination",
                		ArtifactHash: "artifact-contamination",
                	}
                	report, err := runPackage(manifest, outDir, true)
                	if err != nil {
                		t.Fatal(err)
                	}
                	if !report.WorkspaceContaminated {
                		t.Fatalf("expected workspace_contaminated=true, got false")
                	}
                	if report.PackageHash == packageDigest(manifest.ArtifactHash) {
                		t.Fatalf("contaminated package hash should not equal clean package hash")
                	}
                }
                '''
            ).lstrip()
        )
        try:
            result = subprocess.run(
                ["go", "test", "./internal/pipeline", "-run", "TestPackageReportsForeignWorkspaceState", "-count=1"],
                cwd=APP,
                text=True,
                capture_output=True,
                timeout=30,
            )
            assert result.returncode == 0, result.stderr + result.stdout
        finally:
            test_file.unlink(missing_ok=True)

    def test_package_output_is_stable_across_different_stage_order_symptoms(self, tmp_path):
        """A package hash depends only on the immutable artifact hash, not a transient previous writer."""
        scenario = {
            "branch": "release/stable-package",
            "branch_tip_sha": "moved-tip",
            "commit_sha": "pkg-commit-0001",
            "build_number": "6202",
            "environment": "prod",
            "parallel_stages": True,
            "quality_gate": {
                "status": "pass",
                "commit_sha": "pkg-commit-0001",
                "artifact_hash": artifact_digest("pkg-commit-0001", "6202"),
                "coverage": 90.0,
                "report_id": "qg-6202",
            },
        }
        _, out_dir = run_pipeline(tmp_path, scenario)
        artifact_hash = artifact_digest("pkg-commit-0001", "6202")
        package = read_json(out_dir / "packages" / "package_manifest.json")
        assert package["artifact_hash"] == artifact_hash
        assert package["package_hash"] == package_digest(artifact_hash)
        assert package["stage_name"] == "Package"

    def test_artifact_manifest_schema_survives_workspace_fix(self, tmp_path):
        """Workspace isolation does not change the artifact manifest consumed by downstream stages."""
        scenario = {
            "branch": "release/schema-after-parallel",
            "branch_tip_sha": "tip-after-parallel",
            "commit_sha": "commit-after-parallel",
            "build_number": "6203",
            "environment": "staging",
            "parallel_stages": True,
            "quality_gate": {
                "status": "pass",
                "commit_sha": "commit-after-parallel",
                "artifact_hash": artifact_digest("commit-after-parallel", "6203"),
                "coverage": 90.0,
                "report_id": "qg-6203",
            },
        }
        _, out_dir = run_pipeline(tmp_path, scenario)
        manifest = read_json(out_dir / "manifests" / "artifact_manifest.json")
        assert manifest["schema_version"] == "artifact-manifest/v1"
        assert manifest["commit_sha"] == "commit-after-parallel"
        assert manifest["artifact_hash"] == artifact_digest("commit-after-parallel", "6203")

    def test_sequential_run_keeps_documented_stage_workspaces(self, tmp_path):
        """Sequential execution retains the same integration and package workspace contracts."""
        scenario = {
            "branch": "release/sequential-workspaces",
            "branch_tip_sha": "tip-sequential",
            "commit_sha": "commit-sequential",
            "build_number": "6204",
            "environment": "staging",
            "parallel_stages": False,
            "quality_gate": {
                "status": "pass",
                "commit_sha": "commit-sequential",
                "artifact_hash": artifact_digest("commit-sequential", "6204"),
                "coverage": 89.0,
                "report_id": "qg-6204",
            },
        }
        _, out_dir = run_pipeline(tmp_path, scenario)
        integration = read_json(out_dir / "reports" / "integration_report.json")
        package = read_json(out_dir / "packages" / "package_manifest.json")
        assert Path(integration["workspace"]) == out_dir / "workspace" / "integration"
        assert Path(package["workspace"]) == out_dir / "workspace" / "package"
        assert package["workspace_contaminated"] is False
