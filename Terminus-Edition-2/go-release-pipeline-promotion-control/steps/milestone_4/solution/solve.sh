#!/bin/bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Local oracle validation starts this step from the base image. Restore the
# previously established pipeline protections before applying rollback repair.
python3 - <<'PY'
from pathlib import Path
import re

stages = Path('/app/internal/pipeline/stages.go')
s = stages.read_text()
replacements = [
    (
        r'func manifestCommitSHA\(s Scenario, build BuildResult\) string \{.*?\n\}',
        'func manifestCommitSHA(s Scenario, build BuildResult) string {\n\treturn build.CommitSHA\n}',
        'artifact identity function',
    ),
    (
        r'func stageWorkspace\(root, stage string, parallel bool\) string \{.*?\n\}',
        'func stageWorkspace(root, stage string, parallel bool) string {\n\treturn filepath.Join(root, stage)\n}',
        'workspace isolation function',
    ),
]
for pattern, replacement, label in replacements:
    s, n = re.subn(pattern, replacement, s, count=1, flags=re.S)
    if n != 1:
        raise SystemExit(f'expected {label} not found')
stages.write_text(s)

quality = Path('/app/internal/pipeline/quality.go')
q = quality.read_text()
replacements = [
    (
        r'func materializeQualityGate\(s Scenario, manifest ArtifactManifest\) QualityGateReport \{.*?\n\}',
        '''func materializeQualityGate(s Scenario, manifest ArtifactManifest) QualityGateReport {
\tgate := s.QualityGate
\tgate.Status = strings.ToLower(gate.Status)
\treturn gate
}''',
        'quality gate materialization function',
    ),
    (
        r'func validateQualityGate\(gate QualityGateReport, manifest ArtifactManifest\) error \{.*?\n\}',
        '''func validateQualityGate(gate QualityGateReport, manifest ArtifactManifest) error {
\tif strings.ToLower(gate.Status) != "pass" {
\t\treturn fmt.Errorf("quality gate status is %q", gate.Status)
\t}
\tif gate.CommitSHA == "" || gate.CommitSHA != manifest.CommitSHA {
\t\treturn fmt.Errorf("quality gate commit %q does not match artifact commit %q", gate.CommitSHA, manifest.CommitSHA)
\t}
\tif gate.ArtifactHash == "" || gate.ArtifactHash != manifest.ArtifactHash {
\t\treturn fmt.Errorf("quality gate artifact %q does not match promoted artifact %q", gate.ArtifactHash, manifest.ArtifactHash)
\t}
\treturn nil
}''',
        'quality gate validation function',
    ),
]
for pattern, replacement, label in replacements:
    q, n = re.subn(pattern, replacement, q, count=1, flags=re.S)
    if n != 1:
        raise SystemExit(f'expected {label} not found')
quality.write_text(q)
PY

bash "$SCRIPT_DIR/solve4.sh"
