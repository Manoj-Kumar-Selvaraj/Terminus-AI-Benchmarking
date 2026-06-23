package pipeline

import (
	"crypto/sha256"
	"encoding/hex"
)

func digest(parts ...string) string {
	h := sha256.New()
	for _, part := range parts {
		h.Write([]byte(part))
		h.Write([]byte{0})
	}
	return hex.EncodeToString(h.Sum(nil))
}

func artifactDigest(commitSHA, buildNumber string) string {
	return digest("artifact", commitSHA, buildNumber)
}

func packageDigest(artifactHash string) string {
	return digest("package", artifactHash)
}

func contaminatedPackageDigest(stage string, artifactHash string) string {
	return digest("contaminated", stage, artifactHash)
}
