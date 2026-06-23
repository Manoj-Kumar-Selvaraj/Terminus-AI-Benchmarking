#!/usr/bin/env bash
set -euo pipefail
cat > /app/internal/pipeline/rollback.go <<'GO'
package pipeline

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
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

type releaseHistoryKeys struct {
	SchemaVersion string `json:"schema_version"`
	KeysByEnv     map[string]struct {
		KeyID  string `json:"key_id"`
		Secret string `json:"secret"`
	} `json:"keys_by_env"`
}

type releaseHistorySignature struct {
	SchemaVersion string `json:"schema_version"`
	Algorithm     string `json:"algorithm"`
	Environment   string `json:"environment"`
	KeyID         string `json:"key_id"`
	HistoryDigest string `json:"history_digest"`
	Signature     string `json:"signature"`
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
	if !okFloor || !okActual || actual < floor {
		return false
	}
	for _, unit := range rec.DeploymentUnits {
		unitVersion, okUnit := parseContractVersion(unit.ReleaseContractVersion)
		if unit.Name == "" || unit.ArtifactHash == "" || unit.PackageHash == "" || !okUnit || unitVersion < floor {
			return false
		}
	}
	return true
}

func rollbackRecordComplete(rec ReleaseRecord) bool {
	return rec.BuildNumber != "" &&
		rec.CommitSHA != "" &&
		rec.ArtifactHash != "" &&
		rec.PromotedArtifactHash != "" &&
		rec.PackageHash != ""
}

func verifyReleaseHistorySignature(history ReleaseHistory, historyPath string, env string) error {
	keyData, err := os.ReadFile("/app/config/release_history_keys.json")
	if err != nil {
		return err
	}
	var keys releaseHistoryKeys
	if err := json.Unmarshal(keyData, &keys); err != nil {
		return err
	}
	if keys.SchemaVersion != "release-history-keys/v1" {
		return fmt.Errorf("unsupported release history key schema")
	}
	key, ok := keys.KeysByEnv[env]
	if !ok || key.KeyID == "" || key.Secret == "" {
		return fmt.Errorf("release history signing key missing for env %q", env)
	}

	sigData, err := os.ReadFile(historyPath + ".sig")
	if err != nil {
		return err
	}
	var submitted releaseHistorySignature
	if err := json.Unmarshal(sigData, &submitted); err != nil {
		return err
	}
	if submitted.SchemaVersion != "release-history-signature/v1" ||
		submitted.Algorithm != "HMAC-SHA256" ||
		submitted.Environment != env ||
		submitted.KeyID != key.KeyID ||
		submitted.Signature == "" {
		return fmt.Errorf("release history signature metadata mismatch")
	}

	mac := hmac.New(sha256.New, []byte(key.Secret))
	digest := sha256.New()
	writers := []canonicalWriter{mac, digest}
	writeSignedPart(writers, "release-history/v1")
	writeSignedPart(writers, history.SchemaVersion)
	for _, rec := range history.Releases {
		writeSignedPart(writers, rec.Environment)
		writeSignedPart(writers, rec.BuildNumber)
		writeSignedPart(writers, rec.CommitSHA)
		writeSignedPart(writers, rec.ArtifactHash)
		writeSignedPart(writers, rec.PromotedArtifactHash)
		writeSignedPart(writers, rec.PackageHash)
		writeSignedPart(writers, rec.PromotionStatus)
		writeSignedPart(writers, rec.ReleaseContractVersion)
		writeSignedPart(writers, strconv.Itoa(len(rec.DeploymentUnits)))
		for _, unit := range rec.DeploymentUnits {
			writeSignedPart(writers, unit.Name)
			writeSignedPart(writers, unit.ArtifactHash)
			writeSignedPart(writers, unit.PackageHash)
			writeSignedPart(writers, unit.ReleaseContractVersion)
		}
	}
	expected := hex.EncodeToString(mac.Sum(nil))
	expectedDigest := hex.EncodeToString(digest.Sum(nil))
	if !hmac.Equal([]byte(strings.ToLower(submitted.HistoryDigest)), []byte(expectedDigest)) {
		return fmt.Errorf("release history digest mismatch")
	}
	if !hmac.Equal([]byte(strings.ToLower(submitted.Signature)), []byte(expected)) {
		return fmt.Errorf("release history signature mismatch")
	}
	return nil
}

type canonicalWriter interface {
	Write([]byte) (int, error)
}

func writeSignedPart(writers []canonicalWriter, part string) {
	for _, writer := range writers {
		_, _ = writer.Write([]byte(part))
		_, _ = writer.Write([]byte{0})
	}
}

func ExecuteRollback(historyPath, outDir, env, targetBuild string) error {
	if env == "" {
		return fmt.Errorf("env is required")
	}
	if err := os.RemoveAll(outDir); err != nil {
		return err
	}
	if err := os.MkdirAll(outDir, 0o755); err != nil {
		return err
	}
	history, err := readHistory(historyPath)
	if err != nil {
		return err
	}
	if err := verifyReleaseHistorySignature(history, historyPath, env); err != nil {
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
	manifest := RollbackManifest{
		SchemaVersion:        "rollback-manifest/v1",
		Environment:          env,
		TargetBuildNumber:    selected.BuildNumber,
		CommitSHA:            selected.CommitSHA,
		ArtifactHash:         selected.ArtifactHash,
		PromotedArtifactHash: selected.PromotedArtifactHash,
		DeploymentUnits:      selected.DeploymentUnits,
		RollbackSource:       "release_history",
		CommandInterface:     "pipelinesim rollback --history PATH --env ENV --out DIR [--target-build BUILD]",
	}
	return writeJSON(filepath.Join(outDir, "rollback_manifest.json"), manifest)
}
GO
/usr/local/go/bin/gofmt -w /app/internal/pipeline/rollback.go
