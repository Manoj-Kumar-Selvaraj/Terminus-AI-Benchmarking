package pipeline

import (
	"fmt"
	"os"
	"path/filepath"
)

var stageOrder = []string{"Build", "Unit Test", "Integration Test", "Package", "Quality Gate", "Promote"}

func buildArtifact(s Scenario, outDir string) (BuildResult, error) {
	artifactHash := artifactDigest(s.CommitSHA, s.BuildNumber)
	artifactPath := filepath.Join(outDir, "artifacts", s.BuildNumber, artifactHash+".bin")
	if err := os.MkdirAll(filepath.Dir(artifactPath), 0o755); err != nil {
		return BuildResult{}, err
	}
	body := fmt.Sprintf("build=%s\ncommit=%s\nbranch=%s\n", s.BuildNumber, s.CommitSHA, s.Branch)
	if err := os.WriteFile(artifactPath, []byte(body), 0o644); err != nil {
		return BuildResult{}, err
	}
	return BuildResult{BuildNumber: s.BuildNumber, CommitSHA: s.CommitSHA, Branch: s.Branch, ArtifactHash: artifactHash, ArtifactPath: artifactPath}, nil
}

func manifestCommitSHA(s Scenario, build BuildResult) string {
	if s.BranchTipSHA != "" {
		return s.BranchTipSHA
	}
	return build.CommitSHA
}

func createArtifactManifest(s Scenario, build BuildResult) ArtifactManifest {
	return ArtifactManifest{
		SchemaVersion: "artifact-manifest/v1",
		BuildNumber:   build.BuildNumber,
		CommitSHA:     manifestCommitSHA(s, build),
		Branch:        build.Branch,
		ArtifactHash:  build.ArtifactHash,
		ArtifactPath:  build.ArtifactPath,
		CreatedBy:     "Build",
	}
}

func runUnitTests(manifest ArtifactManifest, outDir string) (StageReport, error) {
	report := StageReport{
		Stage:        "unit",
		StageName:    "Unit Test",
		BuildNumber:  manifest.BuildNumber,
		CommitSHA:    manifest.CommitSHA,
		ArtifactHash: manifest.ArtifactHash,
		Workspace:    filepath.Join(outDir, "workspace", "unit"),
		Checks:       []string{"compile", "unit-suite"},
	}
	return report, writeJSON(filepath.Join(outDir, "reports", "unit_report.json"), report)
}

func stageWorkspace(root, stage string, parallel bool) string {
	return filepath.Join(root, "shared")
}

func runIntegration(manifest ArtifactManifest, outDir string, parallel bool) (StageReport, error) {
	workspace := stageWorkspace(filepath.Join(outDir, "workspace"), "integration", parallel)
	if err := os.MkdirAll(workspace, 0o755); err != nil {
		return StageReport{}, err
	}
	report := StageReport{
		Stage:        "integration",
		StageName:    "Integration Test",
		BuildNumber:  manifest.BuildNumber,
		CommitSHA:    manifest.CommitSHA,
		ArtifactHash: manifest.ArtifactHash,
		Workspace:    workspace,
		Checks:       []string{"service-contract", "database-migration"},
	}
	if err := writeJSON(filepath.Join(workspace, "state.json"), report); err != nil {
		return StageReport{}, err
	}
	return report, writeJSON(filepath.Join(outDir, "reports", "integration_report.json"), report)
}

func runPackage(manifest ArtifactManifest, outDir string, parallel bool) (StageReport, error) {
	workspace := stageWorkspace(filepath.Join(outDir, "workspace"), "package", parallel)
	if err := os.MkdirAll(workspace, 0o755); err != nil {
		return StageReport{}, err
	}
	report := StageReport{
		Stage:        "package",
		StageName:    "Package",
		BuildNumber:  manifest.BuildNumber,
		CommitSHA:    manifest.CommitSHA,
		ArtifactHash: manifest.ArtifactHash,
		Workspace:    workspace,
		Checks:       []string{"sbom", "tarball"},
	}
	var prior StageReport
	statePath := filepath.Join(workspace, "state.json")
	if data, err := os.ReadFile(statePath); err == nil {
		if priorErr := jsonUnmarshal(data, &prior); priorErr == nil && prior.Stage != "" && prior.Stage != "package" {
			report.WorkspaceContaminated = true
			report.PackageHash = contaminatedPackageDigest(prior.Stage, manifest.ArtifactHash)
		}
	}
	if report.PackageHash == "" {
		report.PackageHash = packageDigest(manifest.ArtifactHash)
	}
	if err := writeJSON(statePath, report); err != nil {
		return StageReport{}, err
	}
	return report, writeJSON(filepath.Join(outDir, "packages", "package_manifest.json"), report)
}
