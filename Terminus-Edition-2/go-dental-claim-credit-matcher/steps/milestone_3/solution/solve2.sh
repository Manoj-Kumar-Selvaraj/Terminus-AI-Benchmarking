#!/usr/bin/env bash
set -euo pipefail

cd /app

python3 <<'PY'
from pathlib import Path

path = Path("/app/cmd/reconcile/main.go")
text = path.read_text()
if "func canonicalProcedure(procedure string)" in text:
    raise SystemExit(0)

text = text.replace(
    "Procedure: strings.ToUpper(clean(row[4]))",
    "Procedure: canonicalProcedure(row[4])",
)
text = text.replace(
    "Procedure: strings.ToUpper(clean(row[3]))",
    "Procedure: canonicalProcedure(row[3])",
)
text = text.replace(
    'func clean(value string) string {\n\treturn strings.TrimSpace(value)\n}\n\nfunc allowedProcedure(procedure string) bool {\n\tprocedure = strings.ToUpper(clean(procedure))\n\treturn procedure == "PREVENTIVE" || procedure == "RESTORATIVE" || procedure == "ORTHO"\n}',
    '''func clean(value string) string {
\treturn strings.TrimSpace(value)
}

func canonicalProcedure(procedure string) string {
	switch strings.ToUpper(clean(procedure)) {
	case "PREV":
		return "PREVENTIVE"
	case "REST":
		return "RESTORATIVE"
	case "ORT":
		return "ORTHO"
	default:
		return strings.ToUpper(clean(procedure))
	}
}

func allowedProcedure(procedure string) bool {
\tprocedure = canonicalProcedure(procedure)
\treturn procedure == "PREVENTIVE" || procedure == "RESTORATIVE" || procedure == "ORTHO"
}''',
)

path.write_text(text)
PY

/app/scripts/run_batch.sh
test -s /app/out/credit_report.csv
test -s /app/out/credit_summary.json
