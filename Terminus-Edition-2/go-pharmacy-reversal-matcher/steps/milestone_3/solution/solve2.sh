#!/usr/bin/env bash
set -euo pipefail

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
    'func clean(value string) string {\n\treturn strings.TrimSpace(value)\n}\n\nfunc allowedReason(reason string) bool {\n\treason = strings.ToUpper(clean(reason))\n\treturn reason == "RX" || reason == "COPAY" || reason == "COB"\n}',
    '''func clean(value string) string {
\treturn strings.TrimSpace(value)
}

func canonicalReason(reason string) string {
\tswitch strings.ToUpper(clean(reason)) {
\tcase "BEN":
\t\treturn "COPAY"
\tcase "CPY":
\t\treturn "COB"
\tdefault:
\t\treturn strings.ToUpper(clean(reason))
\t}
}

func allowedReason(reason string) bool {
\treason = canonicalReason(reason)
\treturn reason == "RX" || reason == "COPAY" || reason == "COB"
}''',
)

path.write_text(text)
PY

/app/scripts/run_batch.sh
test -s /app/out/reversal_report.csv
test -s /app/out/reversal_summary.json
