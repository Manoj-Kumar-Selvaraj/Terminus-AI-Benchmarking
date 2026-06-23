#!/usr/bin/env bash
set -euo pipefail

cd /app

python3 <<'PY'
from pathlib import Path

path = Path("/app/cmd/reconcile/main.go")
text = path.read_text()

text = text.replace(
    "Program: strings.ToUpper(clean(row[4]))",
    "Program: canonicalProgram(row[4])",
)
text = text.replace(
    "Program: strings.ToUpper(clean(row[3]))",
    "Program: canonicalProgram(row[3])",
)
text = text.replace(
    'func clean(value string) string {\n\treturn strings.TrimSpace(value)\n}\n\nfunc allowedProgram(program string) bool {\n\tprogram = strings.ToUpper(clean(program))\n\treturn program == "ADULT" || program == "FAMILY" || program == "PATRON"\n}',
    '''func clean(value string) string {
\treturn strings.TrimSpace(value)
}

func canonicalProgram(program string) string {
	switch strings.ToUpper(clean(program)) {
	case "ADT":
		return "ADULT"
	case "FAM":
		return "FAMILY"
	case "PTR":
		return "PATRON"
	default:
		return strings.ToUpper(clean(program))
	}
}

func allowedProgram(program string) bool {
\tprogram = canonicalProgram(program)
\treturn program == "ADULT" || program == "FAMILY" || program == "PATRON"
}''',
)

path.write_text(text)
PY

/app/scripts/run_batch.sh
test -s /app/out/refund_report.csv
test -s /app/out/refund_summary.json
