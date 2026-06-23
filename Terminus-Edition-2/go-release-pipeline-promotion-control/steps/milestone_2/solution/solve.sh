#!/bin/bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Local oracle validation starts this step from the base image. Restore the
# already-established artifact identity before applying this step's repair.
python3 - <<'PY'
from pathlib import Path
import re

p = Path('/app/internal/pipeline/stages.go')
s = p.read_text()
pattern = r'func manifestCommitSHA\(s Scenario, build BuildResult\) string \{.*?\n\}'
new = 'func manifestCommitSHA(s Scenario, build BuildResult) string {\n\treturn build.CommitSHA\n}'
s, n = re.subn(pattern, new, s, count=1, flags=re.S)
if n != 1:
    raise SystemExit('expected artifact identity function not found')
p.write_text(s)
PY

bash "$SCRIPT_DIR/solve2.sh"
