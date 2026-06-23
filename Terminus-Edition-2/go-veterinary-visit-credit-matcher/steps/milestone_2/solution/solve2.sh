#!/usr/bin/env bash
set -euo pipefail

cd /app

python3 <<'PY'
from pathlib import Path

path = Path("/app/cmd/reconcile/main.go")
text = path.read_text()

text = text.replace(
    "Clinic: strings.ToUpper(clean(row[4]))",
    "Clinic: canonicalClinic(row[4])",
)
text = text.replace(
    "Clinic: strings.ToUpper(clean(row[3]))",
    "Clinic: canonicalClinic(row[3])",
)
text = text.replace(
    'func clean(value string) string {\n\treturn strings.TrimSpace(value)\n}\n\nfunc allowedClinic(clinic string) bool {\n\tclinic = strings.ToUpper(clean(clinic))\n\treturn clinic == "MAIN" || clinic == "MOBILE" || clinic == "ER"\n}',
    '''func clean(value string) string {
\treturn strings.TrimSpace(value)
}

func canonicalClinic(clinic string) string {
	switch strings.ToUpper(clean(clinic)) {
	case "MN":
		return "MAIN"
	case "VAN":
		return "MOBILE"
	case "URG":
		return "ER"
	default:
		return strings.ToUpper(clean(clinic))
	}
}

func allowedClinic(clinic string) bool {
\tclinic = canonicalClinic(clinic)
\treturn clinic == "MAIN" || clinic == "MOBILE" || clinic == "ER"
}''',
)

path.write_text(text)
PY

/app/scripts/run_batch.sh
test -s /app/out/credit_report.csv
test -s /app/out/credit_summary.json
