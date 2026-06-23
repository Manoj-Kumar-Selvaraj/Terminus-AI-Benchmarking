#!/usr/bin/env bash
set -euo pipefail

cd /app

python3 <<'PY'
from pathlib import Path

path = Path("/app/cmd/reconcile/main.go")
text = path.read_text()
if "func canonicalFormat(format string)" in text:
    raise SystemExit(0)

text = text.replace(
    "Format: strings.ToUpper(clean(row[4]))",
    "Format: canonicalFormat(row[4])",
)
text = text.replace(
    "Format: strings.ToUpper(clean(row[3]))",
    "Format: canonicalFormat(row[3])",
)
text = text.replace(
    """func allowedFormat(format string) bool {
\tformat = strings.ToUpper(clean(format))
\treturn format == "LP" || format == "EP" || format == "BOX"
}""",
    """func canonicalFormat(format string) string {
\tswitch strings.ToUpper(clean(format)) {
\tcase "LONG":
\t\treturn "LP"
\tcase "SING":
\t\treturn "EP"
\tcase "SET":
\t\treturn "BOX"
\tdefault:
\t\treturn strings.ToUpper(clean(format))
\t}
}

func allowedFormat(format string) bool {
\tformat = canonicalFormat(format)
\treturn format == "LP" || format == "EP" || format == "BOX"
}""",
)

path.write_text(text)
PY

/app/scripts/run_batch.sh
test -s /app/out/credit_report.csv
test -s /app/out/credit_summary.json
