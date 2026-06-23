#!/bin/bash
set -euo pipefail
python3 - <<'PY'
from pathlib import Path
import re
p = Path('/app/internal/pipeline/stages.go')
s = p.read_text()
pattern = r'func manifestCommitSHA\(s Scenario, build BuildResult\) string \{.*?\n\}'
new = 'func manifestCommitSHA(s Scenario, build BuildResult) string {\n\treturn build.CommitSHA\n}'
s2, n = re.subn(pattern, new, s, count=1, flags=re.S)
if n != 1:
    raise SystemExit('expected M1 manifestCommitSHA function not found')
p.write_text(s2)
PY
