#!/bin/bash
set -euo pipefail
python3 - <<'PY'
from pathlib import Path
import re
p = Path('/app/internal/pipeline/quality.go')
s = p.read_text()
pattern = r'func materializeQualityGate\(s Scenario, manifest ArtifactManifest\) QualityGateReport \{.*?\n\}'
new = '''func materializeQualityGate(s Scenario, manifest ArtifactManifest) QualityGateReport {
	gate := s.QualityGate
	gate.Status = strings.ToLower(gate.Status)
	return gate
}'''
s, n = re.subn(pattern, new, s, count=1, flags=re.S)
if n != 1:
    raise SystemExit('expected quality gate materialization function not found')
pattern = r'func validateQualityGate\(gate QualityGateReport, manifest ArtifactManifest\) error \{.*?\n\}'
new = '''func validateQualityGate(gate QualityGateReport, manifest ArtifactManifest) error {
	if strings.ToLower(gate.Status) != "pass" {
		return fmt.Errorf("quality gate status is %q", gate.Status)
	}
	if gate.CommitSHA == "" || gate.CommitSHA != manifest.CommitSHA {
		return fmt.Errorf("quality gate commit %q does not match artifact commit %q", gate.CommitSHA, manifest.CommitSHA)
	}
	if gate.ArtifactHash == "" || gate.ArtifactHash != manifest.ArtifactHash {
		return fmt.Errorf("quality gate artifact %q does not match promoted artifact %q", gate.ArtifactHash, manifest.ArtifactHash)
	}
	return nil
}'''
s2, n = re.subn(pattern, new, s, count=1, flags=re.S)
if n != 1:
    raise SystemExit('expected M3 validateQualityGate function not found')
p.write_text(s2)
PY
