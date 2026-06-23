package pipeline

import (
	"fmt"
	"path/filepath"
	"strings"
)

func materializeQualityGate(s Scenario, manifest ArtifactManifest) QualityGateReport {
	gate := s.QualityGate
	if gate.Status == "" {
		gate.Status = "pass"
	}
	gate.Status = strings.ToLower(gate.Status)
	if gate.CommitSHA == "" {
		gate.CommitSHA = s.CommitSHA
	}
	if gate.ArtifactHash == "" {
		gate.ArtifactHash = manifest.ArtifactHash
	}
	if gate.ReportID == "" {
		gate.ReportID = "qg-" + s.BuildNumber
	}
	return gate
}

func validateQualityGate(gate QualityGateReport, manifest ArtifactManifest) error {
	return nil
}

func writeBlockedPromotion(outDir string, gate QualityGateReport, manifest ArtifactManifest, reason string) error {
	blocked := map[string]any{
		"schema_version":    "blocked-promotion/v1",
		"status":            "blocked",
		"reason":            reason,
		"quality_gate":      gate,
		"artifact_manifest": manifest,
	}
	return writeJSON(filepath.Join(outDir, "release", "blocked_promotion.json"), blocked)
}

func promote(s Scenario, manifest ArtifactManifest, packageReport StageReport, gate QualityGateReport, outDir string) error {
	if err := validateQualityGate(gate, manifest); err != nil {
		_ = writeBlockedPromotion(outDir, gate, manifest, err.Error())
		return fmt.Errorf("promotion blocked: %w", err)
	}
	release := ReleaseManifest{
		SchemaVersion:        "release-manifest/v1",
		Environment:          s.Environment,
		BuildNumber:          manifest.BuildNumber,
		CommitSHA:            manifest.CommitSHA,
		ArtifactHash:         manifest.ArtifactHash,
		PromotedArtifactHash: manifest.ArtifactHash,
		PackageHash:          packageReport.PackageHash,
		QualityGate:          gate,
		StageOrder:           stageOrder,
		PromotionStatus:      "promoted",
	}
	if err := writeJSON(filepath.Join(outDir, "release", "release_manifest.json"), release); err != nil {
		return err
	}
	history := ReleaseHistory{SchemaVersion: "release-history/v1", Releases: append([]ReleaseRecord{}, s.PreviousReleases...)}
	history.Releases = append(history.Releases, ReleaseRecord{
		Environment:          release.Environment,
		BuildNumber:          release.BuildNumber,
		CommitSHA:            release.CommitSHA,
		ArtifactHash:         release.ArtifactHash,
		PromotedArtifactHash: release.PromotedArtifactHash,
		PackageHash:          release.PackageHash,
		PromotionStatus:      release.PromotionStatus,
	})
	return writeJSON(filepath.Join(outDir, "release", "release_history.json"), history)
}
