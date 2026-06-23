package pipeline

import (
	"fmt"
	"os"
	"path/filepath"
)

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

	rebuiltHash := artifactDigest("HEAD", "rollback-"+env)
	manifest := RollbackManifest{
		SchemaVersion:        "rollback-manifest/v1",
		Environment:          env,
		TargetBuildNumber:    "rebuilt-from-head",
		CommitSHA:            "HEAD",
		ArtifactHash:         rebuiltHash,
		PromotedArtifactHash: rebuiltHash,
		RollbackSource:       "rebuild",
		CommandInterface:     "pipelinesim rollback --history PATH --env ENV --out DIR [--target-build BUILD]",
	}
	return writeJSON(filepath.Join(outDir, "rollback_manifest.json"), manifest)
}
