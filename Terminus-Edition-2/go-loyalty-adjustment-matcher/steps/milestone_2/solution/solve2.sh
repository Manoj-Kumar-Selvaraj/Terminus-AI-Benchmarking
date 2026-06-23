#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STEPS_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
bash "$SCRIPT_DIR/solve1.sh"

cd /app

python3 <<'PY'
from pathlib import Path

path = Path("/app/cmd/reconcile/main.go")
text = path.read_text()

text = text.replace(
    "Reason: strings.ToUpper(clean(row[4]))",
    "Reason: canonicalReason(row[4])",
)
text = text.replace(
    "Reason: strings.ToUpper(clean(row[3]))",
    "Reason: canonicalReason(row[3])",
)
text = text.replace(
    'func clean(value string) string {\n\treturn strings.TrimSpace(value)\n}\n\nfunc allowedReason(reason string) bool {\n\treason = strings.ToUpper(clean(reason))\n\treturn reason == "PURCHASE" || reason == "BONUS" || reason == "PROMO"\n}',
    '''func clean(value string) string {
\treturn strings.TrimSpace(value)
}

func canonicalReason(reason string) string {
\tswitch strings.ToUpper(clean(reason)) {
\tcase "BNS":
\t\treturn "BONUS"
\tcase "PRM":
\t\treturn "PROMO"
\tdefault:
\t\treturn strings.ToUpper(clean(reason))
\t}
}

func allowedReason(reason string) bool {
\treason = canonicalReason(reason)
\treturn reason == "PURCHASE" || reason == "BONUS" || reason == "PROMO"
}''',
)

path.write_text(text)
PY

/app/scripts/run_batch.sh
test -s /app/out/adjustment_report.csv
test -s /app/out/adjustment_summary.json
