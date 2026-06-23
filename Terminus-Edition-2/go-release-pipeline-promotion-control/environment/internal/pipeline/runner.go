package pipeline

import (
	"fmt"
	"os"
	"path/filepath"
)

func RunPipeline(s Scenario, outDir string) error {
	if err := os.RemoveAll(outDir); err != nil {
		return err
	}
	if err := os.MkdirAll(outDir, 0o755); err != nil {
		return err
	}
	logPath := filepath.Join(outDir, "logs", "pipeline_run.log")
	_ = os.MkdirAll(filepath.Dir(logPath), 0o755)
	_ = os.WriteFile(logPath, []byte(fmt.Sprintf("starting release pipeline build=%s commit=%s branch_tip=%s\n", s.BuildNumber, s.CommitSHA, s.BranchTipSHA)), 0o644)

	build, err := buildArtifact(s, outDir)
	if err != nil {
		return err
	}
	manifest := createArtifactManifest(s, build)
	if err := writeJSON(filepath.Join(outDir, "manifests", "artifact_manifest.json"), manifest); err != nil {
		return err
	}
	if _, err := runUnitTests(manifest, outDir); err != nil {
		return err
	}
	if _, err := runIntegration(manifest, outDir, s.ParallelStages); err != nil {
		return err
	}
	packageReport, err := runPackage(manifest, outDir, s.ParallelStages)
	if err != nil {
		return err
	}
	gate := materializeQualityGate(s, manifest)
	if err := writeJSON(filepath.Join(outDir, "reports", "quality_gate_report.json"), gate); err != nil {
		return err
	}
	return promote(s, manifest, packageReport, gate, outDir)
}
