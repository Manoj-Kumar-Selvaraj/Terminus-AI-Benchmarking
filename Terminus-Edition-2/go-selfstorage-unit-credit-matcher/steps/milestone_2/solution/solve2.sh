#!/usr/bin/env bash
set -euo pipefail

cd /app

python3 <<'PY'
from pathlib import Path

path = Path("/app/cmd/reconcile/main.go")
text = path.read_text()

text = text.replace(
    "UnitType: strings.ToUpper(clean(row[4]))",
    "UnitType: canonicalUnitType(row[4])",
)
text = text.replace(
    "UnitType: strings.ToUpper(clean(row[3]))",
    "UnitType: canonicalUnitType(row[3])",
)
text = text.replace(
    'func clean(value string) string {\n\treturn strings.TrimSpace(value)\n}\n\nfunc allowedUnitType(unit_type string) bool {\n\tunit_type = strings.ToUpper(clean(unit_type))\n\treturn unit_type == "SMALL" || unit_type == "MEDIUM" || unit_type == "LARGE"\n}',
    '''func clean(value string) string {
\treturn strings.TrimSpace(value)
}

func canonicalUnitType(unit_type string) string {
	switch strings.ToUpper(clean(unit_type)) {
	case "SML":
		return "SMALL"
	case "MED":
		return "MEDIUM"
	case "LRG":
		return "LARGE"
	default:
		return strings.ToUpper(clean(unit_type))
	}
}

func allowedUnitType(unit_type string) bool {
\tunit_type = canonicalUnitType(unit_type)
\treturn unit_type == "SMALL" || unit_type == "MEDIUM" || unit_type == "LARGE"
}''',
)

path.write_text(text)
PY

/app/scripts/run_batch.sh
test -s /app/out/credit_report.csv
test -s /app/out/credit_summary.json
