#!/bin/bash
set -euo pipefail
python3 - <<'PY'
from pathlib import Path
import re
p = Path('/app/internal/pipeline/stages.go')
s = p.read_text()
pattern = r'func stageWorkspace\(root, stage string, parallel bool\) string \{.*?\n\}'
new = 'func stageWorkspace(root, stage string, parallel bool) string {\n\treturn filepath.Join(root, stage)\n}'
s2, n = re.subn(pattern, new, s, count=1, flags=re.S)
if n != 1:
    raise SystemExit('expected M2 stageWorkspace function not found')
p.write_text(s2)
PY
