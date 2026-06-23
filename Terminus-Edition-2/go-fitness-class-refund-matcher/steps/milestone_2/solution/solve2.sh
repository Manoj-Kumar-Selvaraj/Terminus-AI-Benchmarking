#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
bash "$SCRIPT_DIR/solve1.sh"

cd /app

python3 <<'PY'
from pathlib import Path

path = Path("/app/cmd/reconcile/main.go")
text = path.read_text()

text = text.replace(
    "Studio: strings.ToUpper(clean(row[4]))",
    "Studio: canonicalStudio(row[4])",
)
text = text.replace(
    "Studio: strings.ToUpper(clean(row[3]))",
    "Studio: canonicalStudio(row[3])",
)
text = text.replace(
    'func clean(value string) string {\n\treturn strings.TrimSpace(value)\n}\n\nfunc allowedStudio(studio string) bool {\n\tstudio = strings.ToUpper(clean(studio))\n\treturn studio == "YOGA" || studio == "SPIN" || studio == "HIIT"\n}',
    '''func clean(value string) string {
\treturn strings.TrimSpace(value)
}

func canonicalStudio(studio string) string {
	switch strings.ToUpper(clean(studio)) {
	case "YG":
		return "YOGA"
	case "SP":
		return "SPIN"
	case "HT":
		return "HIIT"
	default:
		return strings.ToUpper(clean(studio))
	}
}

func allowedStudio(studio string) bool {
\tstudio = canonicalStudio(studio)
\treturn studio == "YOGA" || studio == "SPIN" || studio == "HIIT"
}''',
)

path.write_text(text)
PY

/app/scripts/run_batch.sh
test -s /app/out/refund_report.csv
test -s /app/out/refund_summary.json
