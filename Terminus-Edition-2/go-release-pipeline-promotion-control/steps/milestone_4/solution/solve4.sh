#!/usr/bin/env bash
set -euo pipefail
cat > /app/internal/pipeline/rollback.go <<'GO'
package pipeline

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"
)

type rollbackPolicy struct {
	Rollback struct {
		MinimumReleaseContractByEnv map[string]string `json:"minimum_release_contract_by_env"`
	} `json:"rollback"`
}

func loadRollbackContractFloors(path string) (map[string]string, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var policy rollbackPolicy
	if err := json.Unmarshal(data, &policy); err != nil {
		return nil, err
	}
	if policy.Rollback.MinimumReleaseContractByEnv == nil {
		return nil, fmt.Errorf("rollback compatibility floors missing")
	}
	return policy.Rollback.MinimumReleaseContractByEnv, nil
}

func parseContractVersion(version string) (int, bool) {
	parts := strings.Split(strings.TrimSpace(version), ".")
	if len(parts) != 2 || len(parts[0]) != 4 || len(parts[1]) != 2 {
		return 0, false
	}
	year, errYear := strconv.Atoi(parts[0])
	month, errMonth := strconv.Atoi(parts[1])
	if errYear != nil || errMonth != nil || month < 1 || month > 12 {
		return 0, false
	}
	return year*100 + month, true
}

func rollbackCompatible(rec ReleaseRecord, env string, floors map[string]string) bool {
	floorText, ok := floors[env]
	if !ok {
		return false
	}
	floor, okFloor := parseContractVersion(floorText)
	actual, okActual := parseContractVersion(rec.ReleaseContractVersion)
	return okFloor && okActual && actual >= floor
}

func rollbackRecordComplete(rec ReleaseRecord) bool {
	return rec.BuildNumber != "" &&
		rec.CommitSHA != "" &&
		rec.ArtifactHash != "" &&
		rec.PromotedArtifactHash != "" &&
		rec.PackageHash != ""
}

func ExecuteRollback(historyPath, outDir, env, targetBuild string) error {
	if env == "" {
		return fmt.Errorf("env is required")
	}
	history, err := readHistory(historyPath)
	if err != nil {
		return err
	}
	floors, err := loadRollbackContractFloors("/app/config/pipeline_policy.json")
	if err != nil {
		return err
	}
	var selected *ReleaseRecord
	if targetBuild != "" {
		for i := range history.Releases {
			rec := &history.Releases[i]
			if rec.Environment == env &&
				rec.BuildNumber == targetBuild &&
				rec.PromotionStatus == "promoted" &&
				rollbackCompatible(*rec, env, floors) {
				selected = rec
			}
		}
	} else {
		matches := make([]ReleaseRecord, 0)
		for _, rec := range history.Releases {
			if rec.Environment == env &&
				rec.PromotionStatus == "promoted" &&
				rollbackCompatible(rec, env, floors) {
				matches = append(matches, rec)
			}
		}
		if len(matches) >= 2 {
			selected = &matches[len(matches)-2]
		}
	}
	if selected == nil {
		return fmt.Errorf("no compatible promoted release history record found for environment %q", env)
	}
	if !rollbackRecordComplete(*selected) {
		return fmt.Errorf("selected release history record is incomplete")
	}
	if err := os.RemoveAll(outDir); err != nil {
		return err
	}
	if err := os.MkdirAll(outDir, 0o755); err != nil {
		return err
	}
	manifest := RollbackManifest{
		SchemaVersion:        "rollback-manifest/v1",
		Environment:          env,
		TargetBuildNumber:    selected.BuildNumber,
		CommitSHA:            selected.CommitSHA,
		ArtifactHash:         selected.ArtifactHash,
		PromotedArtifactHash: selected.PromotedArtifactHash,
		RollbackSource:       "release_history",
		CommandInterface:     "pipelinesim rollback --history PATH --env ENV --out DIR [--target-build BUILD]",
	}
	return writeJSON(filepath.Join(outDir, "rollback_manifest.json"), manifest)
}
GO
