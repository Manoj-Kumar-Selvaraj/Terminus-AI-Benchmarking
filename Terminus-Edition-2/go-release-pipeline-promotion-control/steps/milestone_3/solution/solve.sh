#!/bin/bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Local oracle validation starts this step from the base image. Restore the
# previously established artifact identity and workspace isolation first.
python3 - <<'PY'
from pathlib import Path
import re

p = Path('/app/internal/pipeline/stages.go')
s = p.read_text()
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
p.write_text(s)
PY

bash "$SCRIPT_DIR/solve3.sh"
