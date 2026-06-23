#!/usr/bin/env bash
set -euo pipefail
cd /app
python3 <<'PY'
from pathlib import Path
path = Path("/app/java/RemittanceAdapter.java")
text = path.read_text()
text = text.replace('import java.util.ArrayList;\nimport java.util.List;', 'import java.util.ArrayList;\nimport java.util.HashSet;\nimport java.util.List;\nimport java.util.Set;')
text = text.replace('int rejectedCount = 0;\n        for (Row row : rows) {', 'int rejectedCount = 0;\n        Set<String> seen = new HashSet<>();\n        for (Row row : rows) {')
text = text.replace('boolean allowed = railAllowed(rulesUrl, row.rail());\n            if (allowed) {', 'boolean allowed = railAllowed(rulesUrl, row.rail());\n            if (seen.contains(row.id())) {\n                results.add(new Result(row, "DUPLICATE"));\n                continue;\n            }\n            if (allowed) {\n                seen.add(row.id());')
text = text.replace('results.add(new Result(row, "DUPLICATE"));\n                continue;', 'rejectedCount++;\n                results.add(new Result(row, "DUPLICATE"));\n                continue;')
path.write_text(text)
PY
/app/scripts/run_all.sh
test -s /app/out/remit_payload.json
